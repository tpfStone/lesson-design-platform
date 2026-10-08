package com.zone.lesoongen.platform;

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

import com.zone.lesoongen.platform.PlatformAnnotationService.AnnotationRun;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

@RestController
@RequestMapping("/api/platform/lessons/{lessonId}/annotations")
public class PlatformAnnotationController {
    private final PlatformAnnotationService annotations;

    public PlatformAnnotationController(PlatformAnnotationService annotations) {
        this.annotations = annotations;
    }

    public record Start(@NotBlank String versionId, boolean suggest) {}

    @PostMapping
    public ResponseEntity<AnnotationRun> start(@PathVariable String lessonId,
            @Valid @RequestBody Start input) {
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(annotations.create(lessonId, input.versionId(), input.suggest()));
    }

    @GetMapping
    public List<AnnotationRun> list(@PathVariable String lessonId) {
        return annotations.list(lessonId);
    }

    @GetMapping("/{id}")
    public AnnotationRun state(@PathVariable String lessonId, @PathVariable String id) {
        return annotations.state(lessonId, id);
    }

    @GetMapping("/{id}/result")
    public Map<?, ?> result(@PathVariable String lessonId, @PathVariable String id) {
        return annotations.result(lessonId, id);
    }

    @GetMapping("/{id}/artifacts/{kind}")
    public ResponseEntity<byte[]> artifact(@PathVariable String lessonId, @PathVariable String id,
            @PathVariable String kind) {
        byte[] bytes = annotations.artifact(lessonId, id, kind);
        MediaType type = switch (kind) {
            case "json" -> MediaType.APPLICATION_JSON;
            case "md" -> MediaType.parseMediaType("text/markdown;charset=UTF-8");
            default -> MediaType.APPLICATION_OCTET_STREAM;
        };
        String extension = switch (kind) {
            case "docx", "docx_annotated" -> "docx";
            default -> kind;
        };
        return ResponseEntity.ok().contentType(type)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=annotation-" + id + "-" + kind + "." + extension)
                .body(bytes);
    }
}
