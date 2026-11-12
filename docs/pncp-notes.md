# PNCP notes

Source for the first sections: the official [PNCP query API manual](https://www.gov.br/pncp/pt-br/acesso-a-informacao/manuais/ManualPNCPAPIConsultasVerso1.0.pdf). Items marked **to verify** were not tested against the live API yet.

## Endpoint

`GET https://pncp.gov.br/api/consulta/v1/contratacoes/proposta` lists purchases that are still receiving proposals.

| Parameter | Required | Notes |
| --- | --- | --- |
| `dataFinal` | yes | `YYYYMMDD`. Latest proposal deadline to include |
| `codigoModalidadeContratacao` | yes | One call per modality |
| `pagina` | yes | Starts at 1 |
| `tamanhoPagina` | no | Maximum is 50. The manual says 500, but 60 returns HTTP 400 "Tamanho de página inválido" |
| `uf` | no | State code of the purchasing unit |
| `cnpj` | no | Agency CNPJ |
| `codigoMunicipioIbge` | no | IBGE municipality code |

## Response

Wrapper fields: `data`, `totalRegistros`, `totalPaginas`, `numeroPagina`, `paginasRestantes`, `empty`.

Fields used by the schema so far:

| API field | Column in `tenders` |
| --- | --- |
| `numeroControlePNCP` | `pncp_control_number` |
| `orgaoEntidade.cnpj` | `agency_cnpj` |
| `anoCompra` | `purchase_year` |
| `sequencialCompra` | `purchase_sequence` |
| `modalidadeId` | `modality_id` |
| `unidadeOrgao.ufSigla` | `state_code` |
| `objetoCompra` | `object_description` |
| `valorTotalEstimado` | `estimated_value` |
| `dataPublicacaoPncp` | `published_at` |
| `dataEncerramentoProposta` | `proposals_close_at` |

## Modality codes

| Code | Name |
| --- | --- |
| 1 | Leilão - Eletrônico |
| 2 | Diálogo Competitivo |
| 3 | Concurso |
| 4 | Concorrência - Eletrônica |
| 5 | Concorrência - Presencial |
| 6 | Pregão - Eletrônico |
| 7 | Pregão - Presencial |
| 8 | Dispensa de Licitação |
| 9 | Inexigibilidade |
| 10 | Manifestação de Interesse |
| 11 | Pré-qualificação |
| 12 | Credenciamento |
| 13 | Leilão - Presencial |

## Quirks reported by other users (to verify)

- `palavraChave` and `niFornecedor` are accepted but silently ignored.
- HTTP 204 with an empty body means no records, not an error.
- After roughly 15 rapid calls the API answers HTTP 429 with an HTML body.
- The manual lists `situacaoCompraNome` as an integer and spells `razaosocial` inconsistently.

## Observed while testing

Test of 2026-11-11, modality 6, `dataFinal=20261211`, page 1.

- Page size 50 works. Page size 60 returns HTTP 400. The minimum was not tested.
- 17,094 open electronic auctions at that date, which is 342 pages of 50. A full collection is hundreds of calls, so it needs throttling.
- One request with page size 40 stalled until it was interrupted by hand. Slow responses happen, so the client needs a generous read timeout and retries.
- Real field names differ from the manual: `orgaoEntidade.razaoSocial` (camelCase) and `tipoInstrumentoConvocatorioCodigo` (not `...Id`).
- Fields missing from the manual: `dataAtualizacaoGlobal`, `emendaParlamentar`, `fontesOrcamentarias`, `linkProcessoEletronico`.
- Filled in all 50 records: every field used by the schema above, plus `numeroCompra`, `processo`, `srp`, `modoDisputaId`, `situacaoCompraId` and the `amparoLegal` object.
- Partly filled: `linkSistemaOrigem` (41/50), `informacaoComplementar` (33/50).
- Almost always empty: `emendaParlamentar`, `fontesOrcamentarias`, `linkProcessoEletronico` (0/50), `valorTotalHomologado` and `justificativaPresencial` (3/50), `orgaoSubRogado` and `unidadeSubRogada` (1/50, and `null` otherwise).
- Date formats: check in the saved JSON.
- Calls before HTTP 429: not reached yet.
