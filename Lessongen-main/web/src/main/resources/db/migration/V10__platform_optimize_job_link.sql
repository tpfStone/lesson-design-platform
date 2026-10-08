CREATE TABLE platform_optimize_job_link (
    job_id CHAR(26) PRIMARY KEY,
    lesson_id CHAR(26) NOT NULL,
    source_version_id CHAR(26) NOT NULL,
    saved_version_id CHAR(26) NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_optimize_lesson FOREIGN KEY (lesson_id) REFERENCES platform_lesson(id),
    CONSTRAINT fk_optimize_source FOREIGN KEY (source_version_id) REFERENCES platform_lesson_version(id),
    CONSTRAINT fk_optimize_saved FOREIGN KEY (saved_version_id) REFERENCES platform_lesson_version(id),
    INDEX idx_optimize_lesson (lesson_id, created_at)
);
