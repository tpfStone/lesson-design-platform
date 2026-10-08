package com.zone.lesoongen.domain.job;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class LessonJobStateTest {
    private final Clock clock = Clock.fixed(Instant.parse("2026-09-11T00:00:00Z"), ZoneOffset.UTC);

    @Test
    void onlyAllowsForwardTransitionsAndFreezesTerminalState() {
        LessonJob job = job();
        job.transition(JobStatus.DISPATCHING, "dispatching", 0, 2, clock);
        job.transition(JobStatus.RUNNING, "writer", 0, 27, clock);
        job.transition(JobStatus.EXPORTING, "finalize", 2, 92, clock);
        job.transition(JobStatus.COMPLETED, "completed", 2, 100, clock);

        assertEquals(JobStatus.COMPLETED, job.getStatus());
        assertEquals(100, job.getProgressPercent());
        assertThrows(IllegalStateException.class,
                () -> job.transition(JobStatus.RUNNING, "writer", 3, 30, clock));
    }

    @Test
    void rejectsSkippedStateThatWouldHideSubmissionFailure() {
        LessonJob job = job();
        assertThrows(IllegalStateException.class,
                () -> job.transition(JobStatus.COMPLETED, "completed", 0, 100, clock));
    }

    private LessonJob job() {
        return new LessonJob("01ARZ3NDEKTSV4RRFFQ69G5FAV", JobMode.GENERATE,
                "化学", "高二", "官能团", 45, "{}", "0".repeat(64),
                "test-idempotency-key", null, clock);
    }
}
