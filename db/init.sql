-- Runs once, when the database volume is first created.
CREATE EXTENSION IF NOT EXISTS vector;

-- Raw tender notices, exactly as returned by the PNCP API.
-- The PNCP control number is the primary key, which makes collection idempotent:
-- running the collector twice on the same day never duplicates a tender.
CREATE TABLE IF NOT EXISTS tenders (
    pncp_control_number  TEXT PRIMARY KEY,
    agency_cnpj          TEXT NOT NULL,
    purchase_year        INTEGER NOT NULL,
    purchase_sequence    INTEGER NOT NULL,
    modality_id          INTEGER,
    state_code           CHAR(2),
    object_description   TEXT,
    estimated_value      NUMERIC(18, 2),
    published_at         TIMESTAMPTZ,
    proposals_close_at   TIMESTAMPTZ,
    payload              JSONB NOT NULL,
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenders_proposals_close_at ON tenders (proposals_close_at);
CREATE INDEX IF NOT EXISTS idx_tenders_state_code ON tenders (state_code);

-- One row per collector run: pages fetched, tenders seen and new, errors.
-- This feeds the "how collection behaves" section of the README.
CREATE TABLE IF NOT EXISTS collection_runs (
    id            BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    pages         INTEGER NOT NULL DEFAULT 0,
    tenders_new   INTEGER NOT NULL DEFAULT 0,
    tenders_seen  INTEGER NOT NULL DEFAULT 0,
    errors        JSONB NOT NULL DEFAULT '[]'::jsonb
);
