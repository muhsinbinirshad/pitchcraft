# Contributing

Thanks for your interest in Pitchcraft.

## Development setup

```bash
./scripts/install.sh   # or: make setup && make build
make dev               # API on :8600, web UI with hot reload on :3600
make test              # offline tests, no API key needed
```

## Guidelines

- Keep the Word engine (`pitchcraft/engine/`) free of AI calls. Model code belongs in `pitchcraft/ai/`.
- Add or update tests for behaviour changes, and run `make test` before opening a pull request.
- Keep pull requests focused, and explain what changed and why.

## Test documents

Some tests need a real proposal. Put any finished `.docx` at `private/fixtures/client_base.docx`. The `private/` folder is git-ignored, and those tests are skipped when the file is missing.

Never commit client documents, API keys or `.env` files.
