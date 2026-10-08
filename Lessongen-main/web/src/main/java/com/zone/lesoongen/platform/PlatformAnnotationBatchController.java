package com.zone.lesoongen.platform;

import java.util.List;
import java.util.Map;

import com.zone.lesoongen.platform.PlatformAnnotationService.BatchItemRef;

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
import jakarta.validation.constraints.Size;

@RestController
@RequestMapping("/api/platform/annotations")
public class PlatformAnnotationBatchController {
    private final PlatformAnnotationService annotations;

    public PlatformAnnotationBatchController(PlatformAnnotationService annotations) {
        this.annotations = annotations;
    }

    public record VersionRef(@NotBlank String lessonId, @NotBlank String versionId) {}

    public record StartBatch(
            @Valid @Size(min = 2, max = 20) List<VersionRef> items,
            boolean suggest) {}

    public record StartComparison(
            @Size(min = 2, max = 20) List<@NotBlank String> annotationIds) {}

    @PostMapping("/batches")
    public ResponseEntity<Map<String, Object>> startBatch(@Valid @RequestBody StartBatch input) {
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(annotations.createBatch(
                        input.items().stream()
                                .map(item -> new BatchItemRef(item.lessonId(), item.versionId()))
                                .toList(),
                        input.suggest()));
    }

    @GetMapping("/batches/{batchId}")
    public Map<String, Object> batchState(@PathVariable String batchId) {
        return annotations.batchState(batchId);
    }

    @GetMapping("/batches/{batchId}/result")
    public Map<String, Object> batchResult(@PathVariable String batchId) {
        return annotations.batchResult(batchId);
    }

    @GetMapping("/batches/{batchId}/artifacts/{kind}")
    public ResponseEntity<byte[]> batchArtifact(@PathVariable String batchId, @PathVariable String kind) {
        byte[] bytes = annotations.batchArtifact(batchId, kind);
        return download(bytes, kind, "f1-batch-" + batchId);
    }

    @PostMapping("/comparisons")
    public ResponseEntity<Map<String, Object>> startComparison(@Valid @RequestBody StartComparison input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(annotations.createComparison(input.annotationIds()));
    }

    @GetMapping("/comparisons/{comparisonId}")
    public Map<String, Object> comparisonState(@PathVariable String comparisonId) {
        return annotations.comparisonState(comparisonId);
    }

    @GetMapping("/comparisons/{comparisonId}/result")
    public Map<String, Object> comparisonResult(@PathVariable String comparisonId) {
        return annotations.comparisonResult(comparisonId);
    }

    @GetMapping("/comparisons/{comparisonId}/artifacts/{kind}")
    public ResponseEntity<byte[]> comparisonArtifact(@PathVariable String comparisonId,
            @PathVariable String kind) {
        byte[] bytes = annotations.comparisonArtifact(comparisonId, kind);
        return download(bytes, kind, "f1-comparison-" + comparisonId);
    }

    private static ResponseEntity<byte[]> download(byte[] bytes, String kind, String stem) {
        MediaType type;
        String extension;
        switch (kind) {
            case "quality_docx" -> {
                type = MediaType.parseMediaType(
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
                extension = "docx";
            }
            case "quality_json", "comparison_json", "json" -> {
                type = MediaType.APPLICATION_JSON;
                extension = "json";
            }
            case "comparison_md", "md" -> {
                type = MediaType.parseMediaType("text/markdown;charset=UTF-8");
                extension = "md";
            }
            case "comparison_csv", "csv" -> {
                type = MediaType.parseMediaType("text/csv;charset=UTF-8");
                extension = "csv";
            }
            default -> {
                type = MediaType.APPLICATION_OCTET_STREAM;
                extension = "bin";
            }
        }
        return ResponseEntity.ok()
                .contentType(type)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=" + stem + "-" + kind + "." + extension)
                .body(bytes);
    }
}
