# Testing

Run from the repository root with Python 3.11 or later.

```sh
python -I -m unittest discover -s tests -v
python -I examples/run_examples.py
```

The Windows Python 3.11.15 run on November 12, 2026 Singapore time passed 18 CLI tests, one Windows path API regression, and all five examples. One POSIX FIFO test was skipped on Windows. The workflow runs both commands on Ubuntu and Windows. The Windows device-path CLI test is skipped on POSIX.

Tests check independent sequence changes, UTF-8 offsets, prefix and empty cases, JSON syntax and value validation, Unicode handling, size boundaries, and sanitized errors for invalid files and closed output pipes. The example runner checks exact stdout and stderr bytes and the process exit code using [commands](checks.json) and [expected output](examples/expected.json).

| Command | Expected exit | Expected differences (byte, token) |
| --- | --- | --- |
| `python -I chat_render_drift.py examples/baseline.json examples/same.json` | `0` | `null`, `null` |
| `python -I chat_render_drift.py examples/baseline.json examples/byte-drift.json` | `1` | `8`, `null` |
| `python -I chat_render_drift.py examples/baseline.json examples/token-drift.json` | `1` | `null`, `1` |
| `python -I chat_render_drift.py examples/baseline.json examples/both-prefix-drift.json` | `1` | `9`, `1` |
| `python -I chat_render_drift.py examples/baseline.json examples/duplicate-key.json` | `2` | `duplicate_key` on the candidate |
