package com.zone.lesoongen.platform;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.zone.lesoongen.application.AppException;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

/** Persists the structured representation belonging to one immutable lesson version. */
@Service
public class PlatformLessonDocumentService {
    private final JdbcTemplate db;
    private final ObjectMapper mapper;

    public PlatformLessonDocumentService(JdbcTemplate db, ObjectMapper mapper) {
        this.db = db;
        this.mapper = mapper;
    }

    @Transactional
    public void save(String versionId, LessonDocument document, String parseStatus,
            String parserName, String parserVersion, List<String> warnings) {
        String documentJson = json(document);
        String warningsJson = json(warnings == null ? List.of() : warnings);
        Instant now = Instant.now().truncatedTo(ChronoUnit.MICROS);
        int updated = db.update("""
                UPDATE platform_lesson_version_structure
                SET schema_version = ?, structured_content = ?, parse_status = ?, parser_name = ?,
                    parser_version = ?, warnings = ?, updated_at = ?
                WHERE version_id = ?
                """, document.schemaVersion(), documentJson, parseStatus, parserName,
                parserVersion, warningsJson, Timestamp.from(now), versionId);
        if (updated == 0) {
            db.update("""
                    INSERT INTO platform_lesson_version_structure
                    (version_id, schema_version, structured_content, parse_status, parser_name,
                     parser_version, warnings, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, versionId, document.schemaVersion(), documentJson, parseStatus, parserName,
                    parserVersion, warningsJson, Timestamp.from(now), Timestamp.from(now));
        }
    }

    public VersionDocument get(String lessonId, String versionId) {
        List<Row> rows = db.query("""
                SELECT s.version_id, s.schema_version, s.structured_content, s.parse_status,
                       s.parser_name, s.parser_version, s.warnings, s.created_at, s.updated_at
                FROM platform_lesson_version_structure s
                JOIN platform_lesson_version v ON v.id = s.version_id
                WHERE v.lesson_id = ? AND v.id = ?
                """, (rs, row) -> mapRow(rs), lessonId, versionId);
        if (rows.isEmpty()) {
            Integer versionExists = db.queryForObject("""
                    SELECT COUNT(*) FROM platform_lesson_version WHERE lesson_id = ? AND id = ?
                    """, Integer.class, lessonId, versionId);
            if (versionExists == null || versionExists == 0) throw AppException.notFound("教案版本");
            throw new AppException(HttpStatus.NOT_FOUND, "LESSON_DOCUMENT_NOT_FOUND",
                    "该历史版本尚未生成结构化教案；可继续使用原正文，或重新解析后补齐");
        }
        Row row = rows.get(0);
        return new VersionDocument(lessonId, row.versionId(), row.schemaVersion(),
                parseDocument(row.documentJson()), row.parseStatus(), row.parserName(),
                row.parserVersion(), parseWarnings(row.warningsJson()), row.createdAt(), row.updatedAt());
    }

    private Row mapRow(ResultSet rs) throws SQLException {
        return new Row(rs.getString("version_id"), rs.getString("schema_version"),
                rs.getString("structured_content"), rs.getString("parse_status"),
                rs.getString("parser_name"), rs.getString("parser_version"),
                rs.getString("warnings"), rs.getTimestamp("created_at").toInstant(),
                rs.getTimestamp("updated_at").toInstant());
    }

    private String json(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (JacksonException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "LESSON_DOCUMENT_SERIALIZE_FAILED",
                    "结构化教案无法保存");
        }
    }

    private LessonDocument parseDocument(String value) {
        try {
            return mapper.readValue(value, LessonDocument.class);
        } catch (JacksonException error) {
            System.err.println("=== PARSE DOCUMENT FAILED ===");
            System.err.println(value);
            error.printStackTrace();
            throw corrupt();
        }
    }

    @SuppressWarnings("unchecked")
    private List<String> parseWarnings(String value) {
        try {
            return (List<String>) (List<?>) mapper.readValue(value, List.class);
        } catch (JacksonException error) {
            System.err.println("=== PARSE WARNINGS FAILED ===");
            System.err.println(value);
            error.printStackTrace();
            throw corrupt();
        }
    }

    private static AppException corrupt() {
        return new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "LESSON_DOCUMENT_CORRUPT",
                "已保存的结构化教案无法读取");
    }

    public record VersionDocument(String lessonId, String versionId, String schemaVersion,
            LessonDocument document, String parseStatus, String parserName, String parserVersion,
            List<String> warnings, Instant createdAt, Instant updatedAt) {
    }

    private record Row(String versionId, String schemaVersion, String documentJson,
            String parseStatus, String parserName, String parserVersion, String warningsJson,
            Instant createdAt, Instant updatedAt) {
    }
}
