package com.zone.lesoongen.application;

import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.core.io.InputStreamResource;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import tools.jackson.databind.ObjectMapper;
import com.zone.lesoongen.api.dto.LessonResponses;
import com.zone.lesoongen.application.storage.StoragePort;
import com.zone.lesoongen.domain.artifact.ArtifactStatus;
import com.zone.lesoongen.domain.artifact.LessonArtifact;
import com.zone.lesoongen.domain.job.LessonJob;
import com.zone.lesoongen.infrastructure.engine.EngineContracts;
import com.zone.lesoongen.infrastructure.persistence.LessonArtifactRepository;
import com.zone.lesoongen.infrastructure.persistence.LessonJobRepository;

@Service
public class LessonResultService {
    private final LessonJobRepository jobs;
    private final LessonArtifactRepository artifacts;
    private final StoragePort storage;
    private final ObjectMapper mapper;

    public LessonResultService(LessonJobRepository jobs, LessonArtifactRepository artifacts,
            StoragePort storage, ObjectMapper mapper) {
        this.jobs = jobs;
        this.artifacts = artifacts;
        this.storage = storage;
        this.mapper = mapper;
    }

    @Transactional(readOnly = true)
    public LessonResponses.LessonResult result(String jobId) {
        LessonJob job = requiredJob(jobId);
        if (job.getResultStorageKey() == null || !storage.exists(job.getResultStorageKey())) {
            throw new AppException(HttpStatus.CONFLICT, "RESULT_NOT_READY",
                    "任务尚未形成可展示的最佳版本");
        }
        try (InputStream input = storage.open(job.getResultStorageKey())) {
            EngineContracts.Result result = mapper.readValue(input, EngineContracts.Result.class);
            List<LessonResponses.Change> changes = safe(result.implementedChanges()).stream()
                    .map(item -> new LessonResponses.Change(item.summary(), item.targetPath(),
                            List.of(item.critiqueId())))
                    .toList();
            return new LessonResponses.LessonResult(jobId, job.getStatus(), result.stopReason(),
                    result.bestVersionId(), result.lastVersionId(), result.bestLessonPlan(),
                    publicScores(result.rubricScores()), result.overallScore(),
                    "内部质量信号，不代表正式教学效果评价", result.optimization(), result.review(), changes,
                    safe(result.unresolvedIssues()), safe(result.parseWarnings()));
        } catch (IOException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "RESULT_READ_FAILED",
                    "无法读取结构化教案结果");
        }
    }

    @Transactional(readOnly = true)
    public List<LessonResponses.Artifact> artifacts(String jobId) {
        requiredJob(jobId);
        return artifacts.findByJobIdOrderByCreatedAtAsc(jobId).stream()
                .filter(item -> item.getStatus() == ArtifactStatus.AVAILABLE)
                .map(item -> new LessonResponses.Artifact(item.getId(), item.getArtifactType(),
                        item.getDisplayName(), item.getMediaType(), item.getSizeBytes(),
                        item.getSha256(), "/api/v1/lesson-jobs/" + jobId + "/artifacts/"
                                + item.getId() + "/download"))
                .toList();
    }

    @Transactional(readOnly = true)
    public Download download(String jobId, String artifactId) {
        requiredJob(jobId);
        LessonArtifact item = artifacts.findByIdAndJobId(artifactId, jobId)
                .orElseThrow(() -> AppException.notFound("产物"));
        if (item.getStatus() != ArtifactStatus.AVAILABLE || !storage.exists(item.getStorageKey())) {
            throw AppException.notFound("产物文件");
        }
        try {
            verify(item);
            return new Download(new InputStreamResource(storage.open(item.getStorageKey())),
                    item.getDisplayName(), item.getMediaType(), item.getSizeBytes(), item.getSha256());
        } catch (IOException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "ARTIFACT_READ_FAILED",
                    "无法读取教案文件");
        }
    }

    private void verify(LessonArtifact item) throws IOException {
        long total = 0;
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
        try (InputStream input = storage.open(item.getStorageKey())) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) >= 0) {
                total += count;
                digest.update(buffer, 0, count);
            }
        }
        String actual = HexFormat.of().formatHex(digest.digest());
        if (total != item.getSizeBytes() || !actual.equals(item.getSha256())) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR,
                    "ARTIFACT_INTEGRITY_FAILED", "产物完整性检查失败，请重新执行任务");
        }
    }

    private LessonJob requiredJob(String jobId) {
        return jobs.findById(jobId).orElseThrow(() -> AppException.notFound("任务"));
    }

    private static Map<String, Double> publicScores(Map<String, Double> source) {
        if (source == null) return Map.of();
        Map<String, String> names = Map.of(
                "curriculum_alignment", "curriculumAlignment",
                "knowledge_accuracy", "knowledgeAccuracy",
                "teaching_logic", "teachingLogic",
                "classroom_feasibility", "classroomFeasibility",
                "differentiated_instruction", "differentiatedInstruction",
                "student_engagement", "studentEngagement",
                "assessment_design", "assessmentDesign",
                "language_and_format", "languageAndFormat");
        Map<String, Double> result = new LinkedHashMap<>();
        source.forEach((key, value) -> result.put(names.getOrDefault(key, key), value));
        return result;
    }

    private static <T> List<T> safe(List<T> values) {
        return values == null ? List.of() : values;
    }

    public record Download(InputStreamResource resource, String filename, String mediaType,
            long sizeBytes, String sha256) {
    }
}
