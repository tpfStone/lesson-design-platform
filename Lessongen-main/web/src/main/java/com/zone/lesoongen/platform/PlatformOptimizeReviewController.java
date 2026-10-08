package com.zone.lesoongen.platform;

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
@RequestMapping("/api/platform/lessons/{lessonId}/optimizations/{jobId}/review")
public class PlatformOptimizeReviewController {
    private final PlatformOptimizeService service;
    public PlatformOptimizeReviewController(PlatformOptimizeService service) { this.service = service; }

    public record Submit(@NotBlank String expectedVersionId,
            @NotBlank @Size(max = 100000) String content,
            @NotNull Boolean confirmed) {}

    @GetMapping
    public PlatformOptimizeService.ReviewDraft draft(@PathVariable String lessonId, @PathVariable String jobId) {
        return service.reviewDraft(lessonId, jobId);
    }

    @PostMapping
    public PlatformOptimizeService.ReviewSaved submit(@PathVariable String lessonId, @PathVariable String jobId,
            @Valid @RequestBody Submit body) {
        return service.submitReview(lessonId, jobId, body);
    }
}
