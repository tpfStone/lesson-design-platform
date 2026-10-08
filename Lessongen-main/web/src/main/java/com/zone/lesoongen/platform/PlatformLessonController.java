package com.zone.lesoongen.platform;

import java.time.Instant;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

@RestController
@RequestMapping("/api/platform/lessons")
public class PlatformLessonController {
    private final PlatformLessonService lessons;
    private final PlatformLessonDocumentService documents;

    public PlatformLessonController(PlatformLessonService lessons, PlatformLessonDocumentService documents) {
        this.lessons = lessons;
        this.documents = documents;
    }

    public record CreateLesson(
            @NotBlank @Size(max = 255) String title,
            @NotBlank @Size(max = 100) String subject,
            @NotBlank @Size(max = 100) String grade,
            @NotBlank @Size(max = 255) String topic,
            @Min(5) @Max(240) Integer durationMinutes,
            @NotBlank @Size(max = 100000) String content) {}

    public record NewVersion(
            @NotNull String expectedVersionId,
            @NotBlank @Size(max = 100000) String content) {}

    public record LessonSummary(String id, String title, String subject, String grade,
            String topic, Integer durationMinutes, String currentVersionId, Instant updatedAt) {}

    public record LessonVersion(String id, String lessonId, String parentVersionId,
            int versionNumber, String content, String contentSha256,
            String sourceModule, String nativeReference, Instant createdAt) {}

    public record LessonDetail(LessonSummary lesson, List<LessonVersion> versions) {}

    @PostMapping
    public ResponseEntity<LessonDetail> create(@Valid @RequestBody CreateLesson request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(lessons.create(request));
    }

    @GetMapping
    public List<LessonSummary> list() {
        return lessons.list();
    }

    @GetMapping("/{lessonId}")
    public LessonDetail detail(@PathVariable String lessonId) {
        return lessons.detail(lessonId);
    }

    @GetMapping("/{lessonId}/versions/{versionId}/document")
    public PlatformLessonDocumentService.VersionDocument document(
            @PathVariable String lessonId, @PathVariable String versionId) {
        return documents.get(lessonId, versionId);
    }

    @PostMapping("/{lessonId}/versions")
    public ResponseEntity<LessonDetail> addVersion(@PathVariable String lessonId,
            @Valid @RequestBody NewVersion request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(lessons.addVersion(lessonId, request));
    }
}
