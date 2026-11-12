"""Check the exact stdout, stderr and exit code of the bundled examples."""

import json
from pathlib import Path
import subprocess
import sys


def expected_bytes(value):
    if value is None:
        return b""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"


def main():
    root = Path(__file__).resolve().parents[1]
    checks = json.loads((root / "checks.json").read_text(encoding="utf-8"))
    outputs = json.loads((root / "examples" / "expected.json").read_text(encoding="utf-8"))
    for check, output in zip(checks, outputs, strict=True):
        result = subprocess.run(
            [sys.executable, "-I", *check["args"]],
            cwd=root,
            capture_output=True,
            timeout=15,
        )
        expected = (check["exit"], expected_bytes(output["stdout"]), expected_bytes(output["stderr"]))
        actual = (result.returncode, result.stdout, result.stderr)
        name = Path(check["args"][-1]).name
        if actual != expected:
            raise SystemExit(f"FAIL {name}\nexpected {expected!r}\nactual   {actual!r}")
        print(f"PASS {name} (exit {check['exit']})")


if __name__ == "__main__":
    main()
