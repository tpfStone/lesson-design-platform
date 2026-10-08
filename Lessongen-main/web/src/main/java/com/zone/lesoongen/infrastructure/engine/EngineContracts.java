package com.zone.lesoongen.infrastructure.engine;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import tools.jackson.databind.JsonNode;

public final class EngineContracts {
    private EngineContracts() {
    }

    public record LessonInput(
            String mode,
            String subject,
            String grade,
            String topic,
            @JsonProperty("duration_minutes") int durationMinutes,
            @JsonProperty("course_information") String courseInformation,
            @JsonProperty("textbook_version") String textbookVersion,
            @JsonProperty("textbook_content") String textbookContent,
            @JsonProperty("curriculum_standards") List<String> curriculumStandards,
            @JsonProperty("learning_objectives") List<String> learningObjectives,
            @JsonProperty("student_profile") String studentProfile,
            @JsonProperty("class_size") Integer classSize,
            @JsonProperty("available_resources") List<String> availableResources,
            @JsonProperty("additional_requirements") String additionalRequirements,
            @JsonProperty("lesson_style") String lessonStyle,
            @JsonProperty("detail_level") String detailLevel,
            @JsonProperty("optimization_focus") List<String> optimizationFocus,
            @JsonProperty("must_preserve_content") List<String> mustPreserveContent) {
    }

    public record CreateRequest(
            @JsonProperty("contract_version") String contractVersion,
            @JsonProperty("external_job_id") String externalJobId,
            @JsonProperty("request_sha256") String requestSha256,
            LessonInput task) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Accepted(
            @JsonProperty("engine_run_id") String engineRunId,
            @JsonProperty("external_job_id") String externalJobId,
            String status,
            @JsonProperty("created_at") Instant createdAt) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Usage(
            @JsonProperty("model_call_count") int modelCallCount,
            @JsonProperty("input_tokens") long inputTokens,
            @JsonProperty("output_tokens") long outputTokens,
            @JsonProperty("estimated_cost") BigDecimal estimatedCost) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Error(String code, String message) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Snapshot(
            @JsonProperty("engine_run_id") String engineRunId,
            @JsonProperty("external_job_id") String externalJobId,
            String status,
            String stage,
            @JsonProperty("round_index") int roundIndex,
            @JsonProperty("version_id") String versionId,
            @JsonProperty("progress_percent") int progressPercent,
            @JsonProperty("pipeline_status") String pipelineStatus,
            @JsonProperty("stop_reason") String stopReason,
            @JsonProperty("best_version_id") String bestVersionId,
            @JsonProperty("last_version_id") String lastVersionId,
            Usage usage,
            @JsonProperty("last_event_sequence") long lastEventSequence,
            Error error,
            @JsonProperty("updated_at") Instant updatedAt) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Event(
            long sequence,
            @JsonProperty("event_type") String eventType,
            String stage,
            @JsonProperty("round_index") int roundIndex,
            @JsonProperty("version_id") String versionId,
            @JsonProperty("progress_percent") int progressPercent,
            String message,
            @JsonProperty("occurred_at") Instant occurredAt) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record EventPage(
            List<Event> items,
            @JsonProperty("last_sequence") long lastSequence,
            @JsonProperty("has_more") boolean hasMore) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Artifact(
            @JsonProperty("artifact_id") String artifactId,
            String format,
            @JsonProperty("display_name") String displayName,
            @JsonProperty("media_type") String mediaType,
            @JsonProperty("size_bytes") long sizeBytes,
            String sha256,
            String status,
            String error) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Change(
            @JsonProperty("critique_id") String critiqueId,
            @JsonProperty("target_path") String targetPath,
            String summary) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Result(
            @JsonProperty("engine_run_id") String engineRunId,
            @JsonProperty("external_job_id") String externalJobId,
            @JsonProperty("pipeline_status") String pipelineStatus,
            @JsonProperty("stop_reason") String stopReason,
            @JsonProperty("best_version_id") String bestVersionId,
            @JsonProperty("last_version_id") String lastVersionId,
            @JsonProperty("best_lesson_plan") JsonNode bestLessonPlan,
            @JsonProperty("rubric_scores") Map<String, Double> rubricScores,
            @JsonProperty("overall_score") Double overallScore,
            JsonNode optimization,
            JsonNode review,
            @JsonProperty("implemented_changes") List<Change> implementedChanges,
            @JsonProperty("unresolved_issues") List<String> unresolvedIssues,
            @JsonProperty("parse_warnings") List<String> parseWarnings,
            List<Artifact> artifacts) {
    }
}
