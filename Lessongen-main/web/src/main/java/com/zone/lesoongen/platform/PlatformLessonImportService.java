package com.zone.lesoongen.platform;

import java.io.IOException;
import java.io.InputStream;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;

import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.application.storage.StoragePort;
import com.zone.lesoongen.application.storage.StoredObject;
import com.zone.lesoongen.config.AppProperties;
import com.zone.lesoongen.platform.DocxLessonExtractor.ExtractedDocument;
import com.zone.lesoongen.platform.PlatformLessonController.CreateLesson;
import com.zone.lesoongen.platform.PlatformLessonController.LessonDetail;

@Service
public class PlatformLessonImportService {
    private static final Logger log = LoggerFactory.getLogger(PlatformLessonImportService.class);
    private static final String DOCX_MEDIA =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

    private final PlatformLessonService lessons;
    private final DocxLessonExtractor extractor;
    private final StoragePort storage;
    private final AppProperties properties;
    private final JdbcTemplate db;
    private final Clock clock;

    public PlatformLessonImportService(PlatformLessonService lessons, DocxLessonExtractor extractor,
            StoragePort storage, AppProperties properties, JdbcTemplate db, Clock clock) {
        this.lessons = lessons;
        this.extractor = extractor;
        this.storage = storage;
        this.properties = properties;
        this.db = db;
        this.clock = clock;
    }

    public DocxPreview preview(MultipartFile file) {
        ExtractedDocument extracted = extractor.extract(file, properties.maxUploadBytes());
        return new DocxPreview(extracted.originalFilename(), extracted.sizeBytes(),
                extracted.extractedContent(), extracted.extractedContent().length(),
                extracted.structuredContent(), extracted.warnings());
    }

    @Transactional
    public LessonDetail importDocx(MultipartFile file, CreateLesson request) {
        // Re-parse at confirmation time: preview is intentionally stateless and cannot be trusted as persistence input.
        ExtractedDocument extracted = extractor.extract(file, properties.maxUploadBytes());
        CreateLesson normalized = normalizeDocxRequest(extracted, request);
        validateConfirmedLesson(normalized);

        boolean contentUnchanged = request == null || blank(request.content())
                || request.content().equals(extracted.extractedContent());
        LessonDocument document = contentUnchanged
                ? extracted.structuredContent()
                : LessonDocumentSupport.fromPlainText(normalized.content());
        List<String> structureWarnings = new ArrayList<>(extracted.warnings());
        String parseStatus = "PARSED";
        if (!contentUnchanged) {
            parseStatus = "EDITED_FALLBACK";
            structureWarnings.add("确认保存前正文已被编辑，结构已按确认后的正文重新生成；原始 DOCX 仍单独保留。");
        }
        LessonDetail created = lessons.createDocx(normalized, document, parseStatus,
                List.copyOf(structureWarnings));
        String lessonId = created.lesson().id();
        String versionId = created.lesson().currentVersionId();
        String storageKey = "lessons/" + lessonId + "/source/original.docx";
        StoredObject stored;
        try (InputStream stream = file.getInputStream()) {
            stored = storage.store(storageKey, stream, properties.maxUploadBytes());
        } catch (IOException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "FILE_STORAGE_FAILED",
                    "无法安全保存上传的 Word 原稿");
        }
        registerRollbackCleanup(storageKey);

        Instant now = clock.instant().truncatedTo(ChronoUnit.MICROS);
        String contentType = normalizedContentType(file.getContentType());
        int changed = db.update("""
                INSERT INTO platform_lesson_source_document
                (lesson_id, version_id, original_filename, content_type, size_bytes,
                 sha256, storage_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, lessonId, versionId, extracted.originalFilename(), contentType,
                stored.sizeBytes(), stored.sha256(), stored.storageKey(), Timestamp.from(now));
        if (changed != 1) {
            throw new IllegalStateException("source document metadata insert did not create one row");
        }
        return lessons.detail(lessonId);
    }

    public SourceDocumentMetadata sourceDocument(String lessonId) {
        lessons.detail(lessonId); // Distinguish missing lesson from lesson-without-original-file.
        List<SourceDocumentRow> rows = db.query("""
                SELECT lesson_id, version_id, original_filename, content_type,
                       size_bytes, sha256, storage_key, created_at
                FROM platform_lesson_source_document WHERE lesson_id = ?
                """, (rs, row) -> sourceRow(rs), lessonId);
        if (rows.isEmpty()) {
            throw new AppException(HttpStatus.NOT_FOUND, "SOURCE_DOCUMENT_NOT_FOUND",
                    "该教案没有 DOCX 原稿；手工粘贴创建的教案仍可正常使用");
        }
        SourceDocumentRow row = rows.get(0);
        return new SourceDocumentMetadata(row.lessonId(), row.versionId(), row.originalFilename(),
                row.contentType(), row.sizeBytes(), row.sha256(), row.createdAt());
    }

    public SourceDocumentDownload sourceDocumentFile(String lessonId) {
        lessons.detail(lessonId);
        List<SourceDocumentRow> rows = db.query("""
                SELECT lesson_id, version_id, original_filename, content_type,
                       size_bytes, sha256, storage_key, created_at
                FROM platform_lesson_source_document WHERE lesson_id = ?
                """, (rs, row) -> sourceRow(rs), lessonId);
        if (rows.isEmpty()) {
            throw new AppException(HttpStatus.NOT_FOUND, "SOURCE_DOCUMENT_NOT_FOUND",
                    "该教案没有可下载的 DOCX 原稿");
        }
        SourceDocumentRow row = rows.get(0);
        if (!storage.exists(row.storageKey())) {
            throw new AppException(HttpStatus.NOT_FOUND, "SOURCE_DOCUMENT_FILE_NOT_FOUND",
                    "DOCX 原稿记录存在，但文件当前不可用");
        }
        try {
            return new SourceDocumentDownload(row.originalFilename(), row.contentType(), row.sizeBytes(),
                    row.sha256(), storage.open(row.storageKey()));
        } catch (IOException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "FILE_STORAGE_READ_FAILED",
                    "无法读取 DOCX 原稿文件");
        }
    }

    private void registerRollbackCleanup(String storageKey) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                if (status != TransactionSynchronization.STATUS_ROLLED_BACK) {
                    return;
                }
                try {
                    storage.delete(storageKey);
                } catch (IOException | RuntimeException cleanupError) {
                    log.warn("failed to clean rolled-back DOCX storage key={}", storageKey, cleanupError);
                }
            }
        });
    }

    private static CreateLesson normalizeDocxRequest(ExtractedDocument extracted, CreateLesson request) {
        String baseName = extracted.originalFilename().replaceFirst("(?i)\\.docx$", "").trim();
        String title = request == null || blank(request.title()) ? baseName : request.title().trim();
        String subject = request == null || request.subject() == null ? "" : request.subject().trim();
        String grade = request == null || request.grade() == null ? "" : request.grade().trim();
        String topic = request == null || blank(request.topic()) ? title : request.topic().trim();
        Integer duration = request == null ? null : request.durationMinutes();
        String content = request == null || blank(request.content())
                ? extracted.extractedContent() : request.content();
        return new CreateLesson(title, subject, grade, topic, duration, content);
    }

    private static void validateConfirmedLesson(CreateLesson request) {
        if (request == null || blank(request.title()) || blank(request.content())) {
            throw new AppException(HttpStatus.UNPROCESSABLE_ENTITY, "VALIDATION_FAILED",
                    "教案标题和正文不能为空");
        }
        if (request.title().length() > 255 || request.subject().length() > 100
                || request.grade().length() > 100 || request.topic().length() > 255
                || request.content().length() > DocxLessonExtractor.MAX_CONTENT_CHARS) {
            throw new AppException(HttpStatus.UNPROCESSABLE_ENTITY, "VALIDATION_FAILED",
                    "教案字段长度超过允许范围");
        }
        if (request.durationMinutes() != null
                && (request.durationMinutes() < 5 || request.durationMinutes() > 240)) {
            throw new AppException(HttpStatus.UNPROCESSABLE_ENTITY, "VALIDATION_FAILED",
                    "课时长度必须在 5–240 分钟之间");
        }
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }

    private static String normalizedContentType(String value) {
        if (value == null || value.isBlank() || value.length() > 150) {
            return DOCX_MEDIA;
        }
        return value;
    }

    private static SourceDocumentRow sourceRow(ResultSet rs) throws SQLException {
        return new SourceDocumentRow(rs.getString("lesson_id"), rs.getString("version_id"),
                rs.getString("original_filename"), rs.getString("content_type"),
                rs.getLong("size_bytes"), rs.getString("sha256"), rs.getString("storage_key"),
                rs.getTimestamp("created_at").toInstant());
    }

    public record DocxPreview(String originalFilename, long sizeBytes, String extractedContent,
            int contentLength, LessonDocument structuredContent, List<String> warnings) {
    }

    public record SourceDocumentMetadata(String lessonId, String versionId, String originalFilename,
            String contentType, long sizeBytes, String sha256, Instant createdAt) {
    }

    public record SourceDocumentDownload(String originalFilename, String contentType, long sizeBytes,
            String sha256, InputStream stream) {
    }

    private record SourceDocumentRow(String lessonId, String versionId, String originalFilename,
            String contentType, long sizeBytes, String sha256, String storageKey, Instant createdAt) {
    }
}
