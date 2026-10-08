CREATE TABLE platform_issue (
    id CHAR(26) PRIMARY KEY,
    lesson_id CHAR(26) NOT NULL,
    version_id CHAR(26) NOT NULL,
    source_module VARCHAR(8) NOT NULL,
    source_run_id VARCHAR(128) NOT NULL,
    source_issue_id VARCHAR(128) NOT NULL,
    category VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    severity VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
    confidence DECIMAL(5,4) NULL,
    section_ref VARCHAR(255) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_platform_issue_lesson
        FOREIGN KEY (lesson_id) REFERENCES platform_lesson(id),
    CONSTRAINT fk_platform_issue_version
        FOREIGN KEY (version_id) REFERENCES platform_lesson_version(id),
    CONSTRAINT uq_platform_issue_source
        UNIQUE (source_module, source_run_id, source_issue_id),
    CONSTRAINT chk_platform_issue_module
        CHECK (source_module IN ('F1', 'F2', 'F3', 'F4')),
    CONSTRAINT chk_platform_issue_severity
        CHECK (severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT chk_platform_issue_status
        CHECK (status IN ('OPEN', 'ACCEPTED', 'RESOLVED', 'DISMISSED')),
    CONSTRAINT chk_platform_issue_confidence
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    INDEX idx_platform_issue_version_created (lesson_id, version_id, created_at),
    INDEX idx_platform_issue_filter (lesson_id, version_id, source_module, status, severity)
);

CREATE TABLE platform_issue_evidence (
    id CHAR(26) PRIMARY KEY,
    issue_id CHAR(26) NOT NULL,
    evidence_type VARCHAR(32) NOT NULL,
    source_event_id VARCHAR(128) NULL,
    sequence_number INT NULL,
    quote_text TEXT NULL,
    section_ref VARCHAR(255) NULL,
    payload_json LONGTEXT NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_platform_issue_evidence_issue
        FOREIGN KEY (issue_id) REFERENCES platform_issue(id) ON DELETE CASCADE,
    INDEX idx_platform_issue_evidence_issue (issue_id, sequence_number, id)
);

CREATE TABLE platform_issue_recommendation (
    id CHAR(26) PRIMARY KEY,
    issue_id CHAR(26) NOT NULL,
    title VARCHAR(255) NOT NULL,
    action_text TEXT NOT NULL,
    target_module VARCHAR(8) NULL,
    priority VARCHAR(16) NOT NULL DEFAULT 'MEDIUM',
    status VARCHAR(16) NOT NULL DEFAULT 'PROPOSED',
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_platform_issue_recommendation_issue
        FOREIGN KEY (issue_id) REFERENCES platform_issue(id) ON DELETE CASCADE,
    CONSTRAINT chk_platform_recommendation_target
        CHECK (target_module IS NULL OR target_module IN ('F1', 'F2', 'F3', 'F4')),
    CONSTRAINT chk_platform_recommendation_priority
        CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH')),
    CONSTRAINT chk_platform_recommendation_status
        CHECK (status IN ('PROPOSED', 'ACCEPTED', 'APPLIED', 'DISMISSED')),
    INDEX idx_platform_issue_recommendation_issue (issue_id, priority, id)
);

CREATE TABLE platform_issue_context (
    id CHAR(26) PRIMARY KEY,
    issue_id CHAR(26) NOT NULL,
    context_type VARCHAR(32) NOT NULL,
    source_module VARCHAR(8) NULL,
    source_run_id VARCHAR(128) NULL,
    reference_id VARCHAR(255) NULL,
    label VARCHAR(255) NULL,
    payload_json LONGTEXT NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_platform_issue_context_issue
        FOREIGN KEY (issue_id) REFERENCES platform_issue(id) ON DELETE CASCADE,
    CONSTRAINT chk_platform_issue_context_module
        CHECK (source_module IS NULL OR source_module IN ('F1', 'F2', 'F3', 'F4')),
    INDEX idx_platform_issue_context_issue (issue_id, context_type, id)
);
