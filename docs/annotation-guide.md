# Annotation guide

The gold set is a list of tender notices read by a human. Every AI extraction is later compared with it, so the rules below must be applied the same way on every notice. When a rule does not cover a case, decide, write the decision under **Decisions log** at the end of this file and apply it from then on.

## What is annotated

- One notice per file in `gold/annotations/`, created with `scripts/new_annotation.py`.
- Only the text of the notice itself (the document listed in `document_sequence`). Do not use the PNCP metadata, the terms of reference or other annexes. If the notice defers a fact to an annex that is not in the document, the field is `not_found`.
- Seven fields, defined in `src/radar/schema.py`. Each one has a `status`:
  - `found`: the notice states it. `value` and `evidence` are both required.
  - `not_found`: the notice is silent. `value` and `evidence` stay `null`.

An explicit negative is a finding, not an absence. "Visit is not required" is `found` with `not_required`. A notice that never mentions visits is `not_found`.

## Evidence

- `page` is the page number in `document_pages` (starts at 1), the page that holds the decisive sentence. `scripts/show_pages.py` prints the same numbering.
- `quote` is copied from the extracted text of that page: the shortest passage that proves the value, at most 500 characters. Case, accents and line breaks do not matter when it is checked, but the words must be there.
- When the same fact appears in several places, cite the clause in the body of the notice rather than a summary table or the cover page. If two places contradict each other, annotate the body clause and say so in `notes`.

## Fields

| Field | Value | Rule |
| --- | --- | --- |
| `proposal_deadline` | date and time, `2026-11-20T09:00:00` | When proposals stop being received. If the notice says proposals are accepted "until the opening of the session", use the session date and time. Brasília time, as written. A date without a time is `not_found`, with the reason in `notes`. |
| `estimated_value` | number in reais, `150000.50` | Total estimated value of the whole procurement. If only per-item or per-lot values are given, do not add them up: `not_found` and say so in `notes`. A confidential budget ("sigiloso") is `not_found` with `notes: confidential`. |
| `requires_technical_certificate` | `true` / `false` | `true` when the qualification section requires one or more certificates of technical capacity issued by clients (atestado de capacidade técnica). `false` only when the notice says technical qualification is not required. Registration with a professional council alone does not make it `true`. |
| `bid_bond_percentage` | 0 to 100 | Guarantee for submitting a proposal (garantia de proposta / de participação), as a percentage of the estimated value. `0` only when the notice says it is not required. A fixed amount without a percentage is `not_found`, with the amount in `notes`. |
| `performance_bond_percentage` | 0 to 100 | Guarantee for executing the contract (garantia de execução / contratual), as a percentage of the contract value. `0` only when the notice says it is not required. |
| `site_visit` | `required`, `optional`, `not_required` | `required` for a mandatory visit or inspection (vistoria obrigatória). `optional` for "facultativa". `not_required` when the notice says it is not needed or dispenses it. |
| `small_business_preference` | `exclusive`, `quota`, `preference`, `none` | Treatment of micro and small enterprises (ME/EPP). `exclusive` when the tender or any lot is reserved for them. `quota` when a reserved share is set aside. `preference` when the notice only grants the legal tie-break and benefits. `none` when the notice says no such treatment applies. When several apply, use the strongest in this order: `exclusive`, `quota`, `preference`, and list the others in `notes`. |

## Example

```json
"site_visit": {
  "status": "found",
  "value": "optional",
  "evidence": {
    "page": 14,
    "quote": "A visita técnica ao local é facultativa, devendo ser agendada com 48 horas de antecedência."
  }
}
```

```json
"bid_bond_percentage": {
  "status": "not_found",
  "value": null,
  "evidence": null
}
```

## Workflow

1. `uv run python scripts/select_gold.py` picks 20 IT tenders with extracted text, mixing federal, state and municipal agencies. It refuses to run twice: the selection must stay fixed once annotation starts.
2. `uv run python scripts/new_annotation.py --next --annotator YOUR_NAME` creates a blank file for the next tender.
3. `uv run python scripts/show_pages.py CONTROL_NUMBER --hints` lists the lines that mention each topic, with page numbers. Use `--grep TERM` or `--page N` to read more. When in doubt, open the PDF in `data/pdfs/`.
4. Edit the JSON file. Fill `found` fields completely and leave the rest as `not_found`.
5. `uv run python scripts/validate_gold.py` checks the schema and that every quote really is on its cited page.
6. Commit `gold/`. The PDFs and the database are not committed, only the annotations.

## Decisions log

Add a line for each case the rules above did not cover.

| Date | Case | Decision |
| --- | --- | --- |
