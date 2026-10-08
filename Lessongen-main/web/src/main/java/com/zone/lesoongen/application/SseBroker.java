package com.zone.lesoongen.application;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import com.zone.lesoongen.api.dto.LessonResponses;
import com.zone.lesoongen.domain.event.LessonJobEvent;
import com.zone.lesoongen.domain.job.LessonJob;
import com.zone.lesoongen.infrastructure.persistence.LessonJobEventRepository;
import com.zone.lesoongen.infrastructure.persistence.LessonJobRepository;

@Component
public class SseBroker {
    private final LessonJobRepository jobs;
    private final LessonJobEventRepository events;
    private final Map<String, CopyOnWriteArrayList<Subscriber>> subscribers =
            new ConcurrentHashMap<>();

    public SseBroker(LessonJobRepository jobs, LessonJobEventRepository events) {
        this.jobs = jobs;
        this.events = events;
    }

    public SseEmitter subscribe(String jobId, long lastEventId) {
        LessonJob job = jobs.findById(jobId).orElseThrow(() -> AppException.notFound("任务"));
        SseEmitter emitter = new SseEmitter(0L);
        Subscriber subscriber = new Subscriber(emitter, new AtomicLong(lastEventId));
        subscribers.computeIfAbsent(jobId, ignored -> new CopyOnWriteArrayList<>()).add(subscriber);
        Runnable remove = () -> remove(jobId, subscriber);
        emitter.onCompletion(remove);
        emitter.onTimeout(remove);
        emitter.onError(ignored -> remove.run());
        sendSnapshot(job, subscriber);
        sendAvailable(jobId, subscriber, job.getStatus().isTerminal());
        return emitter;
    }

    @Scheduled(fixedDelay = 1000)
    public void pump() {
        subscribers.forEach((jobId, values) -> {
            boolean terminal = jobs.findById(jobId).map(job -> job.getStatus().isTerminal())
                    .orElse(true);
            values.forEach(value -> sendAvailable(jobId, value, terminal));
        });
    }

    @Scheduled(fixedDelay = 15000)
    public void heartbeat() {
        subscribers.forEach((jobId, values) -> values.forEach(value -> {
            try {
                value.emitter.send(SseEmitter.event().comment("keep-alive"));
            } catch (IOException | IllegalStateException error) {
                remove(jobId, value);
            }
        }));
    }

    private void sendAvailable(String jobId, Subscriber subscriber, boolean terminal) {
        List<LessonJobEvent> pending = events
                .findByJobIdAndSequenceNoGreaterThanOrderBySequenceNoAsc(jobId,
                        subscriber.lastSequence.get());
        try {
            for (LessonJobEvent item : pending) {
                LessonResponses.JobEvent payload = new LessonResponses.JobEvent(
                        item.getSequenceNo(), item.getEventType(), item.getStage(),
                        item.getRoundIndex(), item.getVersionId(), item.getProgressPercent(),
                        item.getMessage(), item.getCreatedAt());
                subscriber.emitter.send(SseEmitter.event()
                        .id(Long.toString(item.getSequenceNo()))
                        .name(item.getEventType())
                        .data(payload));
                subscriber.lastSequence.set(item.getSequenceNo());
            }
            if (terminal) {
                subscriber.emitter.complete();
                remove(jobId, subscriber);
            }
        } catch (IOException | IllegalStateException error) {
            remove(jobId, subscriber);
        }
    }

    private void sendSnapshot(LessonJob job, Subscriber subscriber) {
        LessonResponses.JobEvent snapshot = new LessonResponses.JobEvent(
                subscriber.lastSequence.get(), "job.snapshot", job.getCurrentStage(),
                job.getCurrentRound(), job.getLastVersionId(), job.getProgressPercent(),
                snapshotMessage(job), job.getUpdatedAt());
        try {
            // Deliberately omit an SSE id: browser reconnects must keep the latest durable
            // event id, not replace it with a synthetic snapshot marker.
            subscriber.emitter.send(SseEmitter.event().name("job.snapshot").data(snapshot));
        } catch (IOException | IllegalStateException error) {
            remove(job.getId(), subscriber);
        }
    }

    private static String snapshotMessage(LessonJob job) {
        if (job.getStatus().isTerminal()) {
            return switch (job.getStatus()) {
                case COMPLETED -> "教案闭环已完成";
                case NEEDS_HUMAN -> "已形成最佳版本，建议教师复核";
                case FAILED -> "本次任务未完整完成";
                default -> "任务已结束";
            };
        }
        return "当前任务状态已恢复";
    }

    private void remove(String jobId, Subscriber subscriber) {
        CopyOnWriteArrayList<Subscriber> values = subscribers.get(jobId);
        if (values != null) {
            values.remove(subscriber);
            if (values.isEmpty()) subscribers.remove(jobId);
        }
    }

    private record Subscriber(SseEmitter emitter, AtomicLong lastSequence) {
    }
}
