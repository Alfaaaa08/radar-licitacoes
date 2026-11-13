# Radar de Licitações

> Brazilian public tenders read by AI, with every extracted field pointing back to the page it came from, and with extraction accuracy measured and published.

**Status:** under construction (week 1 of 12).

## The problem

Brazil publishes every public procurement on the [National Public Procurement Portal (PNCP)](https://pncp.gov.br). A small IT company that wants to sell to the government has to read dozens of tender notices a week, each 50 to 100 pages long, just to find deadlines, budgets and qualification requirements. Commercial platforms already use AI for this, but none of them show **how reliable** their AI extraction is.

## What the Radar does

1. Collects, every day, the tender notices on PNCP that are still open for proposals.
2. Uses an LLM to extract the fields that matter (deadlines, budget, qualification requirements, guarantees, site visits, small-business preference), **each with the quote and page number it came from**.
3. Measures extraction against a hand-labeled gold set and publishes per-field accuracy.
4. Answers questions about a tender with citations, and says "not found in this tender" when the answer isn't there.

## Principles

- **Every AI output is verifiable:** a cited quote, a deterministic validation, or a published metric.
- **AI only where it wins:** collection, filters and validations are plain code; agents only where the steps can't be known in advance.
- **Cost under control:** batch processing and a hard monthly spending cap.

## Architecture (planned)

```
PNCP API → daily collector (no AI) → PostgreSQL + pgvector
                                          ↕
                           batch AI pipeline (extraction, classification, embeddings)
                                          ↓
                           API (FastAPI) → public site + quality page
```

## Running locally

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/) and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env          # PowerShell: Copy-Item .env.example .env
docker compose up -d          # starts PostgreSQL 17 + pgvector on port 5433
uv sync                       # creates the Python environment and installs dependencies
uv run python scripts/check_db.py
uv run pytest
```

Save one raw page of open tenders from PNCP (electronic auctions, proposals closing in the next 30 days):

```bash
uv run python scripts/fetch_sample.py
uv run python scripts/fetch_sample.py --state SP --page-size 20
```

The JSON goes to `data/raw/` (ignored by Git) and the script prints how often each field is filled.

Collect open tenders into PostgreSQL, one state at a time:

```bash
uv run python scripts/collect.py --states SP --max-pages 2
uv run python scripts/collect.py
```

Running it again is safe: tenders already stored are not duplicated, and every run is recorded in `collection_runs`.

## Design decisions

- **`pncp_control_number` is the primary key.** It is the PNCP's own identifier, so running the collector twice never duplicates a tender (idempotent collection).
- **The `payload` column keeps the raw API response.** If a field turns out to be needed later, there is no need to collect everything again.
- **`collection_runs` records every run** (pages, new tenders, errors), which feeds the collection reliability numbers published here.
- **The collector slices by state.** One broad query for all open electronic auctions took 51 seconds and returned HTTP 500, while the same query for one state answered in 0.2 seconds.
- **Transient failures are retried, bad requests are not.** Timeouts, HTTP 429 and HTTP 5xx are retried with a delay that doubles (2s, 4s, 8s, up to 60s). A state that still fails is recorded in `collection_runs.errors` and the run moves on to the next state.
- **Unchanged tenders are not rewritten.** The upsert only updates a row when the API payload changed, so `updated_at` means "the PNCP changed this tender".
- **PNCP notes live in [`docs/pncp-notes.md`](docs/pncp-notes.md):** endpoints, parameters and the quirks found while testing the API.

## Glossary

| Portuguese | English | Meaning |
| --- | --- | --- |
| Licitação | Public tender | A government purchase open to bids |
| Edital | Tender notice | The document with the rules, deadlines and requirements of a tender |
| Pregão eletrônico | Electronic reverse auction | The most common tender modality for goods and services |
| Habilitação | Qualification | Documents a bidder must provide to be eligible |
| ME/EPP | Micro and small enterprises | Companies that may get exclusive or preferential treatment |

## Project log

| Date | What changed |
| --- | --- |
| 2026-11-10 | Repository created: Docker Compose with Postgres + pgvector, initial schema (`tenders`, `collection_runs`). |
| 2026-11-11 | PNCP client for open-proposal tenders, raw page sample script with field coverage report, no-comments convention. |
| 2026-11-12 | Collector: slicing by state, retries with backoff, idempotent upsert into `tenders`, run log in `collection_runs`. Page size capped at 50 after the API rejected 60. |

## Disclaimer

Demonstration project. It does not replace reading the full tender notice or legal advice.
