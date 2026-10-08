package com.zone.lesoongen.domain.job;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "lesson_job")
public class LessonJob {
    @Id
    @Column(length = 26)
    private String id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private JobMode mode;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 24)
    private JobStatus status;

    @Version
    @Column(name = "status_version", nullable = false)
    private long statusVersion;

    @Column(nullable = false, length = 64)
    private String subject;
    @Column(nullable = false, length = 64)
    private String grade;
    @Column(nullable = false, length = 255)
    private String topic;
    @Column(name = "duration_minutes", nullable = false)
    @JdbcTypeCode(SqlTypes.SMALLINT)
    private int durationMinutes;
    @Column(name = "request_snapshot", nullable = false, columnDefinition = "json")
    private String requestSnapshot;
    @Column(name = "request_sha256", nullable = false, length = 64)
    private String requestSha256;
    @Column(name = "idempotency_key", length = 128)
    private String idempotencyKey;
    @Column(name = "retry_of_job_id", length = 26)
    private String retryOfJobId;
    @Column(name = "engine_run_id")
    private String engineRunId;
    @Column(name = "current_stage", length = 64)
    private String currentStage;
    @Column(name = "current_round", nullable = false)
    @JdbcTypeCode(SqlTypes.SMALLINT)
    private int currentRound;
    @Column(name = "progress_percent", nullable = false)
    @JdbcTypeCode(SqlTypes.TINYINT)
    private int progressPercent;
    @Column(name = "pipeline_status", length = 24)
    private String pipelineStatus;
    @Column(name = "stop_reason", length = 64)
    private String stopReason;
    @Column(name = "best_version_id", length = 64)
    private String bestVersionId;
    @Column(name = "last_version_id", length = 64)
    private String lastVersionId;
    @Column(name = "model_call_count", nullable = false)
    private int modelCallCount;
    @Column(name = "input_tokens", nullable = false)
    private long inputTokens;
    @Column(name = "output_tokens", nullable = false)
    private long outputTokens;
    @Column(name = "estimated_cost", nullable = false, precision = 12, scale = 6)
    private BigDecimal estimatedCost = BigDecimal.ZERO;
    @Column(name = "error_code", length = 64)
    private String errorCode;
    @Column(name = "error_message", length = 1000)
    private String errorMessage;
    @Column(name = "result_storage_key", length = 512)
    private String resultStorageKey;
    @Column(name = "last_engine_event_sequence", nullable = false)
    private long lastEngineEventSequence;
    @Column(name = "owner_id", length = 26)
    private String ownerId;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
    @Column(name = "started_at")
    private Instant startedAt;
    @Column(name = "finished_at")
    private Instant finishedAt;
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected LessonJob() {
    }

    public LessonJob(String id, JobMode mode, String subject, String grade, String topic,
            int durationMinutes, String requestSnapshot, String requestSha256,
            String idempotencyKey, String retryOfJobId, Clock clock) {
        this.id = id;
        this.mode = mode;
        this.status = JobStatus.QUEUED;
        this.subject = subject;
        this.grade = grade;
        this.topic = topic;
        this.durationMinutes = durationMinutes;
        this.requestSnapshot = requestSnapshot;
        this.requestSha256 = requestSha256;
        this.idempotencyKey = idempotencyKey;
        this.retryOfJobId = retryOfJobId;
        this.currentStage = "queued";
        // MySQL stores DATETIME(6). Canonicalize before returning the first response so an
        // idempotent replay loaded from the database has identical timestamps.
        Instant now = clock.instant().truncatedTo(ChronoUnit.MICROS);
        this.createdAt = now;
        this.updatedAt = now;
    }

    public void transition(JobStatus next, String stage, int round, int progress, Clock clock) {
        if (!status.canTransitionTo(next)) {
            throw new IllegalStateException("illegal job transition: " + status + " -> " + next);
        }
        this.status = next;
        this.currentStage = stage;
        this.currentRound = Math.max(0, round);
        this.progressPercent = Math.max(0, Math.min(100, progress));
        this.updatedAt = clock.instant().truncatedTo(ChronoUnit.MICROS);
        if (startedAt == null && next != JobStatus.QUEUED && next != JobStatus.DISPATCHING) {
            startedAt = updatedAt;
        }
        if (next.isTerminal()) {
            finishedAt = updatedAt;
            progressPercent = 100;
        }
    }

    public void attachEngineRun(String engineRunId, JobStatus next, Clock clock) {
        this.engineRunId = engineRunId;
        transition(next, next == JobStatus.PREPROCESSING ? "docx_security_check" : "run", 0, 5, clock);
    }

    public void applyEngineSnapshot(JobStatus next, String stage, int round, int progress,
            String pipelineStatus, String stopReason, String bestVersionId, String lastVersionId,
            int modelCalls, long inputTokens, long outputTokens, BigDecimal cost,
            String errorCode, String errorMessage, long eventSequence, Clock clock) {
        transition(next, stage, round, progress, clock);
        this.pipelineStatus = pipelineStatus;
        this.stopReason = stopReason;
        this.bestVersionId = bestVersionId;
        this.lastVersionId = lastVersionId;
        this.modelCallCount = modelCalls;
        this.inputTokens = inputTokens;
        this.outputTokens = outputTokens;
        this.estimatedCost = cost == null ? BigDecimal.ZERO : cost;
        this.errorCode = errorCode;
        this.errorMessage = errorMessage;
        this.lastEngineEventSequence = Math.max(this.lastEngineEventSequence, eventSequence);
    }

    public void fail(String code, String message, Clock clock) {
        if (!status.isTerminal()) {
            transition(JobStatus.FAILED, "failed", currentRound, 100, clock);
        }
        this.pipelineStatus = "failed";
        this.errorCode = code;
        this.errorMessage = message;
    }

    public void setResultStorageKey(String resultStorageKey) {
        this.resultStorageKey = resultStorageKey;
    }

    public void releaseIdempotencyKey() {
        this.idempotencyKey = null;
    }

    public String getId() { return id; }
    public JobMode getMode() { return mode; }
    public JobStatus getStatus() { return status; }
    public long getStatusVersion() { return statusVersion; }
    public String getSubject() { return subject; }
    public String getGrade() { return grade; }
    public String getTopic() { return topic; }
    public int getDurationMinutes() { return durationMinutes; }
    public String getRequestSnapshot() { return requestSnapshot; }
    public String getRequestSha256() { return requestSha256; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public String getRetryOfJobId() { return retryOfJobId; }
    public String getEngineRunId() { return engineRunId; }
    public String getCurrentStage() { return currentStage; }
    public int getCurrentRound() { return currentRound; }
    public int getProgressPercent() { return progressPercent; }
    public String getPipelineStatus() { return pipelineStatus; }
    public String getStopReason() { return stopReason; }
    public String getBestVersionId() { return bestVersionId; }
    public String getLastVersionId() { return lastVersionId; }
    public int getModelCallCount() { return modelCallCount; }
    public long getInputTokens() { return inputTokens; }
    public long getOutputTokens() { return outputTokens; }
    public BigDecimal getEstimatedCost() { return estimatedCost; }
    public String getErrorCode() { return errorCode; }
    public String getErrorMessage() { return errorMessage; }
    public String getResultStorageKey() { return resultStorageKey; }
    public long getLastEngineEventSequence() { return lastEngineEventSequence; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getStartedAt() { return startedAt; }
    public Instant getFinishedAt() { return finishedAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
