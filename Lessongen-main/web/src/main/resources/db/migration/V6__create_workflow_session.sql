CREATE TABLE workflow_session (
    id VARCHAR(36) PRIMARY KEY,
    lesson_id VARCHAR(36) NOT NULL,
    workflow_type VARCHAR(64) NOT NULL,
    native_session_id VARCHAR(64) NOT NULL,
    current_step VARCHAR(64),
    status VARCHAR(32) DEFAULT 'RUNNING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);