package com.zone.lesoongen.platform;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Creates a safe plain-text structure for versions that existed before migration V14. */
@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class PlatformLessonDocumentBackfill implements ApplicationRunner {
    private static final Logger log = LoggerFactory.getLogger(PlatformLessonDocumentBackfill.class);
    private final JdbcTemplate db;
    private final PlatformLessonDocumentService documents;

    public PlatformLessonDocumentBackfill(JdbcTemplate db, PlatformLessonDocumentService documents) {
        this.db = db;
        this.documents = documents;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<LegacyVersion> missing = db.query("""
                SELECT v.id, v.content
                FROM platform_lesson_version v
                LEFT JOIN platform_lesson_version_structure s ON s.version_id = v.id
                WHERE s.version_id IS NULL
                ORDER BY v.created_at ASC
                """, (rs, row) -> new LegacyVersion(rs.getString("id"), rs.getString("content")));
        for (LegacyVersion version : missing) {
            documents.save(version.id(), LessonDocumentSupport.fromPlainText(version.content()),
                    "LEGACY_FALLBACK", "PLAIN_TEXT", "1",
                    List.of("该版本创建于结构化教案上线前，已从原正文生成兼容结构。"));
        }
        if (!missing.isEmpty()) {
            log.info("backfilled structured lesson documents for {} legacy versions", missing.size());
        }
    }

    private record LegacyVersion(String id, String content) {
    }
}
