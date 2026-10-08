package com.zone.lesoongen.domain.job;

import java.util.EnumSet;
import java.util.Set;

public enum JobStatus {
    QUEUED,
    DISPATCHING,
    PREPROCESSING,
    RUNNING,
    EXPORTING,
    COMPLETED,
    NEEDS_HUMAN,
    FAILED;

    private static final Set<JobStatus> TERMINAL = EnumSet.of(COMPLETED, NEEDS_HUMAN, FAILED);

    public boolean isTerminal() {
        return TERMINAL.contains(this);
    }

    public boolean canTransitionTo(JobStatus next) {
        if (this == next) {
            return true;
        }
        if (isTerminal()) {
            return false;
        }
        return switch (this) {
            case QUEUED -> next == DISPATCHING || next == FAILED;
            case DISPATCHING -> EnumSet.of(PREPROCESSING, RUNNING, FAILED).contains(next);
            // A fast engine run may pass RUNNING/EXPORTING between two backend polls.
            case PREPROCESSING -> EnumSet.of(RUNNING, EXPORTING, COMPLETED, NEEDS_HUMAN, FAILED).contains(next);
            case RUNNING -> EnumSet.of(EXPORTING, COMPLETED, NEEDS_HUMAN, FAILED).contains(next);
            case EXPORTING -> TERMINAL.contains(next);
            default -> false;
        };
    }
}
