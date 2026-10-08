CREATE TABLE platform_lesson_source_document (
    lesson_id CHAR(26) PRIMARY KEY,
    version_id CHAR(26) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(150) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    storage_key VARCHAR(500) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_lesson_source_document_lesson
        FOREIGN KEY (lesson_id) REFERENCES platform_lesson(id),
    CONSTRAINT fk_lesson_source_document_version
        FOREIGN KEY (version_id) REFERENCES platform_lesson_version(id),
    CONSTRAINT uq_lesson_source_document_version UNIQUE (version_id)
);
