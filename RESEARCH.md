# Research and scope

## Why compare the two sequences

- Hugging Face documents that `apply_chat_template` can render or tokenize a conversation. Options such as `add_generation_prompt` and `continue_final_message` affect assistant-turn formatting, and special-token handling matters when tokenization is separate. [Transformers chat templating guide](https://github.com/huggingface/transformers/blob/main/docs/source/en/chat_templating.md)
- llama.cpp documents `/apply-template` for rendering and `/tokenize` for producing token IDs from text, with options for inserting and parsing special tokens. These interfaces can generate captures in a llama.cpp pipeline. [llama.cpp server documentation](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md)
- The author of llama.cpp issue #23840 reported different token IDs for identical text across llama.cpp and Hugging Face Transformers around a leading space after a special token. The issue carries `bug-unconfirmed` and `stale` labels and was closed as not planned after inactivity. [llama.cpp issue #23840](https://github.com/ggml-org/llama.cpp/issues/23840)
- The author of vLLM issue #46256 reported that DeepSeek tokenizer modes ignored rendering flags in some cases. The report motivates retaining rendered output alongside IDs. [vLLM issue #46256](https://github.com/vllm-project/vllm/issues/46256)

## What this project adds

The upstream tools render, tokenize, or serve chats. This CLI compares their already saved outputs with independent byte and token-ID offsets, fixed exit codes, and metadata-only reporting. A text-only diff cannot detect a change in IDs for identical text. A source-file fingerprint measures the input files to the pipeline, while this comparator measures the recorded outputs. [Related source-fingerprint tool](https://github.com/maomao-1937/prompt-lock)

The bundled captures are original synthetic examples. They verify known comparison outcomes. The upstream issue reports were read without running their reproductions or testing any model or provider. Drift can be intentional and cannot establish which capture is correct, which component caused the difference, or whether model output quality changed. Token ID comparisons are most interpretable with comparable vocabularies. Keep the message fixture, tokenizer and template versions, options, and capture stage in your pipeline metadata.
