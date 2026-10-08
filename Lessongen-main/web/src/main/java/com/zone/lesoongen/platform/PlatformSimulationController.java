package com.zone.lesoongen.platform;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

@RestController
@RequestMapping("/api/platform/lessons/{lessonId}/simulations")
public class PlatformSimulationController {
    private final PlatformSimulationService simulations;

    public PlatformSimulationController(PlatformSimulationService simulations) {
        this.simulations = simulations;
    }

    public record SaveSimulationRequest(
            @NotNull Map<String, Object> sessionRecord,
            @NotBlank @Size(max = 204800) String summaryMarkdown) {}

    public record SaveSimulationResponse(
            String simulationRunId,
            String lessonId,
            String versionId,
            String f3SessionId,
            String status,
            int completedRounds,
            boolean alreadySaved,
            Instant createdAt) {}

    public record SimulationSummary(
            String simulationRunId,
            String lessonId,
            String versionId,
            int versionNumber,
            String f3SessionId,
            String status,
            int completedRounds,
            int materialCount,
            String finalClassroomStatus,
            int historyCount,
            String f3ModelContent,
            Instant startedAt,
            Instant finishedAt,
            Instant createdAt) {}

    public record SimulationDetail(
            String simulationRunId,
            String lessonId,
            String versionId,
            int versionNumber,
            String f4SessionId,
            String f4LessonPlanId,
            String f3SessionId,
            String status,
            int requestedRounds,
            int completedRounds,
            int materialCount,
            String finalClassroomStatus,
            int historyCount,
            String httpChain,
            String f4Provider,
            String f3ModelContent,
            Instant startedAt,
            Instant finishedAt,
            Instant createdAt,
            Map<?, ?> sessionRecord,
            String summaryMarkdown) {}

    @PostMapping
    public ResponseEntity<SaveSimulationResponse> save(@PathVariable String lessonId,
            @Valid @RequestBody SaveSimulationRequest request) {
        SaveSimulationResponse result = simulations.save(lessonId, request);
        return ResponseEntity.status(result.alreadySaved() ? HttpStatus.OK : HttpStatus.CREATED)
                .body(result);
    }

    @GetMapping
    public List<SimulationSummary> list(@PathVariable String lessonId) {
        return simulations.list(lessonId);
    }

    @GetMapping("/{simulationRunId}")
    public SimulationDetail detail(@PathVariable String lessonId,
            @PathVariable String simulationRunId) {
        return simulations.detail(lessonId, simulationRunId);
    }

    @GetMapping("/{simulationRunId}/artifacts/json")
    public ResponseEntity<byte[]> json(@PathVariable String lessonId,
            @PathVariable String simulationRunId) {
        byte[] body = simulations.jsonArtifact(lessonId, simulationRunId)
                .getBytes(StandardCharsets.UTF_8);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=simulation-" + simulationRunId + ".json")
                .body(body);
    }

    @GetMapping("/{simulationRunId}/artifacts/md")
    public ResponseEntity<byte[]> markdown(@PathVariable String lessonId,
            @PathVariable String simulationRunId) {
        byte[] body = simulations.markdownArtifact(lessonId, simulationRunId)
                .getBytes(StandardCharsets.UTF_8);
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("text/markdown;charset=UTF-8"))
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=simulation-" + simulationRunId + "-summary.md")
                .body(body);
    }
}
