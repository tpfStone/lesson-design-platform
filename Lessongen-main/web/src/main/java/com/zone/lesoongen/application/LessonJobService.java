package com.zone.lesoongen.application;

import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import com.zone.lesoongen.api.dto.LessonRequests;
import com.zone.lesoongen.api.dto.LessonResponses;
import com.zone.lesoongen.application.storage.StoragePort;
import com.zone.lesoongen.application.storage.StoredObject;
import com.zone.lesoongen.config.AppProperties;
import com.zone.lesoongen.domain.artifact.ArtifactStatus;
import com.zone.lesoongen.domain.artifact.ArtifactType;
import com.zone.lesoongen.domain.artifact.LessonArtifact;
import com.zone.lesoongen.domain.job.JobMode;
import com.zone.lesoongen.domain.job.JobStatus;
import com.zone.lesoongen.domain.job.LessonJob;
import com.zone.lesoongen.domain.shared.Ulids;
import com.zone.lesoongen.domain.source.LessonSourceFile;
import com.zone.lesoongen.infrastructure.engine.EngineContracts;
import com.zone.lesoongen.infrastructure.persistence.LessonArtifactRepository;
import com.zone.lesoongen.infrastructure.persistence.LessonJobRepository;
import com.zone.lesoongen.infrastructure.persistence.LessonJobSummaryView;
import com.zone.lesoongen.infrastructure.persistence.LessonSourceFileRepository;

@Service
public class LessonJobService {
    private static final String DOCX_MEDIA =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

    private final LessonJobRepository jobs;
    private final LessonSourceFileRepository sources;
    private final LessonArtifactRepository artifacts;
    private final StoragePort storage;
    private final JobEventService events;
    private final AppProperties properties;
    private final ObjectMapper mapper;
    private final Clock clock;

    public LessonJobService(LessonJobRepository jobs, LessonSourceFileRepository sources,
            LessonArtifactRepository artifacts, StoragePort storage, JobEventService events,
            AppProperties properties, ObjectMapper mapper, Clock clock) {
        this.jobs = jobs;
        this.sources = sources;
        this.artifacts = artifacts;
        this.storage = storage;
        this.events = events;
        this.properties = properties;
        // Records have a stable declared-property order; retaining Boot's configured mapper also
        // preserves one JSON contract across persistence, HTTP, and idempotency hashing.
        this.mapper = mapper;
        this.clock = clock;
    }

    @Transactional
    public LessonResponses.JobAccepted createGenerate(LessonRequests.Generate input,
            String idempotencyKey) {
        validateIdempotencyKey(idempotencyKey);
        EngineContracts.LessonInput engineInput = toEngine(input);
        String snapshot = json(engineInput);
        String hash = sha256(snapshot.getBytes(StandardCharsets.UTF_8));
        Optional<LessonJob> existing = idempotent(idempotencyKey, hash);
        if (existing.isPresent()) {
            return accepted(existing.get());
        }
        String id = Ulids.next(clock);
        LessonJob job = new LessonJob(id, JobMode.GENERATE, clean(input.subject()),
                clean(input.grade()), clean(input.topic()), value(input.durationMinutes(), 45),
                snapshot, hash, idempotencyKey, blankToNull(input.retryOfJobId()), clock);
        jobs.save(job);
        events.record(job, "job.queued", "生成任务已进入队列", null);
        return accepted(job);
    }

    @Transactional
    public LessonResponses.JobAccepted createOptimize(LessonRequests.Optimize input,
            MultipartFile document, String idempotencyKey) {
        validateIdempotencyKey(idempotencyKey);
        validateDocument(document);
        String fileHash = digest(document);
        EngineContracts.LessonInput engineInput = toEngine(input);
        String snapshot = json(engineInput);
        String hash = sha256((snapshot + "\n" + fileHash).getBytes(StandardCharsets.UTF_8));
        Optional<LessonJob> existing = idempotent(idempotencyKey, hash);
        if (existing.isPresent()) {
            return accepted(existing.get());
        }
        String id = Ulids.next(clock);
        LessonJob job = new LessonJob(id, JobMode.OPTIMIZE, clean(input.subject()),
                clean(input.grade()), clean(input.topic()), value(input.durationMinutes(), 45),
                snapshot, hash, idempotencyKey, blankToNull(input.retryOfJobId()), clock);
        jobs.save(job);
        String key = "jobs/" + id + "/input/original.docx";
        try (InputStream stream = document.getInputStream()) {
            StoredObject stored = storage.store(key, stream, properties.maxUploadBytes());
            String originalName = safeFilename(document.getOriginalFilename());
            LessonSourceFile source = new LessonSourceFile(Ulids.next(clock), id, originalName,
                    DOCX_MEDIA, stored.sizeBytes(), stored.sha256(), key, clock.instant());
            sources.save(source);
            artifacts.save(new LessonArtifact(Ulids.next(clock), id, "original-docx",
                    ArtifactType.ORIGINAL_DOCX, originalName, DOCX_MEDIA, key,
                    stored.sizeBytes(), stored.sha256(), ArtifactStatus.AVAILABLE, "",
                    clock.instant()));
        } catch (IOException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "FILE_STORAGE_FAILED",
                    "无法安全保存上传的 Word 文件");
        }
        events.record(job, "job.queued", "优化任务已进入队列", null);
        return accepted(job);
    }

    @Transactional(readOnly = true)
    public LessonJob get(String jobId) {
        return jobs.findById(jobId).orElseThrow(() -> AppException.notFound("任务"));
    }

    @Transactional(readOnly = true)
    public LessonResponses.JobPage list(int page, int size, JobMode mode, JobStatus status) {
        PageRequest request = PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "createdAt"));
        Page<LessonJobSummaryView> result;
        if (mode != null && status != null) {
            result = jobs.findProjectedByModeAndStatus(mode, status, request);
        } else if (mode != null) {
            result = jobs.findProjectedByMode(mode, request);
        } else if (status != null) {
            result = jobs.findProjectedByStatus(status, request);
        } else {
            result = jobs.findAllProjectedBy(request);
        }
        return new LessonResponses.JobPage(result.getContent().stream().map(this::summary).toList(),
                result.getNumber(), result.getSize(), result.getTotalElements(),
                result.getTotalPages());
    }

    public LessonResponses.JobAccepted accepted(LessonJob job) {
        return new LessonResponses.JobAccepted(job.getId(), job.getStatus(), job.getCreatedAt(),
                LessonResponses.JobLinks.of(job.getId()));
    }

    public LessonResponses.JobSummary summary(LessonJob job) {
        return new LessonResponses.JobSummary(job.getId(), job.getMode(), job.getStatus(),
                job.getSubject(), job.getGrade(), job.getTopic(), job.getCurrentStage(),
                job.getCurrentRound(), job.getProgressPercent(), job.getCreatedAt(),
                job.getFinishedAt());
    }

    private LessonResponses.JobSummary summary(LessonJobSummaryView job) {
        return new LessonResponses.JobSummary(job.getId(), job.getMode(), job.getStatus(),
                job.getSubject(), job.getGrade(), job.getTopic(), job.getCurrentStage(),
                job.getCurrentRound(), job.getProgressPercent(), job.getCreatedAt(),
                job.getFinishedAt());
    }

    public LessonResponses.JobDetail detail(LessonJob job) {
        return new LessonResponses.JobDetail(job.getId(), job.getMode(), job.getStatus(),
                job.getSubject(), job.getGrade(), job.getTopic(), job.getDurationMinutes(),
                job.getCurrentStage(), job.getCurrentRound(), job.getProgressPercent(),
                job.getPipelineStatus(), job.getStopReason(), job.getBestVersionId(),
                job.getLastVersionId(), job.getErrorCode(), job.getErrorMessage(),
                new LessonResponses.JobUsage(job.getModelCallCount(), job.getInputTokens(),
                        job.getOutputTokens(), job.getEstimatedCost()),
                job.getCreatedAt(), job.getStartedAt(), job.getFinishedAt(), job.getUpdatedAt(),
                LessonResponses.JobLinks.of(job.getId()));
    }

    private Optional<LessonJob> idempotent(String key, String requestHash) {
        LessonJob existing = jobs.findByIdempotencyKey(key).orElse(null);
        if (existing == null) {
            return Optional.empty();
        }
        if (Duration.between(existing.getCreatedAt(), clock.instant()).compareTo(Duration.ofHours(24)) > 0) {
            existing.releaseIdempotencyKey();
            jobs.flush();
            return Optional.empty();
        }
        if (!Objects.equals(existing.getRequestSha256(), requestHash)) {
            throw new AppException(HttpStatus.CONFLICT, "IDEMPOTENCY_KEY_CONFLICT",
                    "该 Idempotency-Key 已用于另一份请求");
        }
        return Optional.of(existing);
    }

    private static void validateIdempotencyKey(String value) {
        if (value == null || value.length() < 16 || value.length() > 128
                || value.chars().anyMatch(character -> Character.isWhitespace(character)
                        || Character.isISOControl(character))) {
            throw new AppException(HttpStatus.BAD_REQUEST, "INVALID_IDEMPOTENCY_KEY",
                    "Idempotency-Key 必须为 16–128 位且不能包含空白字符");
        }
    }

    private EngineContracts.LessonInput toEngine(LessonRequests.Generate input) {
        return new EngineContracts.LessonInput("generate", clean(input.subject()),
                clean(input.grade()), clean(input.topic()), value(input.durationMinutes(), 45),
                text(input.courseInformation()), text(input.textbookVersion()),
                text(input.textbookContent()), list(input.curriculumStandards()),
                list(input.learningObjectives()), text(input.studentProfile()), input.classSize(),
                list(input.availableResources()), text(input.additionalRequirements()),
                value(input.lessonStyle(), "choose_the_best_fit_for_this_topic"),
                value(input.detailLevel(), "showcase"), List.of(), List.of());
    }

    private EngineContracts.LessonInput toEngine(LessonRequests.Optimize input) {
        return new EngineContracts.LessonInput("optimize", clean(input.subject()),
                clean(input.grade()), clean(input.topic()), value(input.durationMinutes(), 45),
                text(input.courseInformation()), text(input.textbookVersion()),
                text(input.textbookContent()), list(input.curriculumStandards()),
                list(input.learningObjectives()), text(input.studentProfile()), input.classSize(),
                list(input.availableResources()), text(input.additionalRequirements()),
                value(input.lessonStyle(), "choose_the_best_fit_for_this_topic"),
                value(input.detailLevel(), "showcase"), list(input.optimizationFocus()),
                list(input.mustPreserveContent()));
    }

    private void validateDocument(MultipartFile file) {
        String name = safeFilename(file.getOriginalFilename());
        if (file.isEmpty() || !name.toLowerCase().endsWith(".docx")) {
            throw new AppException(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "INVALID_DOCX",
                    "请选择真正的 .docx 教案文件");
        }
        if (file.getSize() > properties.maxUploadBytes()) {
            throw new AppException(HttpStatus.PAYLOAD_TOO_LARGE, "DOCX_TOO_LARGE",
                    "Word 文件超过 20 MiB 限制");
        }
        try (InputStream stream = file.getInputStream()) {
            byte[] magic = stream.readNBytes(4);
            if (magic.length != 4 || magic[0] != 'P' || magic[1] != 'K'
                    || magic[2] != 3 || magic[3] != 4) {
                throw new AppException(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "INVALID_DOCX",
                        "文件不是有效的 OOXML Word 包");
            }
        } catch (IOException error) {
            throw new AppException(HttpStatus.BAD_REQUEST, "DOCX_READ_FAILED", "无法读取上传文件");
        }
    }

    private String digest(MultipartFile file) {
        try (InputStream stream = file.getInputStream()) {
            return sha256(stream.readAllBytes());
        } catch (IOException error) {
            throw new AppException(HttpStatus.BAD_REQUEST, "DOCX_READ_FAILED", "无法读取上传文件");
        }
    }

    private String json(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (JacksonException error) {
            throw new IllegalStateException("cannot serialize canonical request", error);
        }
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static String safeFilename(String input) {
        String value = input == null ? "lesson.docx" : input.replace('\\', '/');
        value = value.substring(value.lastIndexOf('/') + 1).replaceAll("[\\r\\n\"]", "_").trim();
        return value.isBlank() ? "lesson.docx" : value.substring(0, Math.min(value.length(), 200));
    }

    private static String clean(String value) { return value == null ? "" : value.trim(); }
    private static String text(String value) { return value == null ? "" : value.trim(); }
    private static int value(Integer value, int fallback) { return value == null ? fallback : value; }
    private static String value(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }
    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }
    private static List<String> list(List<String> values) {
        return values == null ? List.of() : values.stream().filter(Objects::nonNull)
                .map(String::trim).filter(item -> !item.isBlank()).toList();
    }
}
