package com.zone.lesoongen.domain.artifact;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "lesson_artifact")
public class LessonArtifact {
    @Id
    @Column(length = 26)
    private String id;
    @Column(name = "job_id", nullable = false, length = 26)
    private String jobId;
    @Column(name = "engine_artifact_id", length = 128)
    private String engineArtifactId;
    @Enumerated(EnumType.STRING)
    @Column(name = "artifact_type", nullable = false, length = 40)
    private ArtifactType artifactType;
    @Column(name = "display_name", nullable = false, length = 255)
    private String displayName;
    @Column(name = "media_type", nullable = false, length = 128)
    private String mediaType;
    @Column(name = "storage_key", nullable = false, length = 512)
    private String storageKey;
    @Column(name = "size_bytes", nullable = false)
    private long sizeBytes;
    @Column(nullable = false, length = 64)
    private String sha256;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private ArtifactStatus status;
    @Column(name = "error_message", length = 1000)
    private String errorMessage;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected LessonArtifact() {
    }

    public LessonArtifact(String id, String jobId, String engineArtifactId,
            ArtifactType artifactType, String displayName, String mediaType,
            String storageKey, long sizeBytes, String sha256, ArtifactStatus status,
            String errorMessage, Instant createdAt) {
        this.id = id;
        this.jobId = jobId;
        this.engineArtifactId = engineArtifactId;
        this.artifactType = artifactType;
        this.displayName = displayName;
        this.mediaType = mediaType;
        this.storageKey = storageKey;
        this.sizeBytes = sizeBytes;
        this.sha256 = sha256;
        this.status = status;
        this.errorMessage = errorMessage;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getJobId() { return jobId; }
    public String getEngineArtifactId() { return engineArtifactId; }
    public ArtifactType getArtifactType() { return artifactType; }
    public String getDisplayName() { return displayName; }
    public String getMediaType() { return mediaType; }
    public String getStorageKey() { return storageKey; }
    public long getSizeBytes() { return sizeBytes; }
    public String getSha256() { return sha256; }
    public ArtifactStatus getStatus() { return status; }
    public String getErrorMessage() { return errorMessage; }
    public Instant getCreatedAt() { return createdAt; }
}
