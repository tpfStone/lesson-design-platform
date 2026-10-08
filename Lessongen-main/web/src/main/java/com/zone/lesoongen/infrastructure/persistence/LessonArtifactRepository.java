package com.zone.lesoongen.infrastructure.persistence;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import com.zone.lesoongen.domain.artifact.ArtifactType;
import com.zone.lesoongen.domain.artifact.LessonArtifact;

public interface LessonArtifactRepository extends JpaRepository<LessonArtifact, String> {
    List<LessonArtifact> findByJobIdOrderByCreatedAtAsc(String jobId);
    Optional<LessonArtifact> findByIdAndJobId(String id, String jobId);
    Optional<LessonArtifact> findByJobIdAndArtifactType(String jobId, ArtifactType type);
    boolean existsByJobIdAndArtifactType(String jobId, ArtifactType type);
}
