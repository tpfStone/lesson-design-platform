package com.zone.lesoongen.platform;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import tools.jackson.databind.ObjectMapper;
import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.domain.shared.Ulids;
import com.zone.lesoongen.platform.PlatformLessonController.CreateLesson;
import com.zone.lesoongen.platform.PlatformLessonController.LessonDetail;
import com.zone.lesoongen.platform.PlatformNavigationBridgeController.Save;

@Service
public class PlatformNavigationBridgeService {
    private final JdbcTemplate db;
    private final PlatformLessonService lessons;
    private final PlatformIssueIngestService issueIngest;
    private final PlatformIssueContextService issueContext;
    private final ObjectMapper mapper;
    private final RestClient f4;
    private final TransactionTemplate transactions;

    public PlatformNavigationBridgeService(JdbcTemplate db, PlatformLessonService lessons,
                                           PlatformIssueIngestService issueIngest,
                                           PlatformIssueContextService issueContext,
                                           ObjectMapper mapper, PlatformTransactionManager transactionManager,
                                           @Value("${platform.f4.base-url:http://127.0.0.1:8000}") String baseUrl) {
        this.db = db; this.lessons = lessons; this.issueIngest = issueIngest;
        this.issueContext = issueContext; this.mapper = mapper;
        transactions = new TransactionTemplate(transactionManager);
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(5));
        factory.setReadTimeout(Duration.ofSeconds(180));
        f4 = RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
    }

    public record Started(String sessionId, String lessonId, String sourceVersionId) {}
    public record BindingContext(String lessonId, String title, String sourceVersionId,
            Integer sourceVersionNumber, String currentVersionId, Integer currentVersionNumber,
            String currentContent) {}
    public record Saved(String lessonId, String versionId, int versionNumber, boolean alreadySaved,
            int roundNumber, String nativeStatus) {}
    public record IssueSyncResult(String sessionId, String lessonId, String versionId, int importedCount) {}
    private record Binding(String lessonId, String sourceVersionId) {}
    private record Head(String id, int number, String hash) {}
    private record Snapshot(String sessionId, String roundId, int roundNumber, String status,
            String original, String content, String hash, Map<?, ?> metadata) {}

    public Started start(String lessonId, String versionId, UUID requestKey,
            String subject, String grade, String topic) {
        LessonDetail detail = lessons.detail(lessonId);
        var version = detail.versions().stream().filter(v -> v.id().equals(versionId))
                .findFirst().orElseThrow(() -> AppException.notFound("教案版本"));
        String f4Subject = nonblank(subject, nonblank(detail.lesson().subject(), "未指定学科"));
        String f4Grade = nonblank(grade, nonblank(detail.lesson().grade(), "未指定年级"));
        String f4Topic = nonblank(topic, nonblank(detail.lesson().topic(), detail.lesson().title()));
        if (f4Subject.isBlank() || f4Grade.isBlank() || f4Topic.isBlank()
                || f4Subject.length() > 100 || f4Grade.length() > 100 || f4Topic.length() > 200) {
            throw new AppException(HttpStatus.BAD_REQUEST, "F4_METADATA_REQUIRED",
                    "无法从教案中获取有效的课题，请在“我的教案”中补充教案标题后重试。");
        }
        String additionalContext = issueContext.f4AdditionalContext(lessonId, version.id());

        Map<String, Object> metadata = new java.util.LinkedHashMap<>();
        metadata.put("subject", f4Subject);
        metadata.put("grade", f4Grade);
        metadata.put("topic", f4Topic);

        if (additionalContext != null && !additionalContext.isBlank()) {
            metadata.put("additional_context", additionalContext);
        }

        Map<?, ?> response = nativeRequest("/sessions", Map.of("request_key", requestKey.toString(),
                "metadata", metadata, "content", version.content()));
        Map<?, ?> session = object(response.get("session"));
        String sessionId = text(session.get("id"));
        try { sessionId = UUID.fromString(sessionId).toString(); }
        catch (IllegalArgumentException invalid) { throw invalidNative(); }
        final String nativeId = sessionId;
        return transactions.execute(status -> {
            lockHead(lessonId);
            Binding existing = binding(nativeId);
            if (existing == null) insertBinding(nativeId, lessonId, versionId);
            else if (!existing.lessonId().equals(lessonId) || !existing.sourceVersionId().equals(versionId)) {
                throw conflict("F4_SESSION_ALREADY_BOUND", "此会话已关联到其他教案版本，请重新开始导航分析。");
            }
            return new Started(nativeId, lessonId, versionId);
        });
    }

    private static String nonblank(String supplied, String saved) {
        if (supplied != null && !supplied.isBlank()) return supplied.trim();
        return saved == null ? "" : saved.trim();
    }

    public BindingContext context(String sessionId) {
        Binding binding = binding(sessionId);
        if (binding == null) return new BindingContext(null, null, null, null, null, null, null);
        LessonDetail detail = lessons.detail(binding.lessonId());
        var source = detail.versions().stream().filter(v -> v.id().equals(binding.sourceVersionId()))
                .findFirst().orElseThrow(() -> AppException.notFound("导航输入版本"));
        var current = detail.versions().stream().filter(v -> v.id().equals(detail.lesson().currentVersionId()))
                .findFirst().orElseThrow(() -> AppException.notFound("当前教案版本"));
        return new BindingContext(binding.lessonId(), detail.lesson().title(), source.id(), source.versionNumber(),
                current.id(), current.versionNumber(), current.content());
    }

    public Saved save(String sessionId, Save input) {
        // Fetch before the MySQL transaction: never lock a lesson while waiting on F4.
        Map<?, ?> state = nativeRequest("/sessions/" + sessionId + "/current-state", null);
        Map<?, ?> session = object(state.get("session"));
        Map<?, ?> round = object(state.get("round"));
        Map<?, ?> plan = object(state.get("lesson_plan"));
        String content = text(plan.get("current_content"));
        String original = text(plan.get("original_content"));
        if (!sessionId.equals(text(session.get("id"))) || content.isBlank() || original.isBlank()) throw invalidNative();
        if (content.length() > 100000 || original.length() > 100000) {
            throw new AppException(HttpStatus.UNPROCESSABLE_ENTITY, "LESSON_CONTENT_TOO_LONG", "教案超过十万字限制，请先导出正文并整理。");
        }
        if (!input.roundId().toString().equals(text(round.get("id"))) || !sha256(content).equals(input.expectedContentSha256())) {
            throw conflict("F4_CONTENT_CHANGED", "F4 正文或轮次已变化，请先恢复最新状态并核对，再保存。");
        }
        if (!(round.get("round_number") instanceof Number number)) throw invalidNative();
        Snapshot snapshot = new Snapshot(sessionId, text(round.get("id")), number.intValue(),
                text(session.get("status")), original, content, sha256(content), object(session.get("lesson_metadata")));
        try { return transactions.execute(status -> persist(snapshot, input.expectedVersionId())); }
        catch (DataIntegrityViolationException racingFirstImport) {
            // A simultaneous first import may win the unique session claim. Retry in a fresh transaction.
            return transactions.execute(status -> persist(snapshot, input.expectedVersionId()));
        }
    }
    public IssueSyncResult syncIssues(String sessionId) {
        Binding binding = binding(sessionId);
        if (binding == null) {
            throw AppException.notFound("F4 会话绑定");
        }
        Map<?, ?> state = nativeRequest("/sessions/" + sessionId + "/current-state", null);
        int imported = issueIngest.ingestF4(binding.lessonId(), binding.sourceVersionId(), sessionId, state);
        return new IssueSyncResult(sessionId, binding.lessonId(), binding.sourceVersionId(), imported);
    }

    private Saved persist(Snapshot state, String expectedVersionId) {
        Binding binding = binding(state.sessionId());
        boolean created = binding == null;
        if (created) {
            String topic = boundedText(state.metadata().get("topic"), 255);
            String subject = boundedText(state.metadata().get("subject"), 100);
            String grade = boundedText(state.metadata().get("grade"), 100);
            LessonDetail newLesson = lessons.create(new CreateLesson(topic, subject, grade, topic, null, state.original()));
            binding = new Binding(newLesson.lesson().id(), newLesson.lesson().currentVersionId());
            insertBinding(state.sessionId(), binding.lessonId(), binding.sourceVersionId());
        }
        Head current = lockHead(binding.lessonId());
        String destinationLesson = binding.lessonId();
        List<Saved> saved = db.query("""
                SELECT w.version_id, v.version_number, w.native_status
                FROM platform_navigation_writeback w JOIN platform_lesson_version v ON v.id = w.version_id
                WHERE w.session_id = ? AND w.round_number = ? AND w.content_sha256 = ? FOR UPDATE
                """, (rs, row) -> new Saved(destinationLesson, rs.getString("version_id"),
                        rs.getInt("version_number"), true, state.roundNumber(), rs.getString("native_status")),
                state.sessionId(), state.roundNumber(), state.hash());
        if (!saved.isEmpty()) return saved.get(0);
        if (!created && !Objects.equals(current.id(), expectedVersionId)) {
            throw conflict("LESSON_VERSION_CONFLICT", "教案空间已有新版本，请刷新关联信息、核对当前正文后重新保存。");
        }
        String versionId = current.id();
        int versionNumber = current.number();
        Instant now = Instant.now();
        if (!current.hash().equals(state.hash())) {
            versionId = Ulids.next(java.time.Clock.systemUTC());
            versionNumber++;
            String nativeReference = "f4:" + state.sessionId() + ":round:" + state.roundNumber() + ":sha256:" + state.hash();
            db.update("""
                    INSERT INTO platform_lesson_version
                    (id, lesson_id, parent_version_id, version_number, content, content_sha256, source_module, native_reference, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'F4_NAVIGATION', ?, ?)
                    """, versionId, binding.lessonId(), current.id(), versionNumber, state.content(), state.hash(), nativeReference, Timestamp.from(now));
            int updated = db.update("UPDATE platform_lesson SET current_version_id = ?, updated_at = ? WHERE id = ? AND current_version_id = ?",
                    versionId, Timestamp.from(now), binding.lessonId(), current.id());
            if (updated != 1) throw conflict("LESSON_VERSION_CONFLICT", "教案空间版本已变化，请刷新后核对。");
        }
        db.update("""
                INSERT INTO platform_navigation_writeback (session_id, round_number, content_sha256, version_id, native_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """, state.sessionId(), state.roundNumber(), state.hash(), versionId, state.status(), Timestamp.from(now));
        return new Saved(binding.lessonId(), versionId, versionNumber, false, state.roundNumber(), state.status());
    }

    private Binding binding(String sessionId) {
        List<Binding> rows = db.query("SELECT lesson_id, source_version_id FROM platform_navigation_link WHERE session_id = ?",
                (rs, row) -> new Binding(rs.getString("lesson_id"), rs.getString("source_version_id")), sessionId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private void insertBinding(String sessionId, String lessonId, String versionId) {
        db.update("INSERT INTO platform_navigation_link (session_id, lesson_id, source_version_id, created_at) VALUES (?, ?, ?, ?)",
                sessionId, lessonId, versionId, Timestamp.from(Instant.now()));
    }

    private Head lockHead(String lessonId) {
        List<Head> rows = db.query("""
                SELECT v.id, v.version_number, v.content_sha256 FROM platform_lesson l
                JOIN platform_lesson_version v ON v.id = l.current_version_id WHERE l.id = ? FOR UPDATE
                """, (rs, row) -> new Head(rs.getString("id"), rs.getInt("version_number"), rs.getString("content_sha256")), lessonId);
        if (rows.isEmpty()) throw AppException.notFound("教案");
        return rows.get(0);
    }

    private Map<?, ?> nativeRequest(String suffix, Map<?, ?> body) {
        try {
            Map<?, ?> result;
            if (body == null) result = f4.get().uri("/api" + suffix).retrieve().body(Map.class);
            else {
                byte[] bytes = mapper.writeValueAsBytes(body);
                result = f4.post().uri("/api" + suffix).contentType(MediaType.APPLICATION_JSON)
                        .contentLength(bytes.length).body(bytes).retrieve().body(Map.class);
            }
            if (result == null) throw invalidNative();
            return result;
        } catch (RestClientResponseException error) {
            String detail = "F4 导航服务返回错误，请恢复状态后重试。";
            try {
                Map<?, ?> data = mapper.readValue(error.getResponseBodyAsByteArray(), Map.class);
                if (data.get("detail") instanceof String value) detail = value;
            } catch (RuntimeException ignored) { }
            HttpStatus status = HttpStatus.resolve(error.getStatusCode().value());
            throw new AppException(status == null ? HttpStatus.BAD_GATEWAY : status, "F4_REQUEST_FAILED", detail);
        } catch (RestClientException error) {
            throw new AppException(HttpStatus.SERVICE_UNAVAILABLE, "F4_CONNECTION_FAILED", "F4 导航服务连接失败，请检查 8000 服务。");
        }
    }

    private static String text(Object value) { return value instanceof String s ? s : ""; }
    private static Map<?, ?> object(Object value) { if (value instanceof Map<?, ?> m) return m; throw invalidNative(); }
    private static String boundedText(Object value, int max) {
        String text = text(value).trim();
        if (text.isEmpty() || text.length() > max) throw invalidNative();
        return text;
    }
    private static String sha256(String content) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    private static AppException invalidNative() { return new AppException(HttpStatus.BAD_GATEWAY, "F4_INVALID_STATE", "F4 返回的教案状态不完整，请恢复最新状态。"); }
    private static AppException conflict(String code, String detail) { return new AppException(HttpStatus.CONFLICT, code, detail); }
}
