package com.zone.lesoongen.platform;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

/** Same-origin workbench gateway. F4 owns its sessions and mutation rules. */
@RestController
@RequestMapping("/api/platform/f4")
public class PlatformF4WorkbenchController {
    private final RestClient client;

    public PlatformF4WorkbenchController(
            @Value("${platform.f4.base-url:http://127.0.0.1:8000}") String baseUrl) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(5));
        factory.setReadTimeout(Duration.ofSeconds(180));
        client = RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
    }

    @GetMapping("/health")
    public ResponseEntity<byte[]> health() { return forward(HttpMethod.GET, "/health", null); }

    @GetMapping("/me")
    public ResponseEntity<byte[]> me() { return forward(HttpMethod.GET, "/me", null); }

    @GetMapping("/capabilities")
    public ResponseEntity<byte[]> capabilities() { return forward(HttpMethod.GET, "/capabilities", null); }

    @GetMapping("/sessions")
    public ResponseEntity<byte[]> sessions() { return forward(HttpMethod.GET, "/sessions", null); }

    @PostMapping("/sessions")
    public ResponseEntity<byte[]> create(@RequestBody byte[] body) {
        return forward(HttpMethod.POST, "/sessions", body);
    }

    @GetMapping("/sessions/{sessionId}/current-state")
    public ResponseEntity<byte[]> state(@PathVariable("sessionId") UUID id) {
        return forward(HttpMethod.GET, "/sessions/" + id + "/current-state", null);
    }

    @PostMapping("/sessions/{sessionId}/view")
    public ResponseEntity<byte[]> view(@PathVariable("sessionId") UUID id, @RequestBody byte[] body) {
        return forward(HttpMethod.POST, "/sessions/" + id + "/view", body);
    }

    @PostMapping("/sessions/{sessionId}/suggestions")
    public ResponseEntity<byte[]> suggestions(@PathVariable("sessionId") UUID id, @RequestBody byte[] body) {
        return forward(HttpMethod.POST, "/sessions/" + id + "/suggestions", body);
    }

    @PostMapping("/sessions/{sessionId}/suggestions/{suggestionId}/decision")
    public ResponseEntity<byte[]> decide(@PathVariable("sessionId") UUID id,
            @PathVariable("suggestionId") UUID suggestionId, @RequestBody byte[] body) {
        return forward(HttpMethod.POST, "/sessions/" + id + "/suggestions/" + suggestionId + "/decision", body);
    }

    @PostMapping("/sessions/{sessionId}/complete-section")
    public ResponseEntity<byte[]> complete(@PathVariable("sessionId") UUID id, @RequestBody byte[] body) {
        return forward(HttpMethod.POST, "/sessions/" + id + "/complete-section", body);
    }

    @PostMapping("/sessions/{sessionId}/rounds/{roundId}/continue")
    public ResponseEntity<byte[]> nextRound(@PathVariable("sessionId") UUID id,
            @PathVariable("roundId") UUID roundId) {
        return forward(HttpMethod.POST, "/sessions/" + id + "/rounds/" + roundId + "/continue", null);
    }

    @PostMapping("/sessions/{sessionId}/terminate")
    public ResponseEntity<byte[]> terminate(@PathVariable("sessionId") UUID id) {
        return forward(HttpMethod.POST, "/sessions/" + id + "/terminate", null);
    }

    @GetMapping("/sessions/{sessionId}/export")
    public ResponseEntity<byte[]> export(@PathVariable("sessionId") UUID id) {
        return forward(HttpMethod.GET, "/sessions/" + id + "/export", null);
    }

    private ResponseEntity<byte[]> forward(HttpMethod method, String suffix, byte[] body) {
        try {
            RestClient.RequestBodySpec request = client.method(method).uri("/api" + suffix)
                    .accept(MediaType.APPLICATION_JSON);
            if (body != null) {
                request.contentType(MediaType.APPLICATION_JSON).contentLength(body.length).body(body);
            } else if (method == HttpMethod.POST) {
                request.contentLength(0);
            }
            // exchange preserves F4's status, detail and code, including 409/422/502.
            return request.exchange((outgoing, incoming) -> {
                MediaType type = incoming.getHeaders().getContentType();
                ResponseEntity.BodyBuilder result = ResponseEntity.status(incoming.getStatusCode())
                        .contentType(type == null ? MediaType.APPLICATION_JSON : type)
                        .header(HttpHeaders.CACHE_CONTROL, "no-store");
                String disposition = incoming.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION);
                if (disposition != null) result.header(HttpHeaders.CONTENT_DISPOSITION, disposition);
                return result.body(incoming.getBody().readAllBytes());
            });
        } catch (ResourceAccessException unavailable) {
            // Never expose model keys, connection headers or upstream exception text.
            String detail = "{\"code\":\"F4_CONNECTION_FAILED\",\"detail\":\"F4 导航服务连接失败或响应超时，请检查 8000 服务；已有会话可恢复后继续。\"}";
            return ResponseEntity.status(503).contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.CACHE_CONTROL, "no-store")
                    .body(detail.getBytes(StandardCharsets.UTF_8));
        }
    }
}
