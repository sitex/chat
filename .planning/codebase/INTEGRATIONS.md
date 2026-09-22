# Integrations

- Telegram Bot API through `python-telegram-bot` (`chatcore/scaffold.py`).
- LLM boundaries for CLIProxyAPI, explicit CLI/provider backends, and Ollama (`chatcore/llm.py`).
- SQLite conversation/state storage (`chatcore/memory.py`) and optional study-repository facts (`chatcore/retrieval.py`).
- Consumer bots install tagged or Git-based `chatcore` versions; deployment templates live in `chatcore/templates/`.
