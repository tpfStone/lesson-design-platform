package com.zone.lesoongen.api.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import tools.jackson.databind.JsonNode;
import com.zone.lesoongen.domain.artifact.ArtifactType;
import com.zone.lesoongen.domain.job.JobMode;
import com.zone.lesoongen.domain.job.JobStatus;

public final class LessonResponses {
    private LessonResponses() {
    }

    public record JobLinks(String self, String events, String result, String artifacts) {
        public static JobLinks of(String jobId) {
            String base = "/api/v1/lesson-jobs/" + jobId;
            return new JobLinks(base, base + "/events", base + "/result", base + "/artifacts");
        }
    }

    public record JobAccepted(String jobId, JobStatus status, Instant createdAt, JobLinks links) {
    }

    public record JobUsage(int modelCallCount, long inputTokens, long outputTokens,
            BigDecimal estimatedCost) {
    }

    public record JobSummary(String jobId, JobMode mode, JobStatus status, String subject,
            String grade, String topic, String currentStage, int currentRound,
            int progressPercent, Instant createdAt, Instant finishedAt) {
    }

    public record JobDetail(String jobId, JobMode mode, JobStatus status, String subject,
            String grade, String topic, int durationMinutes, String currentStage,
            int currentRound, int progressPercent, String pipelineStatus, String stopReason,
            String bestVersionId, String lastVersionId, String errorCode, String errorMessage,
            JobUsage usage, Instant createdAt, Instant startedAt, Instant finishedAt,
            Instant updatedAt, JobLinks links) {
    }

    public record JobPage(List<JobSummary> items, int page, int size, long totalElements,
            int totalPages) {
    }

    public record JobEvent(long sequence, String eventType, String stage, Integer roundIndex,
            String versionId, int progressPercent, String message, Instant occurredAt) {
    }

    public record Artifact(String artifactId, ArtifactType type, String displayName,
            String mediaType, long sizeBytes, String sha256, String downloadUrl) {
    }

    public record Change(String summary, String targetPath, List<String> sourceCritiqueIds) {
    }

    public record LessonResult(String jobId, JobStatus status, String stopReason,
            String bestVersionId, String lastVersionId, JsonNode bestLessonPlan,
            Map<String, Double> scores, Double overallScore, String scoreNotice,
            JsonNode optimization, JsonNode review,
            List<Change> changes, List<String> unresolvedIssues,
            List<String> parseWarnings) {
    }
}
