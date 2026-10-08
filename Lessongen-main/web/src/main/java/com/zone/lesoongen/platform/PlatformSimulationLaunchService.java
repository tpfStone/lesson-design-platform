package com.zone.lesoongen.platform;
import java.util.LinkedHashMap;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.time.Duration;
import java.sql.Timestamp;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.platform.PlatformSimulationLaunchController.LaunchRequest;
import tools.jackson.databind.ObjectMapper;

@Service
public class PlatformSimulationLaunchService {
    public record Launch(UUID launchId, UUID requestKey, String lessonId, String versionId, String state,
            String simulationRunId, String f3SessionId, String f4SessionId, List<String> activeRoles,
            int timeoutSeconds, String message, Instant createdAt) {}
    private final JdbcTemplate db;
    private final PlatformLessonService lessons;
    private final PlatformNavigationBridgeService navigation;
    private final ObjectMapper mapper;
    private final String python, script, f2Url, f3Url, f4Url;
    private final RestClient f3;
    private static final List<String> ROLES = List.of("teacher", "assistant", "class_clown",
            "deep_thinker", "note_taker", "inquisitive_mind");

    public PlatformSimulationLaunchService(JdbcTemplate db, PlatformLessonService lessons,
            PlatformNavigationBridgeService navigation, ObjectMapper mapper,
            @Value("${platform.f3.python:${F3_PYTHON:python}}") String python,
            @Value("${platform.f3.runner-script:scripts/f3-runner/run_f3_demo.py}") String script,
            @Value("${platform.f3.base-url:http://127.0.0.1:8003}") String f3Url,
            @Value("${platform.f4.base-url:http://127.0.0.1:8000}") String f4Url,
            @Value("${platform.f2.self-url:http://127.0.0.1:8080}") String f2Url) {
        this.db = db; this.lessons = lessons; this.navigation = navigation; this.mapper = mapper;
        this.python = python; this.script = script; this.f3Url = f3Url; this.f4Url = f4Url; this.f2Url = f2Url;
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(5));
        factory.setReadTimeout(Duration.ofSeconds(60));
        this.f3 = RestClient.builder().baseUrl(f3Url).requestFactory(factory).build();
    }

    public synchronized Launch start(LaunchRequest request) {
        List<String> roles = request.activeRoles();
        if (roles != null && (roles.isEmpty() || !roles.contains("teacher")
                || roles.stream().anyMatch(role -> role == null || !ROLES.contains(role))
                || roles.stream().distinct().count() != roles.size())) {
            throw new AppException(HttpStatus.BAD_REQUEST, "F3_ROLES_INVALID", "请选择有效的课堂角色，教师必须参与");
        }
        if (roles != null) roles = List.copyOf(roles);
        int timeout = request.timeoutSeconds() == null ? 3 : request.timeoutSeconds();
        if (timeout < 1 || timeout > 300) {
            throw new AppException(HttpStatus.BAD_REQUEST, "F3_TIMEOUT_INVALID", "自动继续等待时间须为 1 至 300 秒");
        }
        Launch existing = findByRequest(request.requestKey());
        if (existing != null) {
            if (!existing.lessonId().equals(request.lessonId()) || !existing.versionId().equals(request.versionId())
                    || !java.util.Objects.equals(existing.activeRoles(), roles) || existing.timeoutSeconds() != timeout)
                throw new AppException(HttpStatus.CONFLICT, "F3_REQUEST_REUSED", "此请求编号已用于其他教案版本");
            return existing;
        }
        var lesson = lessons.detail(request.lessonId());
        if (lesson.versions().stream().noneMatch(v -> v.id().equals(request.versionId())))
            throw AppException.notFound("教案版本");
        UUID id = UUID.randomUUID();
        Launch queued = new Launch(id, request.requestKey(), request.lessonId(), request.versionId(), "QUEUED", null,
                null, null, roles, timeout, "正在准备课堂模拟", Instant.now());
        insert(queued);
        Thread worker = new Thread(() -> run(queued), "f3-launch-" + id);
        worker.setDaemon(true);
        worker.start();
        return queued;
    }

    public Launch status(UUID id) {
        Launch value = find(id);
        if (value == null) throw AppException.notFound("课堂模拟启动任务");
        return value;
    }

    public List<Launch> list() {
        return db.query("""
                SELECT launch_id, request_key, lesson_id, version_id, state, simulation_run_id,
                       f3_session_id, f4_session_id, active_roles_json, timeout_seconds, message, created_at
                FROM platform_simulation_launch ORDER BY created_at DESC, launch_id DESC LIMIT 100
                """, (rs, row) -> launch(rs));
    }

    @EventListener(ApplicationReadyEvent.class)
    public void reconcileAfterRestart() {
        db.update("""
                UPDATE platform_simulation_launch
                SET state = 'INTERRUPTED', message = ?, updated_at = ?
                WHERE state IN ('QUEUED', 'RUNNING')
                """, "平台服务曾重启，此任务已停止；可以重新发起课堂推演",
                Timestamp.from(Instant.now()));
    }

    private void insert(Launch launch) {
        String roles;
        try {
            roles = launch.activeRoles() == null ? null : mapper.writeValueAsString(launch.activeRoles());
        } catch (Exception error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "F3_LAUNCH_SERIALIZE_FAILED",
                    "课堂角色配置保存失败");
        }
        db.update("""
                INSERT INTO platform_simulation_launch
                (launch_id, request_key, lesson_id, version_id, state, simulation_run_id,
                 f3_session_id, f4_session_id, active_roles_json, timeout_seconds,
                 message, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, launch.launchId().toString(), launch.requestKey().toString(), launch.lessonId(),
                launch.versionId(), launch.state(), launch.simulationRunId(), launch.f3SessionId(),
                launch.f4SessionId(), roles, launch.timeoutSeconds(), launch.message(),
                Timestamp.from(launch.createdAt()), Timestamp.from(launch.createdAt()));
    }

    private Launch find(UUID launchId) {
        List<Launch> rows = db.query("""
                SELECT launch_id, request_key, lesson_id, version_id, state, simulation_run_id,
                       f3_session_id, f4_session_id, active_roles_json, timeout_seconds, message, created_at
                FROM platform_simulation_launch WHERE launch_id = ?
                """, (rs, row) -> launch(rs), launchId.toString());
        return rows.isEmpty() ? null : rows.get(0);
    }

    private Launch findByRequest(UUID requestKey) {
        List<Launch> rows = db.query("""
                SELECT launch_id, request_key, lesson_id, version_id, state, simulation_run_id,
                       f3_session_id, f4_session_id, active_roles_json, timeout_seconds, message, created_at
                FROM platform_simulation_launch WHERE request_key = ?
                """, (rs, row) -> launch(rs), requestKey.toString());
        return rows.isEmpty() ? null : rows.get(0);
    }

    @SuppressWarnings("unchecked")
    private Launch launch(ResultSet rs) throws SQLException {
        List<String> roles = null;
        String json = rs.getString("active_roles_json");
        if (json != null && !json.isBlank()) {
            try {
                roles = List.copyOf(mapper.readValue(json, List.class));
            } catch (Exception error) {
                throw new SQLException("Invalid active_roles_json", error);
            }
        }
        return new Launch(UUID.fromString(rs.getString("launch_id")),
                UUID.fromString(rs.getString("request_key")), rs.getString("lesson_id"),
                rs.getString("version_id"), rs.getString("state"), rs.getString("simulation_run_id"),
                rs.getString("f3_session_id"), rs.getString("f4_session_id"), roles,
                rs.getInt("timeout_seconds"), rs.getString("message"),
                rs.getTimestamp("created_at").toInstant());
    }

    private void update(Launch original, String state, String runId, String message) {
        db.update("""
                UPDATE platform_simulation_launch
                SET state = ?, simulation_run_id = ?, message = ?, updated_at = ?
                WHERE launch_id = ?
                """, state, runId, message, Timestamp.from(Instant.now()), original.launchId().toString());
    }

    private void bindF4Session(Launch original, String f4SessionId) {
        db.update("UPDATE platform_simulation_launch SET f4_session_id = ?, updated_at = ? WHERE launch_id = ?",
                f4SessionId, Timestamp.from(Instant.now()), original.launchId().toString());
    }

    private void observeSession(Launch launch, Path livePath) throws IOException {
        if (!Files.isRegularFile(livePath)) return;
        Map<?, ?> live = mapper.readValue(Files.readAllBytes(livePath), Map.class);
        if (!launch.lessonId().equals(live.get("lessonId")) || !launch.versionId().equals(live.get("versionId")))
            throw new IOException("F3 会话与教案版本不匹配");
        String sessionId = UUID.fromString(String.valueOf(live.get("sessionId"))).toString();
        db.update("UPDATE platform_simulation_launch SET f3_session_id = ?, updated_at = ? WHERE launch_id = ?",
                sessionId, Timestamp.from(Instant.now()), launch.launchId().toString());
    }

    private String sessionId(UUID launchId) {
        Launch launch = status(launchId);
        if (launch.f3SessionId() == null)
            throw new AppException(HttpStatus.CONFLICT, "F3_SESSION_PREPARING", "课堂正在准备，请稍后重试");
        return launch.f3SessionId();
    }

    private Map<?, ?> request(java.util.function.Supplier<Map<?, ?>> action) {
        try {
            Map<?, ?> response = action.get();
            if (response == null) throw new AppException(HttpStatus.BAD_GATEWAY, "F3_EMPTY_RESPONSE", "课堂服务未返回结果");
            return response;
        } catch (RestClientResponseException error) {
            HttpStatus code = HttpStatus.resolve(error.getStatusCode().value());
            throw new AppException(code == null ? HttpStatus.BAD_GATEWAY : code, "F3_CLASSROOM_ERROR",
                    "课堂操作未完成：" + tail(error.getResponseBodyAsString()));
        } catch (RestClientException error) {
            throw new AppException(HttpStatus.BAD_GATEWAY, "F3_UNAVAILABLE", "课堂服务暂时不可用，请检查 F3 服务");
        }
    }

    public Map<?, ?> classroom(UUID launchId) {
        String id = sessionId(launchId);
        return request(() -> f3.get().uri("/api/classroom/sessions/{id}", id).retrieve().body(Map.class));
    }

    public Map<?, ?> events(UUID launchId) {
        String id = sessionId(launchId);
        return request(() -> f3.get().uri("/api/classroom/sessions/{id}/events", id).retrieve().body(Map.class));
    }

    public Map<?, ?> message(UUID launchId, String content) {
        String id = sessionId(launchId);
        return request(() -> f3.post().uri("/api/classroom/sessions/{id}/messages", id)
                .body(Map.of("message", content)).retrieve().body(Map.class));
    }

    public Map<?, ?> control(UUID launchId, String action) {
        if (!List.of("pause", "resume", "end").contains(action))
            throw new AppException(HttpStatus.BAD_REQUEST, "F3_CONTROL_INVALID", "无效的课堂操作");
        String id = sessionId(launchId);
        return request(() -> f3.post().uri("/api/classroom/sessions/{id}/" + action, id)
                .retrieve().body(Map.class));
    }

    public Map<?, ?> settings(UUID launchId, int timeoutSeconds) {
        String id = sessionId(launchId);
        return request(() -> f3.patch().uri("/api/classroom/sessions/{id}/settings", id)
                .body(Map.of("timeoutSeconds", timeoutSeconds)).retrieve().body(Map.class));
    }

    private void run(Launch launch) {
        Path directory = null;
        try {
            update(launch, "RUNNING", null, "正在建立教案会话并执行动态课堂模拟");
            var started = navigation.start(launch.lessonId(), launch.versionId(), launch.launchId(), null, null, null);
            bindF4Session(launch, started.sessionId());
            directory = Files.createTempDirectory("f3-launch-");
            Path config = directory.resolve("config.json");
            Path log = directory.resolve("runner.log");
            Path live = directory.resolve("f3-session.json");
            Map<String, Object> input = new LinkedHashMap<>();
            input.put("f4Url", f4Url);
            input.put("f3Url", f3Url);
            input.put("f2Url", f2Url);
            input.put("writebackToF2", true);
            input.put("lessonId", launch.lessonId());
            input.put("versionId", launch.versionId());
            input.put("f4SessionId", started.sessionId());
            input.put("requestKey", launch.launchId().toString());
            input.put("modelMode", "REAL");
            input.put("timeoutSeconds", launch.timeoutSeconds());
            if (launch.activeRoles() != null) input.put("activeRoles", launch.activeRoles());
            input.put("liveStatusPath", live.toString());
            input.put("maxConsecutiveTimeouts", 50);
            input.put("maxEvents", 40);
            input.put("maxWallClockSeconds", 900);
            input.put("outputDir", directory.resolve("outputs").toString());
            Files.writeString(config, mapper.writeValueAsString(input), StandardCharsets.UTF_8);
            Path runner = Path.of(script).toAbsolutePath();
            if (!Files.isRegularFile(runner)) runner = Path.of("web").resolve(script).toAbsolutePath();
            if (!Files.isRegularFile(runner)) throw new IOException("F3 Runner 文件不存在：" + runner);
            ProcessBuilder builder = new ProcessBuilder(python, runner.toString(), "--config", config.toString())
                    .redirectErrorStream(true).redirectOutput(log.toFile());
            // Windows PowerShell commonly gives Python a GBK console encoding. The runner log is
            // consumed as UTF-8 below, so force a stable encoding across Windows installations.
            builder.environment().put("PYTHONUTF8", "1");
            builder.environment().put("PYTHONIOENCODING", "utf-8");
            Process process = builder.start();
            Instant deadline = Instant.now().plus(Duration.ofMinutes(30));
            while (!process.waitFor(1, TimeUnit.SECONDS)) {
                observeSession(launch, live);
                if (Instant.now().isAfter(deadline)) {
                    process.destroyForcibly(); throw new IOException("课堂模拟超过最长等待时间，请检查 F3 服务");
                }
            }
            observeSession(launch, live);
            String output = Files.readString(log, StandardCharsets.UTF_8);
            if (process.exitValue() != 0) throw new IOException("F3 Runner 失败：" + tail(output));
            String marker = "F2 simulationRunId:";
            int index = output.lastIndexOf(marker);
            if (index < 0) throw new IOException("模拟结束但没有 F2 回写凭据：" + tail(output));
            String runId = output.substring(index + marker.length()).stripLeading().split("\\R", 2)[0].trim();
            if (runId.isBlank()) throw new IOException("F2 回写编号为空");
            if (output.contains("最终状态: INTERRUPTED"))
                update(launch, "INTERRUPTED", runId, "课堂已提前结束，已保存现有记录");
            else update(launch, "COMPLETED", runId, "动态课堂模拟已完成，结果已保存到 F2");
        } catch (Exception error) {
            update(launch, "FAILED", null, tail(error.getMessage() == null ? error.toString() : error.getMessage()));
        } finally {
            if (directory != null) try {
                // Successful artifacts are durable in F2; keep failed runner files for local diagnosis.
                if ("COMPLETED".equals(status(launch.launchId()).state())
                        || "INTERRUPTED".equals(status(launch.launchId()).state())) {
                    try (var paths = Files.walk(directory)) {
                        paths.sorted(java.util.Comparator.reverseOrder()).forEach(path -> { try { Files.deleteIfExists(path); } catch (IOException ignored) {} });
                    }
                }
            } catch (IOException ignored) {}
        }
    }

    private static String tail(String text) {
        String clean = text == null ? "未知错误" : text.trim();
        return clean.substring(Math.max(0, clean.length() - 700));
    }
}
