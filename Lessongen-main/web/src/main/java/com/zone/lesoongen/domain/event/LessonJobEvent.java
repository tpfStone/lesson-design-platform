package com.zone.lesoongen.domain.event;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "lesson_job_event", uniqueConstraints = {
        @UniqueConstraint(name = "uq_event_sequence", columnNames = {"job_id", "sequence_no"}),
        @UniqueConstraint(name = "uq_event_engine_key", columnNames = {"job_id", "engine_event_key"})
})
public class LessonJobEvent {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "job_id", nullable = false, length = 26)
    private String jobId;
    @Column(name = "sequence_no", nullable = false)
    private long sequenceNo;
    @Column(name = "event_type", nullable = false, length = 64)
    private String eventType;
    @Column(nullable = false, length = 64)
    private String stage;
    @Column(name = "round_index")
    @JdbcTypeCode(SqlTypes.SMALLINT)
    private Integer roundIndex;
    @Column(name = "version_id", length = 64)
    private String versionId;
    @Column(name = "progress_percent", nullable = false)
    @JdbcTypeCode(SqlTypes.TINYINT)
    private int progressPercent;
    @Column(nullable = false, length = 500)
    private String message;
    @Column(name = "event_payload", columnDefinition = "json")
    private String eventPayload;
    @Column(name = "engine_event_key", length = 128)
    private String engineEventKey;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected LessonJobEvent() {
    }

    public LessonJobEvent(String jobId, long sequenceNo, String eventType, String stage,
            Integer roundIndex, String versionId, int progressPercent, String message,
            String eventPayload, String engineEventKey, Instant createdAt) {
        this.jobId = jobId;
        this.sequenceNo = sequenceNo;
        this.eventType = eventType;
        this.stage = stage;
        this.roundIndex = roundIndex;
        this.versionId = versionId;
        this.progressPercent = progressPercent;
        this.message = message;
        this.eventPayload = eventPayload;
        this.engineEventKey = engineEventKey;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public String getJobId() { return jobId; }
    public long getSequenceNo() { return sequenceNo; }
    public String getEventType() { return eventType; }
    public String getStage() { return stage; }
    public Integer getRoundIndex() { return roundIndex; }
    public String getVersionId() { return versionId; }
    public int getProgressPercent() { return progressPercent; }
    public String getMessage() { return message; }
    public String getEventPayload() { return eventPayload; }
    public String getEngineEventKey() { return engineEventKey; }
    public Instant getCreatedAt() { return createdAt; }
}
