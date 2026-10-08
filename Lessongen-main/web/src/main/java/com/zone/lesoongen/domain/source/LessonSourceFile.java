package com.zone.lesoongen.domain.source;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "lesson_source_file")
public class LessonSourceFile {
    @Id
    @Column(length = 26)
    private String id;
    @Column(name = "job_id", nullable = false, length = 26)
    private String jobId;
    @Column(nullable = false, length = 32)
    private String kind;
    @Column(name = "original_filename", nullable = false, length = 255)
    private String originalFilename;
    @Column(name = "media_type", nullable = false, length = 128)
    private String mediaType;
    @Column(name = "size_bytes", nullable = false)
    private long sizeBytes;
    @Column(nullable = false, length = 64)
    private String sha256;
    @Column(name = "storage_key", nullable = false, length = 512)
    private String storageKey;
    @Enumerated(EnumType.STRING)
    @Column(name = "parse_status", nullable = false, length = 24)
    private ParseStatus parseStatus;
    @Column(name = "parse_warnings", columnDefinition = "json")
    private String parseWarnings;
    @Column(name = "normalized_plan_storage_key", length = 512)
    private String normalizedPlanStorageKey;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected LessonSourceFile() {
    }

    public LessonSourceFile(String id, String jobId, String originalFilename,
            String mediaType, long sizeBytes, String sha256, String storageKey,
            Instant createdAt) {
        this.id = id;
        this.jobId = jobId;
        this.kind = "ORIGINAL_LESSON_DOCX";
        this.originalFilename = originalFilename;
        this.mediaType = mediaType;
        this.sizeBytes = sizeBytes;
        this.sha256 = sha256;
        this.storageKey = storageKey;
        this.parseStatus = ParseStatus.PENDING;
        this.parseWarnings = "[]";
        this.createdAt = createdAt;
    }

    public void updateParse(ParseStatus status, String warnings, String normalizedKey) {
        this.parseStatus = status;
        this.parseWarnings = warnings == null ? "[]" : warnings;
        this.normalizedPlanStorageKey = normalizedKey;
    }

    public String getId() { return id; }
    public String getJobId() { return jobId; }
    public String getKind() { return kind; }
    public String getOriginalFilename() { return originalFilename; }
    public String getMediaType() { return mediaType; }
    public long getSizeBytes() { return sizeBytes; }
    public String getSha256() { return sha256; }
    public String getStorageKey() { return storageKey; }
    public ParseStatus getParseStatus() { return parseStatus; }
    public String getParseWarnings() { return parseWarnings; }
    public String getNormalizedPlanStorageKey() { return normalizedPlanStorageKey; }
    public Instant getCreatedAt() { return createdAt; }
}
