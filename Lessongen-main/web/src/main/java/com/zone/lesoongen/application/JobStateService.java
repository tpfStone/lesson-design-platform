package com.zone.lesoongen.application;

import java.math.BigDecimal;
import java.time.Clock;
import java.util.EnumSet;
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.zone.lesoongen.config.AppProperties;
import com.zone.lesoongen.domain.job.JobMode;
import com.zone.lesoongen.domain.job.JobStatus;
import com.zone.lesoongen.domain.job.LessonJob;
import com.zone.lesoongen.infrastructure.engine.EngineContracts;
import com.zone.lesoongen.infrastructure.persistence.LessonJobRepository;

@Service
public class JobStateService {
    private static final EnumSet<JobStatus> ACTIVE = EnumSet.of(
            JobStatus.DISPATCHING, JobStatus.PREPROCESSING, JobStatus.RUNNING,
            JobStatus.EXPORTING);

    private final LessonJobRepository jobs;
    private final JobEventService events;
    private final AppProperties properties;
    private final Clock clock;

    public JobStateService(LessonJobRepository jobs, JobEventService events,
            AppProperties properties, Clock clock) {
        this.jobs = jobs;
        this.events = events;
        this.properties = properties;
        this.clock = clock;
    }

    @Transactional
    public Optional<LessonJob> claimNext() {
        Optional<LessonJob> candidate = jobs.lockNextByStatus(JobStatus.QUEUED);
        // Count after acquiring the queue-head row lock. A concurrent dispatcher that
        // waited for the same head then observes the committed active job and cannot
        // overbook the configured real-model concurrency.
        if (candidate.isPresent()
                && jobs.countByStatusIn(ACTIVE) >= properties.maxConcurrentJobs()) {
            return Optional.empty();
        }
        candidate.ifPresent(job -> {
            job.transition(JobStatus.DISPATCHING, "dispatching", 0, 2, clock);
            events.record(job, "job.progress", "正在提交到 Python 教案引擎", null);
        });
        return candidate;
    }

    @Transactional
    public void markSubmitted(String jobId, String engineRunId) {
        LessonJob job = required(jobId);
        JobStatus next = job.getMode() == JobMode.OPTIMIZE
                ? JobStatus.PREPROCESSING : JobStatus.RUNNING;
        job.attachEngineRun(engineRunId, next, clock);
        events.record(job, "job.progress",
                next == JobStatus.PREPROCESSING ? "正在检查原 Word 教案" : "引擎已开始生成教案",
                null);
    }

    @Transactional
    public void applySnapshot(String jobId, EngineContracts.Snapshot snapshot,
            EngineContracts.EventPage page) {
        LessonJob job = required(jobId);
        if (job.getStatus().isTerminal()) {
            return;
        }
        JobStatus next = mapStatus(snapshot.status());
        if (next == JobStatus.QUEUED || next == JobStatus.DISPATCHING) {
            next = job.getStatus();
        }
        EngineContracts.Usage usage = snapshot.usage() == null
                ? new EngineContracts.Usage(0, 0, 0, BigDecimal.ZERO)
                : snapshot.usage();
        EngineContracts.Error error = snapshot.error();
        job.applyEngineSnapshot(next, value(snapshot.stage(), job.getCurrentStage()),
                snapshot.roundIndex(), snapshot.progressPercent(), snapshot.pipelineStatus(),
                snapshot.stopReason(), snapshot.bestVersionId(), snapshot.lastVersionId(),
                usage.modelCallCount(), usage.inputTokens(), usage.outputTokens(),
                usage.estimatedCost(), error == null ? null : error.code(),
                error == null ? null : error.message(), page.lastSequence(), clock);
        for (EngineContracts.Event item : page.items()) {
            events.recordEngine(job.getId(),
                    isTerminalEvent(item) ? "job.terminal" : "job.progress", item);
        }
        if (page.items().isEmpty()) {
            events.record(job, next.isTerminal() ? "job.terminal" : "job.progress",
                    publicMessage(next, snapshot.stage()), "snapshot:" + snapshot.lastEventSequence());
        }
    }

    @Transactional
    public void fail(String jobId, String code, String message) {
        LessonJob job = required(jobId);
        job.fail(code, message, clock);
        events.record(job, "job.terminal", message, null);
    }

    @Transactional
    public void setResultStorageKey(String jobId, String key) {
        required(jobId).setResultStorageKey(key);
    }

    @Transactional(readOnly = true)
    public List<LessonJob> activeJobs() {
        return jobs.findByStatusIn(ACTIVE);
    }

    @Transactional
    public int recoverInterruptedDispatches() {
        int count = 0;
        for (LessonJob job : jobs.findByStatusIn(EnumSet.of(JobStatus.DISPATCHING))) {
            if (job.getEngineRunId() == null) {
                job.fail("SPRING_RESTART_INTERRUPTED",
                        "服务重启中断了任务提交，请从该任务创建新的重试", clock);
                events.record(job, "job.terminal", job.getErrorMessage(), null);
                count += 1;
            }
        }
        return count;
    }

    private LessonJob required(String jobId) {
        return jobs.findById(jobId).orElseThrow(() -> AppException.notFound("任务"));
    }

    private static JobStatus mapStatus(String status) {
        return switch (status) {
            case "queued" -> JobStatus.QUEUED;
            case "preprocessing" -> JobStatus.PREPROCESSING;
            case "running" -> JobStatus.RUNNING;
            case "exporting" -> JobStatus.EXPORTING;
            case "completed" -> JobStatus.COMPLETED;
            case "needs_human" -> JobStatus.NEEDS_HUMAN;
            case "failed" -> JobStatus.FAILED;
            default -> throw new IllegalArgumentException("unknown engine status: " + status);
        };
    }

    private static boolean isTerminalEvent(EngineContracts.Event event) {
        return event.sequence() >= 1_000_000 || "run.terminal".equals(event.eventType());
    }

    private static String publicMessage(JobStatus status, String stage) {
        if (status == JobStatus.COMPLETED) return "教案闭环已完成";
        if (status == JobStatus.NEEDS_HUMAN) return "已形成最佳版本，建议教师复核";
        if (status == JobStatus.FAILED) return "教案任务执行失败";
        return "教案流程正在推进：" + value(stage, "running");
    }

    private static String value(String input, String fallback) {
        return input == null || input.isBlank() ? fallback : input;
    }
}
