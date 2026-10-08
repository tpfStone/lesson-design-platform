package com.zone.lesoongen.infrastructure.persistence;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import com.zone.lesoongen.domain.source.LessonSourceFile;

public interface LessonSourceFileRepository extends JpaRepository<LessonSourceFile, String> {
    Optional<LessonSourceFile> findByJobIdAndKind(String jobId, String kind);
}
