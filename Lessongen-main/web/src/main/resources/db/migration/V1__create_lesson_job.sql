CREATE TABLE lesson_job (
    id CHAR(26) PRIMARY KEY,
    mode VARCHAR(16) NOT NULL,
    status VARCHAR(24) NOT NULL,
    status_version BIGINT NOT NULL DEFAULT 0,
    subject VARCHAR(64) NOT NULL,
    grade VARCHAR(64) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    duration_minutes SMALLINT NOT NULL,
    request_snapshot JSON NOT NULL,
    request_sha256 CHAR(64) NOT NULL,
    idempotency_key VARCHAR(128),
    retry_of_job_id CHAR(26),
    engine_run_id VARCHAR(255),
    current_stage VARCHAR(64),
    current_round SMALLINT NOT NULL DEFAULT 0,
    progress_percent TINYINT NOT NULL DEFAULT 0,
    pipeline_status VARCHAR(24),
    stop_reason VARCHAR(64),
    best_version_id VARCHAR(64),
    last_version_id VARCHAR(64),
    model_call_count INT NOT NULL DEFAULT 0,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    estimated_cost DECIMAL(12,6) NOT NULL DEFAULT 0,
    error_code VARCHAR(64),
    error_message VARCHAR(1000),
    result_storage_key VARCHAR(512),
    last_engine_event_sequence BIGINT NOT NULL DEFAULT 0,
    owner_id CHAR(26),
    created_at DATETIME(6) NOT NULL,
    started_at DATETIME(6),
    finished_at DATETIME(6),
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_job_retry FOREIGN KEY (retry_of_job_id) REFERENCES lesson_job(id),
    CONSTRAINT uq_job_idempotency UNIQUE (idempotency_key)
);

CREATE INDEX idx_job_created_at ON lesson_job(created_at);
CREATE INDEX idx_job_mode_status_created ON lesson_job(mode, status, created_at);
CREATE INDEX idx_job_engine_run_id ON lesson_job(engine_run_id);
CREATE INDEX idx_job_retry_of ON lesson_job(retry_of_job_id);
