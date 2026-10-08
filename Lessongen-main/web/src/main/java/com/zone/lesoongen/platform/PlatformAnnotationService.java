package com.zone.lesoongen.platform;

import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.domain.shared.Ulids;
import com.zone.lesoongen.platform.PlatformLessonController.LessonDetail;
import com.zone.lesoongen.platform.PlatformLessonController.LessonVersion;

@Service
public class PlatformAnnotationService {
    private static final Logger log = LoggerFactory.getLogger(PlatformAnnotationService.class);
    private static final Set<String> ARTIFACTS = Set.of("docx", "json", "md", "docx_annotated", "pdf");
    private static final Set<String> BATCH_ARTIFACTS = Set.of(
            "quality_json", "quality_docx", "comparison_json", "comparison_md", "comparison_csv");
    private static final Set<String> COMPARISON_ARTIFACTS = Set.of("json", "md", "csv");
    private final JdbcTemplate db;
    private final PlatformLessonService lessons;
    private final PlatformIssueIngestService issueIngest;
    private final RestClient f1;
    private final ObjectMapper mapper;

    public PlatformAnnotationService(JdbcTemplate db, PlatformLessonService lessons,
            PlatformIssueIngestService issueIngest, ObjectMapper mapper,
            @Value("${app.f1-base-url:http://127.0.0.1:8002}") String f1BaseUrl) {
        this.db = db;
        this.lessons = lessons;
        this.issueIngest = issueIngest;
        this.mapper = mapper;
        // Match F2's working Python-engine transport. Avoid an h2c upgrade,
        // which can cause Uvicorn/httptools to discard the request body.
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(3));
        factory.setReadTimeout(Duration.ofSeconds(30));
        this.f1 = RestClient.builder().baseUrl(f1BaseUrl).requestFactory(factory).build();
    }

    public record AnnotationRun(String id, String lessonId, String versionId,
            int versionNumber, String nativeRunId, Instant createdAt, Map<?, ?> state) {}

    public record BatchItemRef(String lessonId, String versionId) {}

    public AnnotationRun create(String lessonId, String versionId, boolean suggest) {
        LessonDetail detail = lessons.detail(lessonId);
        LessonVersion version = detail.versions().stream()
                .filter(item -> item.id().equals(versionId)).findFirst()
                .orElseThrow(() -> AppException.notFound("教案版本"));
        byte[] payload;
        try {
            payload = mapper.writeValueAsBytes(Map.of("lesson_id", lessonId, "version_id", versionId,
                    "subject", nonblank(detail.lesson().subject(), "未指定学科"),
                    "grade", nonblank(detail.lesson().grade(), "未指定年级"),
                    "topic", nonblank(detail.lesson().topic(), detail.lesson().title()), "content", version.content(),
                    "suggest", suggest));
        } catch (JacksonException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "F1_REQUEST_SERIALIZATION",
                    "无法生成 F1 批注请求");
        }
        log.info("F1 annotation request payloadBytes={}", payload.length);
        Map<?, ?> accepted = request(() -> f1.post().uri("/internal/v1/runs/annotate")
                .contentType(MediaType.APPLICATION_JSON)
                .contentLength(payload.length)
                .accept(MediaType.APPLICATION_JSON)
                .body(payload)
                .retrieve().body(Map.class));
        Object nativeValue = accepted == null ? null : accepted.get("runId");
        String nativeId = nativeValue instanceof String value ? value : "";
        if (!nativeId.matches("[0-9a-f]{32}")) {
            throw new AppException(HttpStatus.BAD_GATEWAY, "F1_INVALID_RESPONSE", "F1 返回的任务编号无效");
        }
        String id = Ulids.next(java.time.Clock.systemUTC());
        Instant now = Instant.now();
        db.update("INSERT INTO platform_annotation_run (id, lesson_id, version_id, native_run_id, created_at) VALUES (?, ?, ?, ?, ?)",
                id, lessonId, versionId, nativeId, Timestamp.from(now));
        return new AnnotationRun(id, lessonId, versionId, version.versionNumber(), nativeId, now, accepted);
    }

    private static String nonblank(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value.trim();
    }


    public Map<String, Object> createBatch(List<BatchItemRef> refs, boolean suggest) {
        if (refs == null || refs.size() < 2 || refs.size() > 20) {
            throw new AppException(HttpStatus.BAD_REQUEST, "F1_BATCH_SIZE",
                    "批量评审需要选择 2 到 20 个教案版本");
        }

        LinkedHashSet<String> seen = new LinkedHashSet<>();
        List<Map<String, Object>> items = new ArrayList<>();
        for (BatchItemRef ref : refs) {
            String key = ref.lessonId() + "\u0000" + ref.versionId();
            if (!seen.add(key)) {
                throw new AppException(HttpStatus.BAD_REQUEST, "F1_BATCH_DUPLICATE",
                        "批量评审中不能重复选择同一教案版本");
            }
            LessonDetail detail = lessons.detail(ref.lessonId());
            LessonVersion version = detail.versions().stream()
                    .filter(item -> item.id().equals(ref.versionId())).findFirst()
                    .orElseThrow(() -> AppException.notFound("教案版本"));

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("lesson_id", ref.lessonId());
            item.put("version_id", ref.versionId());
            item.put("subject", nonblank(detail.lesson().subject(), "未指定学科"));
            item.put("grade", nonblank(detail.lesson().grade(), "未指定年级"));
            item.put("topic", nonblank(detail.lesson().topic(), detail.lesson().title()));
            item.put("content", version.content());
            item.put("suggest", suggest);
            items.add(item);
        }

        byte[] payload = serialize(Map.of("items", items), "F1_BATCH_REQUEST_SERIALIZATION",
                "无法生成 F1 批量评审请求");
        Map<?, ?> accepted = request(() -> f1.post().uri("/internal/v1/batches/annotate")
                .contentType(MediaType.APPLICATION_JSON)
                .contentLength(payload.length)
                .accept(MediaType.APPLICATION_JSON)
                .body(payload)
                .retrieve().body(Map.class));
        Map<String, Object> out = copyMap(accepted);
        requireF1Id(out.get("batchId"), "batchId", "F1 返回的批量任务编号无效");
        return out;
    }

    public Map<String, Object> batchState(String batchId) {
        validateJobId(batchId, "batchId", "批量任务编号无效");
        Map<?, ?> state = request(() -> f1.get().uri("/internal/v1/batches/{id}", batchId)
                .retrieve().body(Map.class));
        return enrichAndSyncBatch(state, false);
    }

    public Map<String, Object> batchResult(String batchId) {
        validateJobId(batchId, "batchId", "批量任务编号无效");
        Map<?, ?> result = request(() -> f1.get().uri("/internal/v1/batches/{id}/result", batchId)
                .retrieve().body(Map.class));
        return enrichAndSyncBatch(result, true);
    }

    public byte[] batchArtifact(String batchId, String kind) {
        validateJobId(batchId, "batchId", "批量任务编号无效");
        if (!BATCH_ARTIFACTS.contains(kind)) throw AppException.notFound("批量评审成果");
        return request(() -> f1.get().uri("/internal/v1/batches/{id}/artifacts/{kind}", batchId, kind)
                .retrieve().body(byte[].class));
    }

    public Map<String, Object> createComparison(List<String> annotationIds) {
        if (annotationIds == null || annotationIds.size() < 2 || annotationIds.size() > 20) {
            throw new AppException(HttpStatus.BAD_REQUEST, "F1_COMPARISON_SIZE",
                    "横向对比需要选择 2 到 20 个评分结果");
        }
        LinkedHashSet<String> unique = new LinkedHashSet<>(annotationIds);
        if (unique.size() < 2) {
            throw new AppException(HttpStatus.BAD_REQUEST, "F1_COMPARISON_DUPLICATE",
                    "横向对比至少需要 2 个不同的评分结果");
        }

        List<String> nativeRunIds = new ArrayList<>();
        List<String> platformIds = new ArrayList<>();
        for (String id : unique) {
            AnnotationRun run = findById(id);
            nativeRunIds.add(run.nativeRunId());
            platformIds.add(run.id());
        }

        byte[] payload = serialize(Map.of("run_ids", nativeRunIds), "F1_COMPARISON_REQUEST_SERIALIZATION",
                "无法生成 F1 横向对比请求");
        Map<?, ?> accepted = request(() -> f1.post().uri("/internal/v1/comparisons")
                .contentType(MediaType.APPLICATION_JSON)
                .contentLength(payload.length)
                .accept(MediaType.APPLICATION_JSON)
                .body(payload)
                .retrieve().body(Map.class));
        Map<String, Object> out = copyMap(accepted);
        requireF1Id(out.get("comparisonId"), "comparisonId", "F1 返回的对比任务编号无效");
        out.put("annotationIds", platformIds);
        return out;
    }

    public Map<String, Object> comparisonState(String comparisonId) {
        validateJobId(comparisonId, "comparisonId", "对比任务编号无效");
        return copyMap(request(() -> f1.get().uri("/internal/v1/comparisons/{id}", comparisonId)
                .retrieve().body(Map.class)));
    }

    public Map<String, Object> comparisonResult(String comparisonId) {
        validateJobId(comparisonId, "comparisonId", "对比任务编号无效");
        return copyMap(request(() -> f1.get().uri("/internal/v1/comparisons/{id}/result", comparisonId)
                .retrieve().body(Map.class)));
    }

    public byte[] comparisonArtifact(String comparisonId, String kind) {
        validateJobId(comparisonId, "comparisonId", "对比任务编号无效");
        if (!COMPARISON_ARTIFACTS.contains(kind)) throw AppException.notFound("横向对比成果");
        return request(() -> f1.get().uri("/internal/v1/comparisons/{id}/artifacts/{kind}", comparisonId, kind)
                .retrieve().body(byte[].class));
    }

    private Map<String, Object> enrichAndSyncBatch(Map<?, ?> source, boolean ingestResults) {
        Map<String, Object> payload = copyMap(source);
        Object itemsValue = source == null ? null : source.get("items");
        if (!(itemsValue instanceof List<?> items)) return payload;

        List<Map<String, Object>> enriched = new ArrayList<>();
        for (Object rawItem : items) {
            if (!(rawItem instanceof Map<?, ?> item)) continue;
            Map<String, Object> row = copyMap(item);
            String nativeRunId = stringValue(item.get("runId"));
            String lessonId = stringValue(item.get("lessonId"));
            String versionId = stringValue(item.get("versionId"));
            String status = stringValue(item.get("status"));

            if (nativeRunId != null && nativeRunId.matches("[0-9a-f]{32}")
                    && lessonId != null && versionId != null) {
                String annotationId = ensureAnnotationRun(nativeRunId, lessonId, versionId);
                row.put("annotationId", annotationId);
                if (ingestResults && "COMPLETED".equals(status)) {
                    Map<?, ?> single = request(() -> f1.get().uri("/internal/v1/runs/{id}/result", nativeRunId)
                            .retrieve().body(Map.class));
                    issueIngest.ingestF1(lessonId, versionId, annotationId, nativeRunId, single);
                }
            }
            enriched.add(row);
        }
        payload.put("items", enriched);
        return payload;
    }

    private synchronized String ensureAnnotationRun(String nativeRunId, String lessonId, String versionId) {
        List<String> existing = db.query("""
                SELECT id FROM platform_annotation_run
                WHERE native_run_id = ? ORDER BY created_at DESC LIMIT 1
                """, (rs, row) -> rs.getString("id"), nativeRunId);
        if (!existing.isEmpty()) return existing.get(0);

        LessonDetail detail = lessons.detail(lessonId);
        boolean versionExists = detail.versions().stream().anyMatch(item -> item.id().equals(versionId));
        if (!versionExists) throw AppException.notFound("教案版本");

        String id = Ulids.next(java.time.Clock.systemUTC());
        db.update("INSERT INTO platform_annotation_run (id, lesson_id, version_id, native_run_id, created_at) VALUES (?, ?, ?, ?, ?)",
                id, lessonId, versionId, nativeRunId, Timestamp.from(Instant.now()));
        return id;
    }

    private AnnotationRun findById(String id) {
        return db.query("""
                SELECT r.id, r.lesson_id, r.version_id, r.native_run_id, r.created_at,
                       v.version_number
                FROM platform_annotation_run r JOIN platform_lesson_version v ON v.id = r.version_id
                WHERE r.id = ?
                """, (rs, row) -> new AnnotationRun(rs.getString("id"), rs.getString("lesson_id"),
                rs.getString("version_id"), rs.getInt("version_number"),
                rs.getString("native_run_id"), rs.getTimestamp("created_at").toInstant(), null),
                id).stream().findFirst().orElseThrow(() -> AppException.notFound("批注任务"));
    }

    private byte[] serialize(Object value, String code, String message) {
        try {
            return mapper.writeValueAsBytes(value);
        } catch (JacksonException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, code, message);
        }
    }

    private static Map<String, Object> copyMap(Map<?, ?> source) {
        Map<String, Object> out = new LinkedHashMap<>();
        if (source == null) return out;
        for (Map.Entry<?, ?> entry : source.entrySet()) {
            if (entry.getKey() != null) out.put(String.valueOf(entry.getKey()), entry.getValue());
        }
        return out;
    }

    private static String stringValue(Object value) {
        return value instanceof String text && !text.isBlank() ? text : null;
    }

    private static String requireF1Id(Object value, String field, String message) {
        String id = stringValue(value);
        if (id == null || !id.matches("[0-9a-f]{32}")) {
            throw new AppException(HttpStatus.BAD_GATEWAY, "F1_INVALID_" + field.toUpperCase(), message);
        }
        return id;
    }

    private static String validateJobId(Object value, String field, String message) {
        String id = stringValue(value);
        if (id == null || !id.matches("[0-9a-f]{32}")) {
            throw new AppException(HttpStatus.BAD_REQUEST, "INVALID_" + field.toUpperCase(), message);
        }
        return id;
    }

    public List<AnnotationRun> list(String lessonId) {
        lessons.detail(lessonId);
        return db.query("""
                SELECT r.id, r.lesson_id, r.version_id, r.native_run_id, r.created_at,
                       v.version_number
                FROM platform_annotation_run r JOIN platform_lesson_version v ON v.id = r.version_id
                WHERE r.lesson_id = ? ORDER BY r.created_at DESC, r.id DESC LIMIT 50
                """, (rs, row) -> new AnnotationRun(rs.getString("id"), rs.getString("lesson_id"),
                rs.getString("version_id"), rs.getInt("version_number"),
                rs.getString("native_run_id"), rs.getTimestamp("created_at").toInstant(), null), lessonId);
    }

    public AnnotationRun state(String lessonId, String id) {
        AnnotationRun run = find(lessonId, id);
        Map<?, ?> state = request(() -> f1.get().uri("/internal/v1/runs/{id}", run.nativeRunId())
                .retrieve().body(Map.class));
        return new AnnotationRun(run.id(), lessonId, run.versionId(), run.versionNumber(),
                run.nativeRunId(), run.createdAt(), state);
    }

    public Map<?, ?> result(String lessonId, String id) {
        AnnotationRun run = find(lessonId, id);
        Map<?, ?> result = request(() -> f1.get().uri("/internal/v1/runs/{id}/result", run.nativeRunId())
                .retrieve().body(Map.class));
        issueIngest.ingestF1(lessonId, run.versionId(), run.id(), run.nativeRunId(), result);
        return result;
    }

    public byte[] artifact(String lessonId, String id, String kind) {
        if (!ARTIFACTS.contains(kind)) throw AppException.notFound("批注文件");
        AnnotationRun run = find(lessonId, id);
        return request(() -> f1.get().uri("/internal/v1/runs/{id}/artifacts/{kind}",
                run.nativeRunId(), kind).retrieve().body(byte[].class));
    }

    private AnnotationRun find(String lessonId, String id) {
        lessons.detail(lessonId);
        return db.query("""
                SELECT r.id, r.lesson_id, r.version_id, r.native_run_id, r.created_at,
                       v.version_number
                FROM platform_annotation_run r JOIN platform_lesson_version v ON v.id = r.version_id
                WHERE r.lesson_id = ? AND r.id = ?
                """, (rs, row) -> new AnnotationRun(rs.getString("id"), rs.getString("lesson_id"),
                rs.getString("version_id"), rs.getInt("version_number"),
                rs.getString("native_run_id"), rs.getTimestamp("created_at").toInstant(), null),
                lessonId, id).stream().findFirst().orElseThrow(() -> AppException.notFound("批注任务"));
    }

    private <T> T request(java.util.function.Supplier<T> action) {
        try {
            return action.get();
        } catch (RestClientResponseException error) {
            throw new AppException(HttpStatus.BAD_GATEWAY, "F1_HTTP_ERROR",
                    "F1 接口返回 HTTP " + error.getStatusCode().value()
                            + "；请查看 8002 终端的字段校验或任务日志");
        } catch (RestClientException error) {
            throw new AppException(HttpStatus.BAD_GATEWAY, "F1_UNAVAILABLE",
                    "F1 批注接口未就绪或返回错误，请检查 8002 端口的终端");
        }
    }
}
