# chat-render-drift

Compare rendered chat bytes and token IDs from two saved captures. Use the CLI in eval or CI to see which sequence changed after a template, tokenizer, or serving configuration upgrade.

Python 3.11 or newer. Standard library only. Runs offline and contacts no model provider.

Locally tested on Windows with CPython 3.11.15. CI runs the tests and examples on Ubuntu and Windows.

## Quickstart

From the repository root, compare the two bundled captures with the same rendered text and different token IDs.

```sh
python -I chat_render_drift.py examples/baseline.json examples/token-drift.json
```

The command exits `1` and prints one JSON line. Shown formatted here for readability.

```json
{
  "rendered_text": {
    "baseline_bytes": 9,
    "baseline_sha256": "15417f7a06f241d8541c03d1293055facc37edbd92dedcac6ab6fdef76c8e24a",
    "candidate_bytes": 9,
    "candidate_sha256": "15417f7a06f241d8541c03d1293055facc37edbd92dedcac6ab6fdef76c8e24a",
    "first_difference": null
  },
  "token_ids": {
    "baseline_count": 2,
    "candidate_count": 2,
    "first_difference": 1
  }
}
```

Use `examples/same.json` as the candidate to get exit `0`. Use `examples/byte-drift.json` to get exit `1` with byte offset `8` and matching token IDs. [Every example and its expected exit](TESTING.md).

## Capture format and comparison

In your own pipeline, save the rendered prompt before tokenization and the input IDs actually passed to inference for the same message fixture. Export one file from the baseline and one from the candidate. Each file must contain exactly these fields.

```json
{"rendered_text":"<chat>\nhello","token_ids":[12,37]}
```

- Inputs are two local regular files, each at most **4 MiB (4,194,304 bytes)**, with strict UTF-8 encoding and no BOM. Duplicate keys, malformed JSON, lone surrogates, and additional fields are rejected. Use paths you trust on a local filesystem. The operating system follows symlinks, junctions, and mounts, which may lead to remote storage. On Windows, explicit UNC and device paths and alternate data streams are rejected.
- `rendered_text` is a string and `token_ids` is an array with at most **200,000** integers in `0..4294967295`. Empty strings and arrays are valid. Booleans and decimal or exponent forms are rejected as token IDs.
- Both `first_difference` values use zero-based indexes. An exact match gives `null`. If one sequence is a strict prefix of the other, the index equals the length of the shorter sequence. A byte offset can fall inside a multi-byte Unicode character.
- Each side has a byte count, a SHA-256 fingerprint of the UTF-8 rendered text, and a token ID count. The comparison preserves whitespace, line endings, and Unicode composition within the text. JSON escaping, object key order, and outer JSON whitespace have no effect.

Pass the baseline and candidate paths in that order. The input limits are fixed. `-h` and `--help` print usage. Use `--` before a path that starts with `-`. The CLI prints no prompt text, token ID values, or input paths. Treat the report as metadata about the captures. A digest can identify a short or guessable prompt by comparison with known text.

| Exit | Meaning | Output |
| --- | --- | --- |
| `0` | Both sequences match | JSON report on stdout |
| `1` | Either sequence differs | JSON report on stdout |
| `2` | Usage, capture, or I/O error | Errors for usage and captures give one JSON object on stderr and no stdout |

Usage errors contain `{"error":"usage"}`. Capture errors include a fixed `error` code and `side` of `baseline` or `candidate`, for example `{"error":"duplicate_key","side":"candidate"}`. Error codes cover file access or type (`invalid_file`), limits (`file_limit`, `token_limit`), decoding (`invalid_utf8`, `invalid_json`, `duplicate_key`), and schema validation (`invalid_fields`, `invalid_rendered_text`, `invalid_token_ids`, `invalid_token_id`).

## 中文说明

在模型模板、分词器或推理服务配置升级前后，分别保存同一组测试消息的渲染文本和实际输入 token ID。工具独立比较两组 UTF-8 字节和两组 ID，适合在评测或 CI 中发现哪部分发生变化。运行需要 Python 3.11 或更新版本，仅使用标准库，整个比较过程离线完成。

在仓库根目录运行下面三条命令，退出码依次为 `0`、`1`、`1`。后两条分别演示仅文本字节变化、仅 token ID 变化。

```sh
python -I chat_render_drift.py examples/baseline.json examples/same.json
python -I chat_render_drift.py examples/baseline.json examples/byte-drift.json
python -I chat_render_drift.py examples/baseline.json examples/token-drift.json
```

- 输入依次为基线和候选文件，均为无 BOM 的 UTF-8 本地普通文件，单个文件不超过 **4 MiB（4,194,304 字节）**。对象只能有 `rendered_text` 和 `token_ids` 两个字段。重复键、非法 JSON 和孤立代理码点会报错。请使用本地文件系统上可信的路径。系统会解析符号链接、目录联接和挂载点，其目标可能是远程存储。Windows 下拒绝显式 UNC、设备路径及备用数据流。
- 文本为字符串，ID 数组最多包含 **200,000** 项，每项为 `0..4294967295` 的整数。空文本和空数组有效，布尔值、小数和指数写法无效。限制固定。`--help` 显示用法，`--` 后可以传入以 `-` 开头的文件名。
- 报告包含两侧文本字节数、SHA-256 指纹、ID 数量，以及两个从零开始的首差位置。相同则为 `null`。若一侧先结束，位置为较短序列的长度。文本保留空白、换行和 Unicode 组合形式，JSON 中等价的转义不影响比较。
- 两组序列均相同返回 `0`，至少一组不同返回 `1`，用法、数据或 I/O 出错返回 `2`。用法及数据错误输出固定 JSON 诊断。报告不输出原文、具体 ID 或路径，但可猜测的文本仍可能通过比对哈希识别。

运行全部测试和示例。

```sh
python -I -m unittest discover -s tests -v
python -I examples/run_examples.py
```

See [research and scope](RESEARCH.md), [verification](TESTING.md), and the [MIT license](LICENSE).
