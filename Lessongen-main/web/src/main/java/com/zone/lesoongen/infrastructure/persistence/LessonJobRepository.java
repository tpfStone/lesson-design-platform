package com.zone.lesoongen.infrastructure.persistence;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import com.zone.lesoongen.domain.job.JobMode;
import com.zone.lesoongen.domain.job.JobStatus;
import com.zone.lesoongen.domain.job.LessonJob;

import jakarta.persistence.LockModeType;

public interface LessonJobRepository extends JpaRepository<LessonJob, String> {
    Optional<LessonJob> findByIdempotencyKey(String idempotencyKey);

    long countByStatusIn(Collection<JobStatus> statuses);

    List<LessonJob> findByStatusIn(Collection<JobStatus> statuses);

    Page<LessonJobSummaryView> findProjectedByModeAndStatus(JobMode mode, JobStatus status,
            Pageable pageable);

    Page<LessonJobSummaryView> findProjectedByMode(JobMode mode, Pageable pageable);

    Page<LessonJobSummaryView> findProjectedByStatus(JobStatus status, Pageable pageable);

    Page<LessonJobSummaryView> findAllProjectedBy(Pageable pageable);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select j from LessonJob j where j.id = (select min(j2.id) from LessonJob j2 where j2.status = :status)")
    Optional<LessonJob> lockNextByStatus(@Param("status") JobStatus status);
}
