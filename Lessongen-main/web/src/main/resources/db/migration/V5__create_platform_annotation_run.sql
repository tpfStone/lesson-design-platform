CREATE TABLE platform_annotation_run (
    id CHAR(26) PRIMARY KEY,
    lesson_id CHAR(26) NOT NULL,
    version_id CHAR(26) NOT NULL,
    native_run_id CHAR(32) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_platform_annotation_lesson FOREIGN KEY (lesson_id) REFERENCES platform_lesson(id),
    CONSTRAINT fk_platform_annotation_version FOREIGN KEY (version_id) REFERENCES platform_lesson_version(id),
    CONSTRAINT uq_platform_annotation_native UNIQUE (native_run_id),
    INDEX idx_platform_annotation_lesson (lesson_id, created_at)
);
