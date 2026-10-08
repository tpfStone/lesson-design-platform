package com.zone.lesoongen.platform;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.domain.shared.Ulids;
import com.zone.lesoongen.platform.PlatformLessonController.CreateLesson;
import com.zone.lesoongen.platform.PlatformLessonController.LessonDetail;
import com.zone.lesoongen.platform.PlatformLessonController.LessonSummary;
import com.zone.lesoongen.platform.PlatformLessonController.LessonVersion;
import com.zone.lesoongen.platform.PlatformLessonController.NewVersion;

@Service
public class PlatformLessonService {
    private final JdbcTemplate db;
    private final PlatformLessonDocumentService documents;

    public PlatformLessonService(JdbcTemplate db, PlatformLessonDocumentService documents) {
        this.db = db;
        this.documents = documents;
    }

    @Transactional
    public LessonDetail create(CreateLesson request) {
        return createInitialVersion(request, "IMPORT_TEXT",
                LessonDocumentSupport.fromPlainText(request.content()), "FALLBACK",
                "PLAIN_TEXT", List.of());
    }

    @Transactional
    public LessonDetail createDocx(CreateLesson request) {
        return createInitialVersion(request, "IMPORT_DOCX",
                LessonDocumentSupport.fromPlainText(request.content()), "FALLBACK",
                "PLAIN_TEXT", List.of("未提供 DOCX 结构，已按确认正文生成兼容结构。"));
    }

    @Transactional
    public LessonDetail createDocx(CreateLesson request, LessonDocument document,
            String parseStatus, List<String> warnings) {
        return createInitialVersion(request, "IMPORT_DOCX", document, parseStatus,
                "APACHE_POI_DOCX", warnings);
    }

    private LessonDetail createInitialVersion(CreateLesson request, String sourceModule,
            LessonDocument document, String parseStatus, String parserName, List<String> warnings) {
        Instant now = Instant.now().truncatedTo(ChronoUnit.MICROS);
        String lessonId = Ulids.next(java.time.Clock.systemUTC());
        String versionId = Ulids.next(java.time.Clock.systemUTC());
        db.update("""
                INSERT INTO platform_lesson
                (id, title, subject, grade, topic, duration_minutes, current_version_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """, lessonId, request.title().trim(), request.subject().trim(), request.grade().trim(),
                request.topic().trim(), request.durationMinutes(), Timestamp.from(now), Timestamp.from(now));
        insertVersion(versionId, lessonId, null, 0, request.content(), sourceModule, now);
        documents.save(versionId, document, parseStatus, parserName, "1", warnings);
        db.update("UPDATE platform_lesson SET current_version_id = ? WHERE id = ?", versionId, lessonId);
        return detail(lessonId);
    }

    public List<LessonSummary> list() {
        return db.query("""
                SELECT id, title, subject, grade, topic, duration_minutes, current_version_id, updated_at
                FROM platform_lesson ORDER BY updated_at DESC, id DESC LIMIT 100
                """, (rs, row) -> summary(rs));
    }

    public LessonDetail detail(String lessonId) {
        List<LessonSummary> matches = db.query("""
                SELECT id, title, subject, grade, topic, duration_minutes, current_version_id, updated_at
                FROM platform_lesson WHERE id = ?
                """, (rs, row) -> summary(rs), lessonId);
        if (matches.isEmpty()) {
            throw AppException.notFound("教案");
        }
        List<LessonVersion> versions = db.query("""
                SELECT id, lesson_id, parent_version_id, version_number, content,
                       content_sha256, source_module, native_reference, created_at
                FROM platform_lesson_version WHERE lesson_id = ? ORDER BY version_number ASC
                """, (rs, row) -> version(rs), lessonId);
        return new LessonDetail(matches.get(0), versions);
    }

    @Transactional
    public LessonDetail addVersion(String lessonId, NewVersion request) {
        return addVersionFromModule(lessonId, request.expectedVersionId(), request.content(), "MANUAL", null);
    }

    @Transactional
    public LessonDetail addVersionFromModule(String lessonId, String expectedVersionId,
            String content, String sourceModule, String nativeReference) {
        LessonDetail before = detail(lessonId);
        String current = before.lesson().currentVersionId();
        if (!Objects.equals(current, expectedVersionId)) {
            throw new AppException(HttpStatus.CONFLICT, "LESSON_VERSION_CONFLICT",
                    "教案已被修改，请刷新后重新确认当前版本");
        }
        int next = before.versions().stream().mapToInt(LessonVersion::versionNumber).max().orElse(-1) + 1;
        String versionId = Ulids.next(java.time.Clock.systemUTC());
        Instant now = Instant.now().truncatedTo(ChronoUnit.MICROS);
        insertVersion(versionId, lessonId, current, next, content, sourceModule, nativeReference, now);
        documents.save(versionId, LessonDocumentSupport.fromPlainText(content), "FALLBACK",
                "PLAIN_TEXT", "1", List.of("该版本由纯正文生成兼容结构；复杂表格可能需要重新解析。"));
        int changed = db.update("""
                UPDATE platform_lesson SET current_version_id = ?, updated_at = ?
                WHERE id = ? AND current_version_id = ?
                """, versionId, Timestamp.from(now), lessonId, current);
        if (changed != 1) {
            throw new AppException(HttpStatus.CONFLICT, "LESSON_VERSION_CONFLICT",
                    "教案已被修改，请刷新后重新确认当前版本");
        }
        return detail(lessonId);
    }

    private void insertVersion(String versionId, String lessonId, String parentId,
            int number, String content, String source, Instant now) {
        insertVersion(versionId, lessonId, parentId, number, content, source, null, now);
    }

    private void insertVersion(String versionId, String lessonId, String parentId,
            int number, String content, String source, String nativeReference, Instant now) {
        db.update("""
                INSERT INTO platform_lesson_version
                (id, lesson_id, parent_version_id, version_number, content,
                 content_sha256, source_module, native_reference, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, versionId, lessonId, parentId, number, content, sha256(content),
                source, nativeReference, Timestamp.from(now));
    }

    private static String sha256(String content) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(content.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private static LessonSummary summary(ResultSet rs) throws SQLException {
        int duration = rs.getInt("duration_minutes");
        Integer minutes = rs.wasNull() ? null : duration;
        return new LessonSummary(rs.getString("id"), rs.getString("title"),
                rs.getString("subject"), rs.getString("grade"), rs.getString("topic"),
                minutes, rs.getString("current_version_id"),
                rs.getTimestamp("updated_at").toInstant());
    }

    private static LessonVersion version(ResultSet rs) throws SQLException {
        return new LessonVersion(rs.getString("id"), rs.getString("lesson_id"),
                rs.getString("parent_version_id"), rs.getInt("version_number"),
                rs.getString("content"), rs.getString("content_sha256"),
                rs.getString("source_module"), rs.getString("native_reference"),
                rs.getTimestamp("created_at").toInstant());
    }
}
