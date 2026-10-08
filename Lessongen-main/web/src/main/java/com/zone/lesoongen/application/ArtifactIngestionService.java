package com.zone.lesoongen.application;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.time.Clock;
import java.util.List;
import java.util.Optional;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import com.zone.lesoongen.application.storage.StoragePort;
import com.zone.lesoongen.application.storage.StoredObject;
import com.zone.lesoongen.domain.artifact.ArtifactStatus;
import com.zone.lesoongen.domain.artifact.ArtifactType;
import com.zone.lesoongen.domain.artifact.LessonArtifact;
import com.zone.lesoongen.domain.job.LessonJob;
import com.zone.lesoongen.domain.source.LessonSourceFile;
import com.zone.lesoongen.domain.source.ParseStatus;
import com.zone.lesoongen.domain.shared.Ulids;
import com.zone.lesoongen.infrastructure.engine.EngineClient;
import com.zone.lesoongen.infrastructure.engine.EngineContracts;
import com.zone.lesoongen.infrastructure.persistence.LessonArtifactRepository;
import com.zone.lesoongen.infrastructure.persistence.LessonSourceFileRepository;

@Service
public class ArtifactIngestionService {
    private static final long MAX_ARTIFACT_BYTES = 50L * 1024 * 1024;

    private final EngineClient engine;
    private final StoragePort storage;
    private final LessonArtifactRepository artifacts;
    private final LessonSourceFileRepository sources;
    private final JobStateService states;
    private final ObjectMapper mapper;
    private final Clock clock;

    public ArtifactIngestionService(EngineClient engine, StoragePort storage,
            LessonArtifactRepository artifacts, LessonSourceFileRepository sources,
            JobStateService states,
            ObjectMapper mapper, Clock clock) {
        this.engine = engine;
        this.storage = storage;
        this.artifacts = artifacts;
        this.sources = sources;
        this.states = states;
        this.mapper = mapper;
        this.clock = clock;
    }

    public void ingestTerminal(LessonJob job, EngineContracts.Snapshot snapshot) {
        Optional<EngineContracts.Result> result = engine.result(job.getEngineRunId());
        boolean requiresDeliverable = "completed".equals(snapshot.status())
                || "needs_human".equals(snapshot.status());
        if (requiresDeliverable && result.isEmpty()) {
            throw new AppException(HttpStatus.BAD_GATEWAY, "ENGINE_RESULT_MISSING",
                    "引擎已结束，但结构化教案结果缺失");
        }
        if (job.getResultStorageKey() == null) {
            result.ifPresent(value -> storeResult(job, value));
        }
        List<EngineContracts.Artifact> remote = engine.artifacts(job.getEngineRunId());
        for (EngineContracts.Artifact item : remote) {
            if (!"ok".equals(item.status()) || "original-docx".equals(item.artifactId())) {
                continue;
            }
            ArtifactType type = mapType(item);
            if (type == null || artifacts.existsByJobIdAndArtifactType(job.getId(), type)) {
                continue;
            }
            byte[] bytes = engine.download(job.getEngineRunId(), item.artifactId());
            if (bytes.length > MAX_ARTIFACT_BYTES) {
                throw new AppException(HttpStatus.BAD_GATEWAY, "ENGINE_ARTIFACT_TOO_LARGE",
                        "引擎产物超过允许大小");
            }
            String filename = safeArtifactName(type, item.displayName());
            String key = "jobs/" + job.getId() + "/artifacts/" + filename;
            try {
                StoredObject stored = storage.store(key, new ByteArrayInputStream(bytes),
                        MAX_ARTIFACT_BYTES);
                if (!stored.sha256().equals(item.sha256())) {
                    throw new AppException(HttpStatus.BAD_GATEWAY, "ARTIFACT_HASH_MISMATCH",
                            "引擎产物完整性校验失败");
                }
                saveArtifact(job, item, type, key, stored);
            } catch (IOException error) {
                throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "ARTIFACT_STORAGE_FAILED",
                        "无法保存教案结果文件");
            }
        }
        if (requiresDeliverable
                && !artifacts.existsByJobIdAndArtifactType(job.getId(), ArtifactType.BEST_DOCX)) {
            throw new AppException(HttpStatus.BAD_GATEWAY, "ENGINE_WORD_MISSING",
                    "引擎已结束，但可下载的 Word 教案缺失");
        }
        updateSourceParse(job, snapshot, result.orElse(null));
    }

    private void updateSourceParse(LessonJob job, EngineContracts.Snapshot snapshot,
            EngineContracts.Result result) {
        LessonSourceFile source = sources.findByJobIdAndKind(job.getId(),
                "ORIGINAL_LESSON_DOCX").orElse(null);
        if (source == null) return;
        LessonArtifact normalized = artifacts.findByJobIdAndArtifactType(job.getId(),
                ArtifactType.NORMALIZED_INPUT_JSON).orElse(null);
        if (normalized != null) {
            List<String> warnings = result == null ? List.of() : result.parseWarnings();
            source.updateParse(warnings == null || warnings.isEmpty()
                            ? ParseStatus.PARSED : ParseStatus.WARNING,
                    json(warnings == null ? List.of() : warnings), normalized.getStorageKey());
            sources.save(source);
        } else if ("failed".equals(snapshot.status())) {
            source.updateParse(ParseStatus.FAILED, "[]", null);
            sources.save(source);
        }
    }

    private void storeResult(LessonJob job, EngineContracts.Result result) {
        String key = "jobs/" + job.getId() + "/result/engine_result.json";
        try {
            byte[] bytes = mapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(result);
            storage.store(key, new ByteArrayInputStream(bytes), MAX_ARTIFACT_BYTES);
            states.setResultStorageKey(job.getId(), key);
        } catch (JacksonException error) {
            throw new IllegalStateException("cannot serialize engine result", error);
        } catch (IOException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "RESULT_STORAGE_FAILED",
                    "无法保存结构化教案结果");
        }
    }

    private String json(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (JacksonException error) {
            return "[]";
        }
    }

    @Transactional
    protected void saveArtifact(LessonJob job, EngineContracts.Artifact remote,
            ArtifactType type, String key, StoredObject stored) {
        artifacts.save(new LessonArtifact(Ulids.next(clock), job.getId(), remote.artifactId(),
                type, safeArtifactName(type, remote.displayName()), remote.mediaType(), key,
                stored.sizeBytes(), stored.sha256(), ArtifactStatus.AVAILABLE, "",
                clock.instant()));
    }

    private static ArtifactType mapType(EngineContracts.Artifact item) {
        return switch (item.artifactId()) {
            case "best-plan-docx" -> ArtifactType.BEST_DOCX;
            case "revised-candidate-docx" -> ArtifactType.REVISED_CANDIDATE_DOCX;
            case "best-plan-json" -> ArtifactType.BEST_JSON;
            case "recovery-plan-json" -> ArtifactType.RECOVERY_JSON;
            case "run-trace" -> ArtifactType.TRACE;
            case "normalized-input-json" -> ArtifactType.NORMALIZED_INPUT_JSON;
            case "optimization-report-json" -> ArtifactType.OPTIMIZATION_REPORT_JSON;
            default -> null;
        };
    }

    private static String safeArtifactName(ArtifactType type, String remote) {
        String extension = switch (type) {
            case BEST_DOCX, REVISED_CANDIDATE_DOCX, ORIGINAL_DOCX -> ".docx";
            case BEST_MARKDOWN, RECOVERY_MARKDOWN, PROCESS_REPORT,
                    OPTIMIZATION_REPORT_MARKDOWN -> ".md";
            case TRACE -> ".jsonl";
            default -> ".json";
        };
        String base = remote == null ? type.name().toLowerCase() : remote;
        base = base.replace('\\', '/');
        base = base.substring(base.lastIndexOf('/') + 1).replaceAll("[^\\p{L}\\p{N}._-]", "-");
        if (!base.toLowerCase().endsWith(extension)) {
            base = type.name().toLowerCase() + extension;
        }
        return base.substring(0, Math.min(base.length(), 180));
    }
}
