ALTER TABLE tenders ADD COLUMN IF NOT EXISTS it_matched_terms TEXT[];
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS it_checked_at TIMESTAMPTZ;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS documents_listed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS tender_documents (
    id                   BIGSERIAL PRIMARY KEY,
    pncp_control_number  TEXT NOT NULL REFERENCES tenders (pncp_control_number) ON DELETE CASCADE,
    document_sequence    INTEGER NOT NULL,
    document_type_id     INTEGER,
    document_type_name   TEXT,
    title                TEXT,
    source_url           TEXT,
    published_at         TIMESTAMPTZ,
    payload              JSONB NOT NULL,
    download_status      TEXT NOT NULL DEFAULT 'pending'
        CHECK (download_status IN ('pending', 'downloaded', 'failed', 'skipped')),
    download_error       TEXT,
    file_path            TEXT,
    file_type            TEXT,
    size_bytes           BIGINT,
    sha256               TEXT,
    text_status          TEXT CHECK (text_status IN ('text', 'scanned', 'failed', 'unsupported')),
    page_count           INTEGER,
    char_count           INTEGER,
    downloaded_at        TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pncp_control_number, document_sequence)
);

CREATE INDEX IF NOT EXISTS idx_tender_documents_status ON tender_documents (download_status);

CREATE TABLE IF NOT EXISTS document_pages (
    document_id  BIGINT NOT NULL REFERENCES tender_documents (id) ON DELETE CASCADE,
    page_number  INTEGER NOT NULL,
    text         TEXT NOT NULL,
    PRIMARY KEY (document_id, page_number)
);
