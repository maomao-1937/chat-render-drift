"""Compare rendered chat bytes and token IDs from two local JSON captures."""

import hashlib
import json
import os
from pathlib import PureWindowsPath
import stat
import sys


MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOKEN_IDS = 200_000
UINT32_MAX = 4294967295
FIELDS = {"rendered_text", "token_ids"}
USAGE = """usage: python -I chat_render_drift.py [--] BASELINE.json CANDIDATE.json

Compare rendered UTF-8 bytes and token IDs from two local JSON captures.
Exit 0 for a match, 1 for drift, or 2 for an error.
"""


class InvalidCapture(ValueError):
    """An input error with a fixed diagnostic code."""


def check_path(path):
    if not path or path == "-" or "\x00" in path:
        raise InvalidCapture("invalid_file")
    if os.name == "nt":
        windows_path = PureWindowsPath(path)
        # UNC and device namespaces are not local file paths. An alternate
        # data stream can look like a file to stat, so reject it lexically.
        if windows_path.drive.startswith("\\\\") or path.replace("\\", "/").startswith("//"):
            raise InvalidCapture("invalid_file")
        is_reserved = getattr(os.path, "isreserved", None)
        for part in windows_path.parts[1 if windows_path.anchor else 0:]:
            if ":" in part:
                raise InvalidCapture("invalid_file")
            if is_reserved is None:
                reserved = PureWindowsPath(part).is_reserved()  # Python 3.11–3.12
            else:
                reserved = is_reserved(part)
            if reserved:
                raise InvalidCapture("invalid_file")


def check_file(info):
    if not stat.S_ISREG(info.st_mode):
        raise InvalidCapture("invalid_file")
    if info.st_size > MAX_FILE_BYTES:
        raise InvalidCapture("file_limit")


def read_file(path):
    check_path(path)
    check_file(os.stat(path))
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        check_file(os.fstat(descriptor))
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(data) > MAX_FILE_BYTES:
        raise InvalidCapture("file_limit")
    return data


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidCapture("duplicate_key")
        result[key] = value
    return result


def parse_integer(digits):
    # No valid uint32 representation needs more than ten characters.
    if len(digits) > 10:
        raise InvalidCapture("invalid_token_id")
    return int(digits)


def reject_constant(_):
    raise InvalidCapture("invalid_json")


def load_capture(path):
    try:
        data = read_file(path)
    except (OSError, UnicodeError):
        raise InvalidCapture("invalid_file") from None
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidCapture("invalid_utf8") from None
    try:
        capture = json.loads(
            content, object_pairs_hook=unique_object,
            parse_int=parse_integer, parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, RecursionError):
        raise InvalidCapture("invalid_json") from None
    if not isinstance(capture, dict) or capture.keys() != FIELDS:
        raise InvalidCapture("invalid_fields")
    rendered = capture["rendered_text"]
    tokens = capture["token_ids"]
    if not isinstance(rendered, str):
        raise InvalidCapture("invalid_rendered_text")
    try:
        rendered = rendered.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidCapture("invalid_rendered_text") from None
    if not isinstance(tokens, list):
        raise InvalidCapture("invalid_token_ids")
    if len(tokens) > MAX_TOKEN_IDS:
        raise InvalidCapture("token_limit")
    if any(type(token) is not int or not 0 <= token <= UINT32_MAX for token in tokens):
        raise InvalidCapture("invalid_token_id")
    return rendered, tokens


def first_difference(baseline, candidate):
    for index, (before, after) in enumerate(zip(baseline, candidate)):
        if before != after:
            return index
    if len(baseline) != len(candidate):
        return min(len(baseline), len(candidate))
    return None


def emit(descriptor, output, status):
    remaining = memoryview(output.encode("ascii"))
    try:
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                return 2
            remaining = remaining[written:]
    except OSError:
        return 2
    return status


def json_line(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"


def main(args):
    if args in (["-h"], ["--help"]):
        return emit(1, USAGE, 0)
    separator = args.index("--") if "--" in args else len(args)
    paths = args[:separator] + args[separator + 1:]
    if len(paths) != 2 or any(arg.startswith("-") and arg != "-" for arg in args[:separator]):
        return emit(2, json_line({"error": "usage"}), 2)
    captures = []
    for side, path in zip(("baseline", "candidate"), paths):
        try:
            captures.append(load_capture(path))
        except InvalidCapture as error:
            return emit(2, json_line({"error": str(error), "side": side}), 2)

    (baseline_text, baseline_tokens), (candidate_text, candidate_tokens) = captures
    byte_index = first_difference(baseline_text, candidate_text)
    token_index = first_difference(baseline_tokens, candidate_tokens)
    report = {
        "rendered_text": {
            "baseline_bytes": len(baseline_text),
            "candidate_bytes": len(candidate_text),
            "baseline_sha256": hashlib.sha256(baseline_text).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate_text).hexdigest(),
            "first_difference": byte_index,
        },
        "token_ids": {
            "baseline_count": len(baseline_tokens),
            "candidate_count": len(candidate_tokens),
            "first_difference": token_index,
        },
    }
    return emit(1, json_line(report), int(byte_index is not None or token_index is not None))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
