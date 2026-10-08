CREATE TABLE lesson_source_file (
    id CHAR(26) PRIMARY KEY,
    job_id CHAR(26) NOT NULL,
    kind VARCHAR(32) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    media_type VARCHAR(128) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    storage_key VARCHAR(512) NOT NULL,
    parse_status VARCHAR(24) NOT NULL,
    parse_warnings JSON,
    normalized_plan_storage_key VARCHAR(512),
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_source_job FOREIGN KEY (job_id) REFERENCES lesson_job(id),
    CONSTRAINT uq_source_job_kind UNIQUE (job_id, kind)
);

CREATE TABLE lesson_artifact (
    id CHAR(26) PRIMARY KEY,
    job_id CHAR(26) NOT NULL,
    engine_artifact_id VARCHAR(128),
    artifact_type VARCHAR(40) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    media_type VARCHAR(128) NOT NULL,
    storage_key VARCHAR(512) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL,
    error_message VARCHAR(1000),
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_artifact_job FOREIGN KEY (job_id) REFERENCES lesson_job(id),
    CONSTRAINT uq_artifact_job_type UNIQUE (job_id, artifact_type)
);

CREATE INDEX idx_artifact_job ON lesson_artifact(job_id);
