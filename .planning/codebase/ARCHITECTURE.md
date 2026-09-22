# Architecture

- `config` establishes process-wide paths and labels; `data_store`, `persona`, `memory`, and `retrieval` provide state/content services.
- `llm` resolves a backend and owns generation/summarization; `scaffold` composes Telegram handlers and the shared bot lifecycle.
- `admin`, `ratelimit`, and `singleinstance` are focused operational modules; bot-specific code remains in consumer repositories.
