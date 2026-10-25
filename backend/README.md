# llmwatch (backend)

The FastAPI backend and `llmwatch` command-line tool of
[LLMWatch](https://github.com/omer-ulucan/llmwatch), a self-hostable LLMOps
platform. See the repository README for setup and documentation.

## Development

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"
.venv/bin/llmwatch serve --reload   # API on http://127.0.0.1:8000
.venv/bin/pytest
ruff check . && ruff format --check .
```
