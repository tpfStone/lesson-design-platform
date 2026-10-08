package com.zone.lesoongen.application;

import java.time.Clock;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.zone.lesoongen.domain.event.LessonJobEvent;
import com.zone.lesoongen.domain.job.LessonJob;
import com.zone.lesoongen.infrastructure.persistence.LessonJobEventRepository;

@Service
public class JobEventService {
    private final LessonJobEventRepository repository;
    private final Clock clock;

    public JobEventService(LessonJobEventRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    @Transactional
    public LessonJobEvent record(LessonJob job, String eventType, String message,
            String engineEventKey) {
        return record(job.getId(), eventType, job.getCurrentStage(), job.getCurrentRound(),
                job.getLastVersionId(), job.getProgressPercent(), message, engineEventKey);
    }

    @Transactional
    public LessonJobEvent recordEngine(String jobId, String eventType,
            com.zone.lesoongen.infrastructure.engine.EngineContracts.Event source) {
        return record(jobId, eventType, source.stage(), source.roundIndex(),
                source.versionId(), source.progressPercent(), source.message(),
                "engine:" + source.sequence());
    }

    private LessonJobEvent record(String jobId, String eventType, String stage,
            Integer roundIndex, String versionId, int progressPercent, String message,
            String engineEventKey) {
        if (engineEventKey != null
                && repository.existsByJobIdAndEngineEventKey(jobId, engineEventKey)) {
            return null;
        }
        long sequence = repository.maxSequence(jobId) + 1;
        LessonJobEvent event = new LessonJobEvent(
                jobId, sequence, eventType, value(stage, "running"),
                roundIndex, value(versionId, null), Math.max(0, Math.min(100, progressPercent)),
                value(message, "教案流程正在推进"), "{}", engineEventKey, clock.instant());
        return repository.save(event);
    }

    private static String value(String input, String fallback) {
        return input == null || input.isBlank() ? fallback : input;
    }
}
