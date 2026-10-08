CREATE TABLE platform_lesson_version_structure (
    version_id CHAR(26) PRIMARY KEY,
    schema_version VARCHAR(16) NOT NULL,
    structured_content CLOB NOT NULL,
    parse_status VARCHAR(24) NOT NULL,
    parser_name VARCHAR(64) NOT NULL,
    parser_version VARCHAR(32) NOT NULL,
    warnings CLOB NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_platform_version_structure_version
        FOREIGN KEY (version_id) REFERENCES platform_lesson_version(id)
);