# Conventions

## Language

Everything in the repository is written in **English**: code, identifiers, comments, docstrings, database tables and columns, commit messages, issues, pull requests, the README and these docs.

The only exception is **text shown to end users** on the public site (labels, messages, AI answers), which is in Brazilian Portuguese because the users are Brazilian. That text will live in its own files (for example `web/locales/pt-BR.json` or prompt templates under `prompts/`), never mixed into code.

Domain terms keep their English equivalent in code (`tender`, not `edital`). The README glossary maps them. When a field mirrors a PNCP API field, keep a comment with the original Portuguese name.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`. Imperative mood, short subject line.

```
feat: add daily PNCP collector with retries
docs: add first extraction accuracy table
```

## Python

- Python 3.12+, dependencies managed with `uv`.
- `ruff check` and `ruff format` before committing.
- Tests with `pytest` under `tests/`.
