package com.zone.lesoongen.platform;

import java.util.List;
import java.util.UUID;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.zone.lesoongen.api.dto.LessonResponses;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

@RestController
@RequestMapping("/api/platform/lessons/{lessonId}/optimizations")
public class PlatformOptimizeController {
    private final PlatformOptimizeService service;

    public PlatformOptimizeController(PlatformOptimizeService service) { this.service = service; }

    public record Start(@NotBlank String versionId, @NotNull UUID requestKey,
            @Size(max = 64) String subject, @Size(max = 64) String grade,
            @Size(max = 255) String topic, Integer durationMinutes,
            @Size(max = 4000) String courseInformation,
            @Size(max = 255) String textbookVersion,
            @Size(max = 30000) String textbookContent,
            @Size(max = 50) List<@NotBlank @Size(max = 1000) String> curriculumStandards,
            @Size(max = 20) List<@NotBlank @Size(max = 1000) String> learningObjectives,
            @Size(max = 8000) String studentProfile,
            @Min(1) @Max(200) Integer classSize,
            @Size(max = 50) List<@NotBlank @Size(max = 500) String> availableResources,
            @Size(max = 8000) String additionalRequirements,
            @Pattern(regexp = "choose_the_best_fit_for_this_topic|inquiry_through_cognitive_conflict|authentic_problem_driven|dialogue_and_discussion|project_or_task_based|close_reading_and_evidence") String lessonStyle,
            @Pattern(regexp = "standard|showcase") String detailLevel,
            @Size(max = 20) List<@NotBlank @Size(max = 1000) String> optimizationFocus,
            @Size(max = 20) List<@NotBlank @Size(max = 2000) String> mustPreserveContent) {}

    @PostMapping
    public LessonResponses.JobAccepted start(@PathVariable String lessonId, @Valid @RequestBody Start input) {
        return service.start(lessonId, input);
    }

    @GetMapping("/{jobId}")
    public PlatformOptimizeService.Link link(@PathVariable String lessonId, @PathVariable String jobId) {
        return service.link(lessonId, jobId);
    }

    @PostMapping("/{jobId}/save")
    public PlatformOptimizeService.Saved save(@PathVariable String lessonId, @PathVariable String jobId) {
        return service.save(lessonId, jobId);
    }
}
