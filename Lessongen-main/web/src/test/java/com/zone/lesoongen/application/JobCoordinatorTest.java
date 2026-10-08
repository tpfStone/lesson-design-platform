package com.zone.lesoongen.application;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import com.zone.lesoongen.application.storage.StoragePort;
import com.zone.lesoongen.domain.job.JobMode;
import com.zone.lesoongen.domain.job.LessonJob;
import com.zone.lesoongen.domain.source.LessonSourceFile;
import com.zone.lesoongen.infrastructure.engine.EngineClient;
import com.zone.lesoongen.infrastructure.engine.EngineContracts;
import com.zone.lesoongen.infrastructure.persistence.LessonSourceFileRepository;

import tools.jackson.databind.ObjectMapper;

class JobCoordinatorTest {
    @BeforeAll
    static void prepareJvmTempDirectory() throws Exception {
        Files.createDirectories(Path.of("target", "test-tmp"));
    }

    @Test
    void missingRuntimeClassFailsClaimedJobInsteadOfLeavingItDispatching() throws Exception {
        JobStateService states = mock(JobStateService.class);
        EngineClient engine = mock(EngineClient.class);
        LessonSourceFileRepository sources = mock(LessonSourceFileRepository.class);
        StoragePort storage = mock(StoragePort.class);
        ArtifactIngestionService ingestion = mock(ArtifactIngestionService.class);
        ObjectMapper mapper = new ObjectMapper();
        LessonJob job = mock(LessonJob.class);
        LessonSourceFile source = mock(LessonSourceFile.class);
        Path document = Path.of("original.docx");
        String jobId = "01J00000000000000000000000";
        EngineContracts.LessonInput input = new EngineContracts.LessonInput(
                "optimize", "语文", "八年级", "《背影》", 45,
                "", "", "", List.of(), List.of(), "", null, List.of(), "",
                "choose_the_best_fit_for_this_topic", "showcase", List.of(), List.of());

        when(states.claimNext()).thenReturn(Optional.of(job));
        when(job.getId()).thenReturn(jobId);
        when(job.getMode()).thenReturn(JobMode.OPTIMIZE);
        when(job.getRequestSha256()).thenReturn("a".repeat(64));
        when(job.getRequestSnapshot()).thenReturn(mapper.writeValueAsString(input));
        when(sources.findByJobIdAndKind(jobId, "ORIGINAL_LESSON_DOCX"))
                .thenReturn(Optional.of(source));
        when(source.getStorageKey()).thenReturn("jobs/" + jobId + "/input/original.docx");
        when(storage.localPath(source.getStorageKey())).thenReturn(document);
        when(engine.submitOptimize(any(EngineContracts.CreateRequest.class), eq(document)))
                .thenThrow(new NoClassDefFoundError("org/reactivestreams/Publisher"));

        new JobCoordinator(states, engine, sources, storage, ingestion, mapper).dispatch();

        verify(states).fail(eq(jobId), eq("ENGINE_RUNTIME_DEPENDENCY_MISSING"), any(String.class));
    }

    @Test
    void reconcileFailsJobAfterRepeatedTransientSyncFailures() {
        JobStateService states = mock(JobStateService.class);
        EngineClient engine = mock(EngineClient.class);
        LessonSourceFileRepository sources = mock(LessonSourceFileRepository.class);
        StoragePort storage = mock(StoragePort.class);
        ArtifactIngestionService ingestion = mock(ArtifactIngestionService.class);
        ObjectMapper mapper = new ObjectMapper();
        LessonJob job = mock(LessonJob.class);
        String jobId = "01J00000000000000000000001";

        when(job.getId()).thenReturn(jobId);
        when(job.getEngineRunId()).thenReturn("run-001");
        when(states.activeJobs()).thenReturn(List.of(job));
        when(engine.snapshot("run-001"))
                .thenThrow(new org.springframework.web.client.ResourceAccessException(
                        "engine unreachable"));

        JobCoordinator coordinator = new JobCoordinator(
                states, engine, sources, storage, ingestion, mapper);
        for (int attempt = 0; attempt < 15; attempt++) {
            coordinator.reconcile();
        }

        verify(states).fail(eq(jobId), eq("ENGINE_SYNC_FAILED"), any(String.class));
    }
}
