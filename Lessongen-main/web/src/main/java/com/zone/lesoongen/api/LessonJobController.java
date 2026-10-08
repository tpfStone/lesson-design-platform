package com.zone.lesoongen.api;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import com.zone.lesoongen.api.dto.LessonRequests;
import com.zone.lesoongen.api.dto.LessonResponses;
import com.zone.lesoongen.application.LessonJobService;
import com.zone.lesoongen.application.LessonResultService;
import com.zone.lesoongen.application.SseBroker;
import com.zone.lesoongen.domain.job.JobMode;
import com.zone.lesoongen.domain.job.JobStatus;

import jakarta.validation.Valid;

@RestController
@RequestMapping("/api/v1/lesson-jobs")
public class LessonJobController {
    private final LessonJobService jobs;
    private final LessonResultService results;
    private final SseBroker sse;

    public LessonJobController(LessonJobService jobs, LessonResultService results,
            SseBroker sse) {
        this.jobs = jobs;
        this.results = results;
        this.sse = sse;
    }

    @PostMapping("/generate")
    public ResponseEntity<LessonResponses.JobAccepted> generate(
            @Valid @RequestBody LessonRequests.Generate request,
            @RequestHeader("Idempotency-Key") String idempotencyKey) {
        return ResponseEntity.accepted().body(jobs.createGenerate(request, idempotencyKey));
    }

    @PostMapping(path = "/optimize", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<LessonResponses.JobAccepted> optimize(
            @Valid @RequestPart("request") LessonRequests.Optimize request,
            @RequestPart("document") MultipartFile document,
            @RequestHeader("Idempotency-Key") String idempotencyKey) {
        return ResponseEntity.accepted().body(
                jobs.createOptimize(request, document, idempotencyKey));
    }

    @GetMapping
    public LessonResponses.JobPage list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "12") int size,
            @RequestParam(required = false) JobMode mode,
            @RequestParam(required = false) JobStatus status) {
        if (page < 0 || size < 1 || size > 50) {
            throw new IllegalArgumentException("page/size 参数超出范围");
        }
        return jobs.list(page, size, mode, status);
    }

    @GetMapping("/{jobId}")
    public LessonResponses.JobDetail detail(@PathVariable String jobId) {
        return jobs.detail(jobs.get(jobId));
    }

    @GetMapping(path = "/{jobId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(@PathVariable String jobId,
            @RequestHeader(name = "Last-Event-ID", defaultValue = "0") long lastEventId) {
        return sse.subscribe(jobId, lastEventId);
    }

    @GetMapping("/{jobId}/result")
    public LessonResponses.LessonResult result(@PathVariable String jobId) {
        return results.result(jobId);
    }

    @GetMapping("/{jobId}/artifacts")
    public java.util.List<LessonResponses.Artifact> artifacts(@PathVariable String jobId) {
        return results.artifacts(jobId);
    }

    @GetMapping("/{jobId}/artifacts/{artifactId}/download")
    public ResponseEntity<Resource> download(@PathVariable String jobId,
            @PathVariable String artifactId) {
        LessonResultService.Download download = results.download(jobId, artifactId);
        ContentDisposition disposition = ContentDisposition.attachment()
                .filename(download.filename(), StandardCharsets.UTF_8)
                .build();
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(download.mediaType()))
                .contentLength(download.sizeBytes())
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
                .header("Digest", "sha-256=" + download.sha256())
                .body(download.resource());
    }
}
