package com.zone.lesoongen.infrastructure.persistence;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import com.zone.lesoongen.domain.event.LessonJobEvent;

public interface LessonJobEventRepository extends JpaRepository<LessonJobEvent, Long> {
    List<LessonJobEvent> findByJobIdAndSequenceNoGreaterThanOrderBySequenceNoAsc(String jobId, long sequenceNo);
    boolean existsByJobIdAndEngineEventKey(String jobId, String engineEventKey);

    @Query("select coalesce(max(e.sequenceNo), 0) from LessonJobEvent e where e.jobId = :jobId")
    long maxSequence(@Param("jobId") String jobId);
}
