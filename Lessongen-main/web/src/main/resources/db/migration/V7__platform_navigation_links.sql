CREATE TABLE platform_navigation_link (
    session_id CHAR(36) PRIMARY KEY,
    lesson_id CHAR(26) NOT NULL,
    source_version_id CHAR(26) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_navigation_link_lesson FOREIGN KEY (lesson_id) REFERENCES platform_lesson(id),
    CONSTRAINT fk_navigation_link_source FOREIGN KEY (source_version_id) REFERENCES platform_lesson_version(id)
);

CREATE TABLE platform_navigation_writeback (
    session_id CHAR(36) NOT NULL,
    round_number INT NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    version_id CHAR(26) NOT NULL,
    native_status VARCHAR(24) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (session_id, round_number, content_sha256),
    CONSTRAINT fk_navigation_writeback_session FOREIGN KEY (session_id) REFERENCES platform_navigation_link(session_id),
    CONSTRAINT fk_navigation_writeback_version FOREIGN KEY (version_id) REFERENCES platform_lesson_version(id)
);
