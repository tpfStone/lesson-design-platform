package com.zone.lesoongen.infrastructure.engine;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.function.Supplier;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.infrastructure.engine.EngineContracts.Accepted;
import com.zone.lesoongen.infrastructure.engine.EngineContracts.Artifact;
import com.zone.lesoongen.infrastructure.engine.EngineContracts.CreateRequest;
import com.zone.lesoongen.infrastructure.engine.EngineContracts.EventPage;
import com.zone.lesoongen.infrastructure.engine.EngineContracts.Result;
import com.zone.lesoongen.infrastructure.engine.EngineContracts.Snapshot;

import org.springframework.http.HttpStatus;

@Component
public class EngineClient {
    private final RestClient client;
    private final ObjectMapper objectMapper;

    public EngineClient(RestClient engineRestClient, ObjectMapper objectMapper) {
        this.client = engineRestClient;
        this.objectMapper = objectMapper;
    }

    public Accepted submitGenerate(CreateRequest request) {
        return retry(() -> require(client.post()
                .uri("/internal/v1/runs/generate")
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(Accepted.class)));
    }

    public Accepted submitOptimize(CreateRequest request, Path document) {
        // Use the MVC multipart form converter. MultipartBodyBuilder also loads
        // Reactive Streams types, which are not present in this MVC-only app.
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        HttpHeaders requestHeaders = new HttpHeaders();
        requestHeaders.setContentType(MediaType.APPLICATION_JSON);
        body.add("request", new HttpEntity<>(requestJson(request), requestHeaders));
        HttpHeaders documentHeaders = new HttpHeaders();
        documentHeaders.setContentType(MediaType.parseMediaType(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"));
        body.add("document", new HttpEntity<>(new FileSystemResource(document), documentHeaders));
        return retry(() -> require(client.post()
                .uri("/internal/v1/runs/optimize")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(body)
                .retrieve()
                .body(Accepted.class)));
    }

    private String requestJson(CreateRequest request) {
        try {
            // FastAPI accepts a JSON string form field alongside the bounded DOCX upload.
            return objectMapper.writeValueAsString(request);
        } catch (JacksonException exception) {
            throw new IllegalStateException("无法序列化 Python 引擎请求", exception);
        }
    }

    public Snapshot snapshot(String engineRunId) {
        return retry(() -> require(client.get()
                .uri("/internal/v1/runs/{id}", engineRunId)
                .retrieve()
                .body(Snapshot.class)));
    }

    public EventPage events(String engineRunId, long afterSequence) {
        return retry(() -> require(client.get()
                .uri(builder -> builder.path("/internal/v1/runs/{id}/events")
                        .queryParam("afterSequence", afterSequence)
                        .build(engineRunId))
                .retrieve()
                .body(EventPage.class)));
    }

    public Optional<Result> result(String engineRunId) {
        try {
            return Optional.ofNullable(retry(() -> client.get()
                    .uri("/internal/v1/runs/{id}/result", engineRunId)
                    .retrieve()
                    .body(Result.class)));
        } catch (RestClientResponseException error) {
            if (error.getStatusCode().value() == 409) {
                return Optional.empty();
            }
            throw translate(error);
        }
    }

    public List<Artifact> artifacts(String engineRunId) {
        Artifact[] response = retry(() -> client.get()
                .uri("/internal/v1/runs/{id}/artifacts", engineRunId)
                .retrieve()
                .body(Artifact[].class));
        return response == null ? List.of() : List.of(response);
    }

    public byte[] download(String engineRunId, String artifactId) {
        try {
            return retry(() -> require(client.get()
                    .uri("/internal/v1/runs/{id}/artifacts/{artifactId}", engineRunId, artifactId)
                    .retrieve()
                    .body(byte[].class)));
        } catch (RestClientResponseException error) {
            // A 404 on an artifact the engine itself listed means the file is
            // gone, not temporarily unavailable. Surface it as a terminal
            // AppException so reconciliation fails the job instead of treating
            // it as a transient sync failure and leaving the job "running"
            // forever. 5xx responses keep the transient path via retry().
            if (error.getStatusCode().value() == HttpStatus.NOT_FOUND.value()) {
                throw new AppException(HttpStatus.BAD_GATEWAY, "ENGINE_ARTIFACT_NOT_FOUND",
                        "Python 引擎产物丢失（" + artifactId + "）");
            }
            throw translate(error);
        }
    }

    private static <T> T retry(Supplier<T> operation) {
        RestClientException latest = null;
        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                return operation.get();
            } catch (RestClientException error) {
                latest = error;
                if (attempt == 3 || !retryable(error)) {
                    throw error;
                }
                try {
                    Thread.sleep(Duration.ofMillis(150L * (1L << (attempt - 1))).toMillis());
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw error;
                }
            }
        }
        throw latest;
    }

    private static boolean retryable(RestClientException error) {
        if (error instanceof RestClientResponseException response) {
            int status = response.getStatusCode().value();
            return status == 502 || status == 503 || status == 504;
        }
        // Connect/read failures are safe to retry because create calls carry the same
        // external_job_id and the Python engine enforces idempotency.
        return true;
    }

    private static <T> T require(T value) {
        if (value == null) {
            throw new AppException(HttpStatus.BAD_GATEWAY, "ENGINE_EMPTY_RESPONSE",
                    "Python 引擎返回了空响应");
        }
        return value;
    }

    public static AppException translate(RestClientException error) {
        if (error instanceof RestClientResponseException response) {
            int status = response.getStatusCode().value();
            String code = switch (status) {
                case 401, 403 -> "ENGINE_AUTH_FAILED";
                case 402 -> "MODEL_BALANCE_EXHAUSTED";
                case 409 -> "ENGINE_IDEMPOTENCY_CONFLICT";
                case 413 -> "DOCX_TOO_LARGE";
                case 415 -> "INVALID_DOCX";
                case 422 -> "ENGINE_INVALID_REQUEST";
                case 429 -> "MODEL_RATE_LIMITED";
                default -> "ENGINE_UNAVAILABLE";
            };
            return new AppException(HttpStatus.BAD_GATEWAY, code,
                    "Python 教案引擎请求失败（" + status + "）");
        }
        return new AppException(HttpStatus.BAD_GATEWAY, "ENGINE_UNAVAILABLE",
                "无法连接 Python 教案引擎");
    }
}
