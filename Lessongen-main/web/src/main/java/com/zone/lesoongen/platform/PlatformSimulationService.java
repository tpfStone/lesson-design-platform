package com.zone.lesoongen.platform;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.domain.shared.Ulids;
import com.zone.lesoongen.platform.PlatformLessonController.LessonDetail;
import com.zone.lesoongen.platform.PlatformLessonController.LessonVersion;
import com.zone.lesoongen.platform.PlatformSimulationController.SaveSimulationRequest;
import com.zone.lesoongen.platform.PlatformSimulationController.SaveSimulationResponse;
import com.zone.lesoongen.platform.PlatformSimulationController.SimulationDetail;
import com.zone.lesoongen.platform.PlatformSimulationController.SimulationSummary;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Service
public class PlatformSimulationService {
    private static final int MAX_RESULT_BYTES = 5 * 1024 * 1024;
    private static final int MAX_SUMMARY_BYTES = 200 * 1024;

    private final JdbcTemplate db;
    private final PlatformLessonService lessons;
    private final ObjectMapper mapper;
    private final PlatformIssueIngestService issueIngest;

    public PlatformSimulationService(JdbcTemplate db, PlatformLessonService lessons,
            ObjectMapper mapper, PlatformIssueIngestService issueIngest) {
        this.db = db;
        this.lessons = lessons;
        this.mapper = mapper;
        this.issueIngest = issueIngest;
    }

    private record Validated(
            String lessonId,
            String versionId,
            int versionNumber,
            String f4SessionId,
            String f4LessonPlanId,
            String f3SessionId,
            String status,
            int requestedRounds,
            int completedRounds,
            int materialCount,
            String finalClassroomStatus,
            int historyCount,
            String httpChain,
            String f4Provider,
            String f3ModelContent,
            String resultJson,
            String resultSha256,
            String summaryMarkdown,
            Instant startedAt,
            Instant finishedAt) {}

    private record Stored(
            String id,
            String lessonId,
            String versionId,
            int versionNumber,
            String f4SessionId,
            String f4LessonPlanId,
            String f3SessionId,
            String status,
            int requestedRounds,
            int completedRounds,
            int materialCount,
            String finalClassroomStatus,
            int historyCount,
            String httpChain,
            String f4Provider,
            String f3ModelContent,
            String resultJson,
            String resultSha256,
            String summaryMarkdown,
            Instant startedAt,
            Instant finishedAt,
            Instant createdAt) {}

    @Transactional
    public SaveSimulationResponse save(String lessonId, SaveSimulationRequest request) {
        Map<String, Object> record = request.sessionRecord();
        Validated value = validate(lessonId, request);
        Stored existing = findByF3Session(value.f3SessionId());
        if (existing != null) {
            if (!existing.resultSha256().equals(value.resultSha256())) {
                throw new AppException(HttpStatus.CONFLICT, "SIMULATION_RESULT_CONFLICT",
                        "同一 F3 session 已保存不同内容，禁止覆盖原模拟结果");
            }
            issueIngest.ingestF3(existing.lessonId(), existing.versionId(), existing.id(),
                    existing.f3SessionId(), record);
            return saveResponse(existing, true);
        }

        String id = Ulids.next(java.time.Clock.systemUTC());
        Instant createdAt = Instant.now().truncatedTo(ChronoUnit.MICROS);
        db.update("""
                INSERT INTO platform_simulation_run
                (id, lesson_id, version_id, f4_session_id, f4_lesson_plan_id, f3_session_id,
                 status, requested_rounds, completed_rounds, material_count,
                 final_classroom_status, history_count, http_chain, f4_provider,
                 f3_model_content, result_json, result_sha256, summary_markdown,
                 started_at, finished_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                id, value.lessonId(), value.versionId(), value.f4SessionId(), value.f4LessonPlanId(),
                value.f3SessionId(), value.status(), value.requestedRounds(), value.completedRounds(),
                value.materialCount(), value.finalClassroomStatus(), value.historyCount(), value.httpChain(),
                value.f4Provider(), value.f3ModelContent(), value.resultJson(), value.resultSha256(),
                value.summaryMarkdown(), Timestamp.from(value.startedAt()), Timestamp.from(value.finishedAt()),
                Timestamp.from(createdAt));
        issueIngest.ingestF3(value.lessonId(), value.versionId(), id, value.f3SessionId(), record);
        return new SaveSimulationResponse(id, value.lessonId(), value.versionId(), value.f3SessionId(),
                value.status(), value.completedRounds(), false, createdAt);
    }

    public List<SimulationSummary> list(String lessonId) {
        lessons.detail(lessonId);
        return db.query("""
                SELECT r.id, r.lesson_id, r.version_id, v.version_number, r.f3_session_id,
                       r.status, r.completed_rounds, r.material_count, r.final_classroom_status,
                       r.history_count, r.f3_model_content, r.started_at, r.finished_at, r.created_at
                FROM platform_simulation_run r
                JOIN platform_lesson_version v ON v.id = r.version_id
                WHERE r.lesson_id = ?
                ORDER BY r.created_at DESC, r.id DESC LIMIT 50
                """, (rs, row) -> summary(rs), lessonId);
    }

    public SimulationDetail detail(String lessonId, String simulationRunId) {
        Stored stored = find(lessonId, simulationRunId);
        return new SimulationDetail(stored.id(), stored.lessonId(), stored.versionId(), stored.versionNumber(),
                stored.f4SessionId(), stored.f4LessonPlanId(), stored.f3SessionId(), stored.status(),
                stored.requestedRounds(), stored.completedRounds(), stored.materialCount(),
                stored.finalClassroomStatus(), stored.historyCount(), stored.httpChain(), stored.f4Provider(),
                stored.f3ModelContent(), stored.startedAt(), stored.finishedAt(), stored.createdAt(),
                parseJson(stored.resultJson()), stored.summaryMarkdown());
    }

    public String jsonArtifact(String lessonId, String simulationRunId) {
        return find(lessonId, simulationRunId).resultJson();
    }

    public String markdownArtifact(String lessonId, String simulationRunId) {
        return find(lessonId, simulationRunId).summaryMarkdown();
    }

    private Validated validate(String lessonId, SaveSimulationRequest request) {
        Map<String, Object> record = request.sessionRecord();
        if (record == null || record.isEmpty()) {
            throw bad("SIMULATION_RECORD_REQUIRED", "sessionRecord 不能为空");
        }

        boolean dynamicF3 = isDynamicF3(record);
        Map<?, ?> session = dynamicF3 ? map(record, "session") : Map.of();

        String recordLessonId = dynamicF3 ? text(session, "lessonId") : text(record, "lessonId");
        if (!lessonId.equals(recordLessonId)) {
            throw bad("SIMULATION_LESSON_MISMATCH", "URL lessonId 与 sessionRecord.lessonId 不一致");
        }

        LessonDetail detail = lessons.detail(lessonId);
        String versionId = dynamicF3 ? text(session, "versionId") : text(record, "versionId");
        LessonVersion version = detail.versions().stream().filter(item -> item.id().equals(versionId))
                .findFirst().orElseThrow(() -> AppException.notFound("教案版本"));

        String f4SessionId;
        String f4LessonPlanId;
        String f3SessionId;
        String status;
        int requestedRounds;
        int completedRounds;
        int materialCount;
        String finalClassroomStatus;
        int historyCount;
        String httpChain;
        String f4Provider;
        String f3ModelContent;
        Instant startedAt;
        Instant finishedAt;

        if (dynamicF3) {
            f4SessionId = optionalUuid(record, "f4SessionId");
            f4LessonPlanId = optionalUuid(record, "f4LessonPlanId");
            f3SessionId = uuid(session, "sessionId");
            status = bounded(text(session, "status"), 24, "session.status");

            requestedRounds = 0;
            completedRounds = 0;

            List<?> events = list(record, "events");
            List<?> materials = list(session, "materials");
            materialCount = materials.size();

            String stopReason = optionalText(session.get("stopReason"));
            finalClassroomStatus = stopReason == null
                    ? status
                    : bounded(stopReason, 24, "session.stopReason");

            historyCount = events.size();

            Map<?, ?> boundary = optionalMap(record, "executionBoundary");
            httpChain = bounded(optionalText(boundary.get("httpChain"), "REAL"),
                    16, "executionBoundary.httpChain");
            f4Provider = bounded(optionalText(boundary.get("f4Provider"), "NONE"),
                    24, "executionBoundary.f4Provider");
            f3ModelContent = bounded(optionalText(boundary.get("f3ModelContent"), text(session, "modelMode")),
                    24, "executionBoundary.f3ModelContent");

            startedAt = instant(text(session, "startedAt"), "session.startedAt");
            finishedAt = instant(text(session, "finishedAt"), "session.finishedAt");
        } else {
            f4SessionId = uuid(record, "f4SessionId");
            f4LessonPlanId = uuid(record, "f4LessonPlanId");
            f3SessionId = uuid(record, "f3SessionId");
            status = bounded(text(record, "status"), 24, "status");

            requestedRounds = number(record, "requestedRounds");
            completedRounds = number(record, "completedRounds");
            materialCount = number(record, "materialCount");

            if (requestedRounds < 0 || completedRounds < 0 || completedRounds > requestedRounds) {
                throw bad("SIMULATION_ROUND_COUNT_INVALID", "completedRounds 不得大于 requestedRounds");
            }

            List<?> rounds = list(record, "rounds");
            if (rounds.size() != completedRounds) {
                throw bad("SIMULATION_ROUND_COUNT_MISMATCH", "rounds 数量必须等于 completedRounds");
            }

            List<?> materials = list(record, "materials");
            if (materials.size() != materialCount) {
                throw bad("SIMULATION_MATERIAL_COUNT_MISMATCH", "materialCount 必须等于 materials 数量");
            }

            Map<?, ?> finalState = map(record, "finalState");
            List<?> history = list(finalState, "history");
            finalClassroomStatus = optionalText(finalState.get("status"));
            if (finalClassroomStatus != null) {
                finalClassroomStatus = bounded(finalClassroomStatus, 24, "finalState.status");
            }
            historyCount = history.size();

            Map<?, ?> boundary = map(record, "executionBoundary");
            httpChain = bounded(text(boundary, "httpChain"), 16, "executionBoundary.httpChain");
            f4Provider = bounded(text(boundary, "f4Provider"), 24, "executionBoundary.f4Provider");
            f3ModelContent = bounded(text(boundary, "f3ModelContent"), 24, "executionBoundary.f3ModelContent");

            startedAt = instant(text(record, "startedAt"), "startedAt");
            finishedAt = instant(text(record, "finishedAt"), "finishedAt");
        }

        if (finishedAt.isBefore(startedAt)) {
            throw bad("SIMULATION_TIME_INVALID", "finishedAt 不能早于 startedAt");
        }

        String summary = request.summaryMarkdown();
        if (summary == null || summary.isBlank()) {
            throw bad("SIMULATION_SUMMARY_REQUIRED", "summaryMarkdown 不能为空");
        }
        if (summary.getBytes(StandardCharsets.UTF_8).length > MAX_SUMMARY_BYTES) {
            throw new AppException(HttpStatus.PAYLOAD_TOO_LARGE, "SIMULATION_SUMMARY_TOO_LARGE",
                    "summaryMarkdown 超过 200 KB 限制");
        }

        String resultJson = serializeCanonical(record);
        return new Validated(
                lessonId,
                version.id(),
                version.versionNumber(),
                f4SessionId,
                f4LessonPlanId,
                f3SessionId,
                status,
                requestedRounds,
                completedRounds,
                materialCount,
                finalClassroomStatus,
                historyCount,
                httpChain,
                f4Provider,
                f3ModelContent,
                resultJson,
                sha256(resultJson),
                summary,
                startedAt,
                finishedAt
        );
    }

    private Stored find(String lessonId, String simulationRunId) {
        lessons.detail(lessonId);
        return db.query("""
                SELECT r.*, v.version_number
                FROM platform_simulation_run r
                JOIN platform_lesson_version v ON v.id = r.version_id
                WHERE r.lesson_id = ? AND r.id = ?
                """, (rs, row) -> stored(rs), lessonId, simulationRunId)
                .stream().findFirst().orElseThrow(() -> AppException.notFound("课堂模拟记录"));
    }

    private Stored findByF3Session(String f3SessionId) {
        return db.query("""
                SELECT r.*, v.version_number
                FROM platform_simulation_run r
                JOIN platform_lesson_version v ON v.id = r.version_id
                WHERE r.f3_session_id = ?
                """, (rs, row) -> stored(rs), f3SessionId)
                .stream().findFirst().orElse(null);
    }

    private static SaveSimulationResponse saveResponse(Stored stored, boolean alreadySaved) {
        return new SaveSimulationResponse(stored.id(), stored.lessonId(), stored.versionId(),
                stored.f3SessionId(), stored.status(), stored.completedRounds(), alreadySaved, stored.createdAt());
    }

    private static SimulationSummary summary(ResultSet rs) throws SQLException {
        return new SimulationSummary(rs.getString("id"), rs.getString("lesson_id"), rs.getString("version_id"),
                rs.getInt("version_number"), rs.getString("f3_session_id"), rs.getString("status"),
                rs.getInt("completed_rounds"), rs.getInt("material_count"),
                rs.getString("final_classroom_status"), rs.getInt("history_count"),
                rs.getString("f3_model_content"), rs.getTimestamp("started_at").toInstant(),
                rs.getTimestamp("finished_at").toInstant(), rs.getTimestamp("created_at").toInstant());
    }

    private static Stored stored(ResultSet rs) throws SQLException {
        return new Stored(rs.getString("id"), rs.getString("lesson_id"), rs.getString("version_id"),
                rs.getInt("version_number"), rs.getString("f4_session_id"), rs.getString("f4_lesson_plan_id"),
                rs.getString("f3_session_id"), rs.getString("status"), rs.getInt("requested_rounds"),
                rs.getInt("completed_rounds"), rs.getInt("material_count"),
                rs.getString("final_classroom_status"), rs.getInt("history_count"), rs.getString("http_chain"),
                rs.getString("f4_provider"), rs.getString("f3_model_content"), rs.getString("result_json"),
                rs.getString("result_sha256"), rs.getString("summary_markdown"),
                rs.getTimestamp("started_at").toInstant(), rs.getTimestamp("finished_at").toInstant(),
                rs.getTimestamp("created_at").toInstant());
    }

    private Map<?, ?> parseJson(String json) {
        try {
            return mapper.readValue(json, Map.class);
        } catch (JacksonException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "SIMULATION_RESULT_CORRUPT",
                    "已保存的课堂模拟结果无法读取");
        }
    }

    private String serializeCanonical(Map<String, Object> record) {
        try {
            return mapper.writeValueAsString(canonical(record));
        } catch (JacksonException error) {
            throw bad("SIMULATION_RESULT_INVALID", "sessionRecord 无法序列化为 JSON");
        }
    }

    private static Object canonical(Object value) {
        if (value instanceof Map<?, ?> source) {
            Map<String, Object> sorted = new TreeMap<>();
            source.forEach((key, item) -> sorted.put(String.valueOf(key), canonical(item)));
            return sorted;
        }
        if (value instanceof List<?> source) {
            List<Object> result = new ArrayList<>(source.size());
            source.forEach(item -> result.add(canonical(item)));
            return result;
        }
        return value;
    }

    private static String sha256(String content) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(content.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 unavailable", impossible);
        }
    }

    private static String text(Map<?, ?> map, String key) {
        String value = optionalText(map.get(key));
        if (value == null || value.isBlank()) throw bad("SIMULATION_FIELD_REQUIRED", key + " 必须为非空字符串");
        return value.trim();
    }

    private static String optionalText(Object value) {
        return value instanceof String text ? text.trim() : null;
    }

    private static String optionalUuid(Map<?, ?> map, String key) {
        String value = optionalText(map.get(key));
        if (value == null || value.isBlank()) return null;
        try {
            UUID.fromString(value);
            return value;
        } catch (IllegalArgumentException error) {
            throw bad("SIMULATION_UUID_INVALID", key + " 必须是 UUID 字符串");
        }
    }

    private static Map<?, ?> optionalMap(Map<?, ?> source, String key) {
        Object value = source.get(key);
        if (value == null) return Map.of();
        if (value instanceof Map<?, ?> map) return map;
        throw bad("SIMULATION_OBJECT_INVALID", key + " 必须是对象");
    }

    private static String optionalText(Object value, String fallback) {
        String text = optionalText(value);
        return text == null || text.isBlank() ? fallback : text;
    }

    private static boolean isDynamicF3(Map<String, Object> record) {
        if (!"2.0".equals(optionalText(record.get("schemaVersion")))) return false;
        return record.get("session") instanceof Map<?, ?> && record.get("events") instanceof List<?>;
    }

    private static String uuid(Map<?, ?> map, String key) {
        String value = text(map, key);
        try {
            UUID.fromString(value);
            return value;
        } catch (IllegalArgumentException error) {
            throw bad("SIMULATION_UUID_INVALID", key + " 必须是 UUID 字符串");
        }
    }

    private static int number(Map<?, ?> map, String key) {
        Object value = map.get(key);
        if (!(value instanceof Number number)) throw bad("SIMULATION_NUMBER_INVALID", key + " 必须是整数");
        int result = number.intValue();
        if (number.doubleValue() != result) throw bad("SIMULATION_NUMBER_INVALID", key + " 必须是整数");
        return result;
    }

    private static List<?> list(Map<?, ?> map, String key) {
        Object value = map.get(key);
        if (value instanceof List<?> list) return list;
        throw bad("SIMULATION_ARRAY_INVALID", key + " 必须是数组");
    }

    private static Map<?, ?> map(Map<?, ?> source, String key) {
        Object value = source.get(key);
        if (value instanceof Map<?, ?> map) return map;
        throw bad("SIMULATION_OBJECT_INVALID", key + " 必须是对象");
    }

    private static Instant instant(String value, String key) {
        try {
            return OffsetDateTime.parse(value).toInstant();
        } catch (RuntimeException error) {
            try {
                return Instant.parse(value);
            } catch (RuntimeException ignored) {
                throw bad("SIMULATION_TIME_INVALID", key + " 必须是 ISO-8601 时间");
            }
        }
    }

    private static String bounded(String value, int max, String key) {
        if (value.length() > max) throw bad("SIMULATION_FIELD_TOO_LONG", key + " 超过长度限制");
        return value;
    }

    private static AppException bad(String code, String message) {
        return new AppException(HttpStatus.BAD_REQUEST, code, message);
    }
}
