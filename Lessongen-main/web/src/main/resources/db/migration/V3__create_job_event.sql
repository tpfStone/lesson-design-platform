CREATE TABLE lesson_job_event (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id CHAR(26) NOT NULL,
    sequence_no BIGINT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    stage VARCHAR(64) NOT NULL,
    round_index SMALLINT,
    version_id VARCHAR(64),
    progress_percent TINYINT NOT NULL,
    message VARCHAR(500) NOT NULL,
    event_payload JSON,
    engine_event_key VARCHAR(128),
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_event_job FOREIGN KEY (job_id) REFERENCES lesson_job(id),
    CONSTRAINT uq_event_sequence UNIQUE (job_id, sequence_no),
    CONSTRAINT uq_event_engine_key UNIQUE (job_id, engine_event_key)
);

CREATE INDEX idx_event_job_created ON lesson_job_event(job_id, created_at);
