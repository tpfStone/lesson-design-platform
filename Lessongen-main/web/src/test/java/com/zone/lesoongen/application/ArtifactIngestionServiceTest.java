package com.zone.lesoongen.application;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.lang.reflect.Proxy;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.zone.lesoongen.application.storage.StoragePort;
import com.zone.lesoongen.domain.job.LessonJob;
import com.zone.lesoongen.domain.job.JobMode;
import com.zone.lesoongen.domain.job.JobStatus;
import com.zone.lesoongen.infrastructure.engine.EngineClient;
import com.zone.lesoongen.infrastructure.engine.EngineContracts;
import com.zone.lesoongen.infrastructure.persistence.LessonArtifactRepository;
import com.zone.lesoongen.infrastructure.persistence.LessonSourceFileRepository;

import tools.jackson.databind.ObjectMapper;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

class ArtifactIngestionServiceTest {
    private StubEngineClient engine;
    private LessonArtifactRepository artifacts;
    private ArtifactIngestionService service;
    private LessonJob job;

    @BeforeEach
    void setUp() {
        engine = new StubEngineClient();
        artifacts = emptyRepository(LessonArtifactRepository.class);
        Clock clock = Clock.fixed(Instant.parse("2026-09-11T07:00:00Z"), ZoneOffset.UTC);
        service = new ArtifactIngestionService(engine, (StoragePort) null, artifacts,
                (LessonSourceFileRepository) null, (JobStateService) null,
                new ObjectMapper(), clock);
        job = new LessonJob("01J00000000000000000000000", JobMode.GENERATE,
                "化学", "高二", "官能团", 45, "{}", "a".repeat(64),
                "artifact-ingestion-test", null, clock);
        job.transition(JobStatus.DISPATCHING, "dispatching", 0, 2, clock);
        job.attachEngineRun("run-001", JobStatus.RUNNING, clock);
        job.setResultStorageKey("already-stored");
    }

    @Test
    void completedSnapshotCannotBecomeAWebSuccessWithoutStructuredResult() {
        engine.result = Optional.empty();

        AppException error = assertThrows(AppException.class,
                () -> service.ingestTerminal(job, snapshot("completed")));

        assertEquals("ENGINE_RESULT_MISSING", error.code());
    }

    @Test
    void completedSnapshotCannotBecomeAWebSuccessWithoutWordArtifact() {
        engine.result = Optional.of(result());
        engine.artifacts = List.of();

        AppException error = assertThrows(AppException.class,
                () -> service.ingestTerminal(job, snapshot("completed")));

        assertEquals("ENGINE_WORD_MISSING", error.code());
    }

    private static EngineContracts.Snapshot snapshot(String status) {
        return new EngineContracts.Snapshot("run-001", "01J00000000000000000000000",
                status, "finalize", 2, "v1", 100, status, "quality_passed",
                "v1", "v1", new EngineContracts.Usage(8, 1000, 500, BigDecimal.ONE),
                1_000_000, null, Instant.parse("2026-09-11T07:05:00Z"));
    }

    private static EngineContracts.Result result() {
        return new EngineContracts.Result("run-001", "01J00000000000000000000000",
                "completed", "quality_passed", "v1", "v1",
                new ObjectMapper().createObjectNode(), Map.of(), 8.0, null, null,
                List.of(), List.of(), List.of(), List.of());
    }

    @SuppressWarnings("unchecked")
    private static <T> T emptyRepository(Class<T> type) {
        return (T) Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[] {type},
                (proxy, method, args) -> {
                    Class<?> result = method.getReturnType();
                    if (result == boolean.class) return false;
                    if (result == long.class) return 0L;
                    if (result == int.class) return 0;
                    if (Optional.class.isAssignableFrom(result)) return Optional.empty();
                    if (List.class.isAssignableFrom(result)) return List.of();
                    return null;
                });
    }

    private static final class StubEngineClient extends EngineClient {
        private Optional<EngineContracts.Result> result = Optional.empty();
        private List<EngineContracts.Artifact> artifacts = List.of();

        private StubEngineClient() {
            super(RestClient.builder().requestFactory(new SimpleClientHttpRequestFactory()).build(),
                    new ObjectMapper());
        }

        @Override
        public Optional<EngineContracts.Result> result(String engineRunId) {
            return result;
        }

        @Override
        public List<EngineContracts.Artifact> artifacts(String engineRunId) {
            return artifacts;
        }
    }
}
