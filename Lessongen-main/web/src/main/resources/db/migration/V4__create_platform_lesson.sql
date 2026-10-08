CREATE TABLE platform_lesson (
    id CHAR(26) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    subject VARCHAR(100) NOT NULL,
    grade VARCHAR(100) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    duration_minutes SMALLINT NULL,
    current_version_id CHAR(26) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    INDEX idx_platform_lesson_updated (updated_at)
);

CREATE TABLE platform_lesson_version (
    id CHAR(26) PRIMARY KEY,
    lesson_id CHAR(26) NOT NULL,
    parent_version_id CHAR(26) NULL,
    version_number INT NOT NULL,
    content LONGTEXT NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    source_module VARCHAR(24) NOT NULL,
    native_reference VARCHAR(255) NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_platform_version_lesson FOREIGN KEY (lesson_id) REFERENCES platform_lesson(id),
    CONSTRAINT fk_platform_version_parent FOREIGN KEY (parent_version_id) REFERENCES platform_lesson_version(id),
    CONSTRAINT uq_platform_version_number UNIQUE (lesson_id, version_number),
    INDEX idx_platform_version_lesson (lesson_id, version_number)
);

ALTER TABLE platform_lesson ADD CONSTRAINT fk_platform_current_version
    FOREIGN KEY (current_version_id) REFERENCES platform_lesson_version(id);
