package com.zone.lesoongen.platform;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.InputStreamResource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.zone.lesoongen.platform.PlatformLessonController.CreateLesson;
import com.zone.lesoongen.platform.PlatformLessonController.LessonDetail;
import com.zone.lesoongen.platform.PlatformLessonImportService.DocxPreview;
import com.zone.lesoongen.platform.PlatformLessonImportService.SourceDocumentMetadata;


@RestController
@RequestMapping("/api/platform/lessons")
public class PlatformLessonImportController {
    private final PlatformLessonImportService imports;

    public PlatformLessonImportController(PlatformLessonImportService imports) {
        this.imports = imports;
    }

    @PostMapping(value = "/imports/docx/preview", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public DocxPreview preview(@RequestPart("file") MultipartFile file) {
        return imports.preview(file);
    }

    @PostMapping(value = "/imports/docx", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<LessonDetail> importDocx(
            @RequestPart("file") MultipartFile file,
            @RequestParam(required = false, defaultValue = "") String title,
            @RequestParam(required = false, defaultValue = "") String subject,
            @RequestParam(required = false, defaultValue = "") String grade,
            @RequestParam(required = false, defaultValue = "") String topic,
            @RequestParam(required = false) Integer durationMinutes,
            @RequestParam(required = false, defaultValue = "") String content) {
        CreateLesson request = new CreateLesson(title, subject, grade, topic, durationMinutes, content);
        return ResponseEntity.status(HttpStatus.CREATED).body(imports.importDocx(file, request));
    }

    @GetMapping("/{lessonId}/source-document")
    public SourceDocumentMetadata sourceDocument(@PathVariable String lessonId) {
        return imports.sourceDocument(lessonId);
    }

    @GetMapping("/{lessonId}/source-document/file")
    public ResponseEntity<InputStreamResource> sourceDocumentFile(@PathVariable String lessonId) {
        var file = imports.sourceDocumentFile(lessonId);
        MediaType contentType;
        try {
            contentType = MediaType.parseMediaType(file.contentType());
        } catch (IllegalArgumentException ignored) {
            contentType = MediaType.APPLICATION_OCTET_STREAM;
        }
        String disposition = ContentDisposition.attachment()
                .filename(file.originalFilename(), StandardCharsets.UTF_8)
                .build().toString();
        return ResponseEntity.ok()
                .contentType(contentType)
                .contentLength(file.sizeBytes())
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .body(new InputStreamResource(file.stream()));
    }
}
