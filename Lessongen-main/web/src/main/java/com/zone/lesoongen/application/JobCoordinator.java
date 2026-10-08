package com.zone.lesoongen.application;

import java.util.List;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import com.zone.lesoongen.application.storage.StoragePort;
import com.zone.lesoongen.domain.job.JobMode;
import com.zone.lesoongen.domain.job.LessonJob;
import com.zone.lesoongen.domain.source.LessonSourceFile;
import com.zone.lesoongen.infrastructure.engine.EngineClient;
import com.zone.lesoongen.infrastructure.engine.EngineContracts;
import com.zone.lesoongen.infrastructure.persistence.LessonSourceFileRepository;

@Component
@ConditionalOnProperty(name = "app.scheduling-enabled", havingValue = "true", matchIfMissing = true)
public class JobCoordinator {
    private static final Logger log = LoggerFactory.getLogger(JobCoordinator.class);

    /** Consecutive transient reconcile failures before a job is failed outright. */
    private static final int MAX_CONSECUTIVE_RECONCILE_FAILURES = 15;

    private final JobStateService states;
    private final EngineClient engine;
    private final LessonSourceFileRepository sources;
    private final StoragePort storage;
    private final ArtifactIngestionService ingestion;
    private final ObjectMapper mapper;
    private final Map<String, Integer> reconcileFailures = new HashMap<>();

    public JobCoordinator(JobStateService states, EngineClient engine,
            LessonSourceFileRepository sources, StoragePort storage,
            ArtifactIngestionService ingestion, ObjectMapper mapper) {
        this.states = states;
        this.engine = engine;
        this.sources = sources;
        this.storage = storage;
        this.ingestion = ingestion;
        this.mapper = mapper;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void recoverAfterRestart() {
        int recovered = states.recoverInterruptedDispatches();
        if (recovered > 0) {
            log.warn("marked {} interrupted dispatches as failed during startup", recovered);
        }
    }

    @Scheduled(fixedDelayString = "${app.dispatch-delay-ms:1000}")
    public void dispatch() {
        states.claimNext().ifPresent(job -> {
            try {
                EngineContracts.CreateRequest request = new EngineContracts.CreateRequest(
                        "1", job.getId(), job.getRequestSha256(),
                        mapper.readValue(job.getRequestSnapshot(), EngineContracts.LessonInput.class));
                EngineContracts.Accepted accepted;
                if (job.getMode() == JobMode.GENERATE) {
                    accepted = engine.submitGenerate(request);
                } else {
                    LessonSourceFile source = sources.findByJobIdAndKind(job.getId(),
                                    "ORIGINAL_LESSON_DOCX")
                            .orElseThrow(() -> AppException.notFound("原 Word 文件"));
                    accepted = engine.submitOptimize(request, storage.localPath(source.getStorageKey()));
                }
                states.markSubmitted(job.getId(), accepted.engineRunId());
            } catch (JacksonException error) {
                states.fail(job.getId(), "REQUEST_SNAPSHOT_INVALID", "任务快照无法解析");
            } catch (AppException error) {
                states.fail(job.getId(), error.code(), error.getMessage());
            } catch (RestClientException error) {
                AppException translated = EngineClient.translate(error);
                states.fail(job.getId(), translated.code(), translated.getMessage());
            } catch (LinkageError error) {
                // A missing runtime class is an Error, not an Exception. Without
                // this boundary the scheduler logs it but leaves the job stuck
                // in DISPATCHING and blocks the single-job queue indefinitely.
                log.error("engine submission linkage failure for job {}", job.getId(), error);
                states.fail(job.getId(), "ENGINE_RUNTIME_DEPENDENCY_MISSING",
                        "教案引擎提交组件缺少运行依赖，请重启修复后的服务并创建新任务");
            } catch (Exception error) {
                log.error("unexpected engine submission failure for job {} ({})",
                        job.getId(), error.getClass().getSimpleName());
                states.fail(job.getId(), "ENGINE_SUBMISSION_FAILED",
                        "引擎提交失败，请稍后从该任务创建新的重试");
            }
        });
    }

    @Scheduled(fixedDelayString = "${app.reconcile-delay-ms:2000}")
    public void reconcile() {
        List<LessonJob> active = states.activeJobs();
        for (LessonJob job : active) {
            if (job.getEngineRunId() == null) {
                continue;
            }
            try {
                EngineContracts.Snapshot snapshot = engine.snapshot(job.getEngineRunId());
                EngineContracts.EventPage events = fetchEvents(job);
                if (isTerminal(snapshot.status())) {
                    ingestion.ingestTerminal(job, snapshot);
                }
                states.applySnapshot(job.getId(), snapshot, events);
                reconcileFailures.remove(job.getId());
            } catch (AppException error) {
                reconcileFailures.remove(job.getId());
                states.fail(job.getId(), error.code(), error.getMessage());
            } catch (RestClientException error) {
                log.warn("engine reconciliation temporarily failed for job {}: {}",
                        job.getId(), error.getClass().getSimpleName());
                failAfterRepeatedTransientErrors(job);
            } catch (Exception error) {
                log.error("job reconciliation failed for {}", job.getId(), error);
                failAfterRepeatedTransientErrors(job);
            }
        }
    }

    /**
     * A transient engine sync failure must not leave a job "running" forever:
     * after {@link #MAX_CONSECUTIVE_RECONCILE_FAILURES} consecutive transient
     * failures the job is failed so the user gets a terminal, actionable state
     * instead of an endless spinner.
     */
    private void failAfterRepeatedTransientErrors(LessonJob job) {
        int failures = reconcileFailures.merge(job.getId(), 1, Integer::sum);
        if (failures >= MAX_CONSECUTIVE_RECONCILE_FAILURES) {
            reconcileFailures.remove(job.getId());
            log.error("failing job {} after {} consecutive transient reconcile failures",
                    job.getId(), failures);
            states.fail(job.getId(), "ENGINE_SYNC_FAILED",
                    "引擎状态同步持续失败，任务已终止，请查看恢复产物或创建新的重试");
        }
    }

    private static boolean isTerminal(String status) {
        return "completed".equals(status) || "needs_human".equals(status)
                || "failed".equals(status);
    }

    private EngineContracts.EventPage fetchEvents(LessonJob job) {
        long cursor = job.getLastEngineEventSequence();
        List<EngineContracts.Event> collected = new ArrayList<>();
        boolean hasMore;
        int pages = 0;
        do {
            EngineContracts.EventPage page = engine.events(job.getEngineRunId(), cursor);
            collected.addAll(page.items());
            hasMore = page.hasMore();
            if (hasMore && page.lastSequence() <= cursor) {
                throw new IllegalStateException("engine event cursor did not advance");
            }
            cursor = page.lastSequence();
            pages += 1;
        } while (hasMore && pages < 100);
        if (hasMore) {
            throw new IllegalStateException("engine event backlog exceeded 100 pages");
        }
        return new EngineContracts.EventPage(collected, cursor, false);
    }

}
