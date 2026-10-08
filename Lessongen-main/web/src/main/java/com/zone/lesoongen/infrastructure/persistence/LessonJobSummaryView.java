package com.zone.lesoongen.infrastructure.persistence;

import java.time.Instant;

import com.zone.lesoongen.domain.job.JobMode;
import com.zone.lesoongen.domain.job.JobStatus;

/**
 * Closed projection for the recent-jobs query. Keeping this interface limited to
 * card fields prevents Hibernate from loading request_snapshot and result data
 * for every row in a paginated list.
 */
public interface LessonJobSummaryView {
    String getId();

    JobMode getMode();

    JobStatus getStatus();

    String getSubject();

    String getGrade();

    String getTopic();

    String getCurrentStage();

    int getCurrentRound();

    int getProgressPercent();

    Instant getCreatedAt();

    Instant getFinishedAt();
}
