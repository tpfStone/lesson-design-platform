package com.zone.lesoongen.platform;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.ArrayList;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import java.util.Objects;

import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;


import com.zone.lesoongen.api.dto.LessonRequests;
import com.zone.lesoongen.api.dto.LessonResponses;
import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.application.LessonJobService;
import com.zone.lesoongen.application.LessonResultService;
import com.zone.lesoongen.domain.artifact.ArtifactType;
import com.zone.lesoongen.platform.PlatformLessonController.LessonDetail;
import com.zone.lesoongen.platform.PlatformLessonController.LessonVersion;

@Service
public class PlatformOptimizeService {
    private final JdbcTemplate db;
    private final PlatformLessonService lessons;
    private final LessonJobService jobs;
    private final LessonResultService results;
    private final PlatformIssueContextService issueContext;

    public PlatformOptimizeService(JdbcTemplate db, PlatformLessonService lessons,
                                   LessonJobService jobs, LessonResultService results,
                                   PlatformIssueContextService issueContext) {
        this.db = db; this.lessons = lessons; this.jobs = jobs; this.results = results;
        this.issueContext = issueContext;
    }

    public record Link(String jobId, String lessonId, String sourceVersionId, String savedVersionId) {}
    public record History(String jobId, String lessonId, String lessonTitle, String sourceVersionId,
            String savedVersionId, String status, Instant createdAt) {}
    public record Saved(String lessonId, String sourceVersionId, String versionId,
            boolean alreadySaved, boolean unchanged) {}

    @Transactional
    public LessonResponses.JobAccepted start(String lessonId, PlatformOptimizeController.Start input) {
        LessonDetail detail = lessons.detail(lessonId);
        if (!Objects.equals(detail.lesson().currentVersionId(), input.versionId())) {
            throw new AppException(HttpStatus.CONFLICT, "OPTIMIZE_VERSION_CHANGED", "请先选择教案当前版本再优化");
        }
        LessonVersion version = detail.versions().stream().filter(v -> v.id().equals(input.versionId()))
                .findFirst().orElseThrow(() -> AppException.notFound("教案版本"));
        String subject = nonblank(input.subject(), nonblank(detail.lesson().subject(), "未指定学科"));
        String grade = nonblank(input.grade(), nonblank(detail.lesson().grade(), "未指定年级"));
        String topic = nonblank(input.topic(), nonblank(detail.lesson().topic(), detail.lesson().title()));
        Integer duration = input.durationMinutes() != null ? input.durationMinutes()
                : detail.lesson().durationMinutes() != null ? detail.lesson().durationMinutes() : 45;
        if (subject.length() > 64 || grade.length() > 64 || topic.length() > 255
                || duration < 5 || duration > 240) {
            throw new AppException(HttpStatus.BAD_REQUEST, "OPTIMIZE_METADATA_INVALID", "请检查学科、年级、课题和课时");
        }
        List<String> focus = mergeFocus(input.optimizationFocus(),
                issueContext.optimizationFocus(lessonId, version.id()));

        LessonRequests.Optimize request = new LessonRequests.Optimize(subject, grade, topic, duration,
                input.courseInformation(), input.textbookVersion(), input.textbookContent(),
                input.curriculumStandards(), input.learningObjectives(), input.studentProfile(),
                input.classSize(), input.availableResources(), input.additionalRequirements(),
                input.lessonStyle(), input.detailLevel(),
                focus, input.mustPreserveContent(), null);
        var accepted = jobs.createOptimize(request, docx(version.content()), input.requestKey().toString());
        db.update("""
                INSERT IGNORE INTO platform_optimize_job_link
                (job_id, lesson_id, source_version_id, saved_version_id, created_at)
                VALUES (?, ?, ?, NULL, ?)
                """, accepted.jobId(), lessonId, version.id(), Timestamp.from(Instant.now()));
        Link linked = link(lessonId, accepted.jobId());
        if (!linked.sourceVersionId().equals(version.id())) {
            throw new AppException(HttpStatus.CONFLICT, "OPTIMIZE_JOB_REUSED", "此优化任务已关联其他教案版本");
        }
        return accepted;
    }

    public Link link(String lessonId, String jobId) {
        return db.query("""
                SELECT job_id, lesson_id, source_version_id, saved_version_id
                FROM platform_optimize_job_link WHERE lesson_id = ? AND job_id = ?
                """, (rs, i) -> new Link(rs.getString(1), rs.getString(2), rs.getString(3), rs.getString(4)),
                lessonId, jobId).stream().findFirst().orElseThrow(() -> AppException.notFound("教案优化任务"));
    }

    public List<History> history() {
        return db.query("""
                SELECT l.job_id, l.lesson_id, p.title, l.source_version_id, l.saved_version_id,
                       j.status, l.created_at
                FROM platform_optimize_job_link l
                JOIN platform_lesson p ON p.id = l.lesson_id
                JOIN lesson_job j ON j.id = l.job_id
                ORDER BY l.created_at DESC, l.job_id DESC LIMIT 100
                """, (rs, i) -> new History(rs.getString(1), rs.getString(2), rs.getString(3),
                rs.getString(4), rs.getString(5), rs.getString(6), rs.getTimestamp(7).toInstant()));
    }

    @Transactional
    public Saved save(String lessonId, String jobId) {
        List<Link> locked = db.query("""
                SELECT job_id, lesson_id, source_version_id, saved_version_id
                FROM platform_optimize_job_link WHERE lesson_id = ? AND job_id = ? FOR UPDATE
                """, (rs, i) -> new Link(rs.getString(1), rs.getString(2), rs.getString(3), rs.getString(4)),
                lessonId, jobId);
        if (locked.isEmpty()) throw AppException.notFound("教案优化任务");
        Link binding = locked.get(0);
        if (binding.savedVersionId() != null) {
            return new Saved(lessonId, binding.sourceVersionId(), binding.savedVersionId(), true,
                    binding.savedVersionId().equals(binding.sourceVersionId()));
        }
        var result = results.result(jobId);
        LessonDetail detail = lessons.detail(lessonId);
        if (!Objects.equals(detail.lesson().currentVersionId(), binding.sourceVersionId())) {
            throw new AppException(HttpStatus.CONFLICT, "OPTIMIZE_VERSION_CHANGED", "教案已有新版本，请先查看后再决定如何合并优化结果");
        }
        boolean changed = result.optimization() != null && result.optimization().path("content_changed").asBoolean(false);
        String savedId = binding.sourceVersionId();
        if (changed) {
            var word = results.artifacts(jobId).stream().filter(a -> a.type() == ArtifactType.BEST_DOCX)
                    .findFirst().orElseThrow(() -> new AppException(HttpStatus.CONFLICT,
                            "OPTIMIZE_WORD_MISSING", "优化稿 Word 尚未生成，请稍后重试"));
            String content = readDocx(jobId, word.artifactId());
            if (content.length() > 100000) {
                throw new AppException(HttpStatus.BAD_REQUEST, "OPTIMIZE_CONTENT_TOO_LONG", "优化稿超过教案版本长度限制");
            }
            String original = detail.versions().stream().filter(v -> v.id().equals(binding.sourceVersionId()))
                    .findFirst().orElseThrow(() -> AppException.notFound("教案版本")).content();
            if (!content.isBlank() && !content.equals(original.trim())) {
                savedId = lessons.addVersionFromModule(lessonId, binding.sourceVersionId(), content,
                        "F2_OPTIMIZE", "f2:" + jobId).lesson().currentVersionId();
            }
        }
        db.update("UPDATE platform_optimize_job_link SET saved_version_id = ? WHERE job_id = ?", savedId, jobId);
        return new Saved(lessonId, binding.sourceVersionId(), savedId, false,
                savedId.equals(binding.sourceVersionId()));
    }

    public record ReviewDraft(String lessonId, String jobId, String sourceVersionId, int sourceVersionNumber,
            String originalContent, String candidateContent, String candidateSource, String jobStatus,
            String savedVersionId) {}
    public record ReviewSaved(String lessonId, String versionId, int versionNumber,
            boolean alreadySaved, boolean unchanged) {}

    public ReviewDraft reviewDraft(String lessonId, String jobId) {
        Link binding = link(lessonId, jobId);
        String status = reviewableStatus(jobId);
        LessonDetail detail = lessons.detail(lessonId);
        LessonVersion source = detail.versions().stream().filter(v -> v.id().equals(binding.sourceVersionId()))
                .findFirst().orElseThrow(() -> AppException.notFound("教案版本"));
        String candidate = null;
        String sourceName = null;
        var available = results.artifacts(jobId);
        // A revised candidate is a suggestion only; it has not passed a teacher's review.
        var revised = available.stream().filter(a -> a.type() == ArtifactType.REVISED_CANDIDATE_DOCX)
                .findFirst();
        if (revised.isPresent()) {
            candidate = readDocx(jobId, revised.get().artifactId());
            sourceName = "修改候选稿（待教师核对）";
        } else {
            var best = available.stream().filter(a -> a.type() == ArtifactType.BEST_DOCX).findFirst();
            if (best.isPresent()) {
                candidate = readDocx(jobId, best.get().artifactId());
                sourceName = "任务交付稿（待教师核对）";
            }
        }
        if (candidate != null && (candidate.isBlank() || candidate.trim().equals(source.content().trim()))) {
            candidate = null;
            sourceName = null;
        }
        return new ReviewDraft(lessonId, jobId, source.id(), source.versionNumber(), source.content(),
                candidate, sourceName, status, binding.savedVersionId());
    }

    @Transactional
    public ReviewSaved submitReview(String lessonId, String jobId, PlatformOptimizeReviewController.Submit request) {
        List<Link> locked = db.query("""
                SELECT job_id, lesson_id, source_version_id, saved_version_id
                FROM platform_optimize_job_link WHERE lesson_id = ? AND job_id = ? FOR UPDATE
                """, (rs, i) -> new Link(rs.getString(1), rs.getString(2), rs.getString(3), rs.getString(4)),
                lessonId, jobId);
        if (locked.isEmpty()) throw AppException.notFound("教案优化任务");
        Link binding = locked.get(0);
        reviewableStatus(jobId);
        if (!Boolean.TRUE.equals(request.confirmed())) {
            throw new AppException(HttpStatus.BAD_REQUEST, "REVIEW_NOT_CONFIRMED", "请先确认已核对教案正文");
        }
        if (!binding.sourceVersionId().equals(request.expectedVersionId())) {
            throw new AppException(HttpStatus.CONFLICT, "OPTIMIZE_SOURCE_MISMATCH", "复核所用教案版本不匹配，请刷新");
        }
        LessonDetail detail = lessons.detail(lessonId);
        if (binding.savedVersionId() != null) {
            LessonVersion saved = detail.versions().stream().filter(v -> v.id().equals(binding.savedVersionId()))
                    .findFirst().orElseThrow(() -> AppException.notFound("已保存的教案版本"));
            return new ReviewSaved(lessonId, saved.id(), saved.versionNumber(), true,
                    saved.id().equals(binding.sourceVersionId()));
        }
        if (!binding.sourceVersionId().equals(detail.lesson().currentVersionId())) {
            throw new AppException(HttpStatus.CONFLICT, "OPTIMIZE_VERSION_CHANGED", "教案已有新版本，请先查看后再决定如何合并优化结果");
        }
        LessonVersion original = detail.versions().stream().filter(v -> v.id().equals(binding.sourceVersionId()))
                .findFirst().orElseThrow(() -> AppException.notFound("教案版本"));
        String content = request.content().trim();
        String savedId = original.id();
        int number = original.versionNumber();
        if (!content.equals(original.content().trim())) {
            LessonDetail updated = lessons.addVersionFromModule(lessonId, original.id(), content,
                    "F2_OPTIMIZE", "f2:" + jobId + ":teacher-reviewed");
            savedId = updated.lesson().currentVersionId();
            number = updated.versions().stream().mapToInt(LessonVersion::versionNumber).max().orElse(number);
        }
        db.update("UPDATE platform_optimize_job_link SET saved_version_id = ? WHERE job_id = ?", savedId, jobId);
        return new ReviewSaved(lessonId, savedId, number, false, savedId.equals(original.id()));
    }

    private String reviewableStatus(String jobId) {
        String status = db.query("SELECT status FROM lesson_job WHERE id = ?", (rs, i) -> rs.getString(1), jobId)
                .stream().findFirst().orElseThrow(() -> AppException.notFound("优化任务"));
        if (!"COMPLETED".equals(status) && !"NEEDS_HUMAN".equals(status)) {
            throw new AppException(HttpStatus.CONFLICT, "REVIEW_NOT_READY", "任务尚未进入可复核状态");
        }
        return status;
    }

    private String readDocx(String jobId, String artifactId) {
        try (InputStream stream = results.download(jobId, artifactId).resource().getInputStream();
             XWPFDocument document = new XWPFDocument(stream)) {
            List<String> lines = new ArrayList<>();

            for (var element : document.getBodyElements()) {
                if (element instanceof XWPFParagraph paragraph) {
                    lines.add(paragraph.getText());
                } else if (element instanceof XWPFTable table) {
                    for (var row : table.getRows()) {
                        lines.add(row.getTableCells().stream()
                                .map(cell -> cell.getText())
                                .reduce((a, b) -> a + "\t" + b).orElse(""));
                    }
                }
            }

            return String.join("\n", lines).trim();
        } catch (IOException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR,
                    "REVIEW_DRAFT_READ_FAILED", "无法读取修改候选稿");
        }
    }

    private static String nonblank(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value.trim();
    }

    private static List<String> mergeFocus(List<String> userFocus, List<String> issueFocus) {
        List<String> result = new ArrayList<>();

        if (userFocus != null) {
            for (String item : userFocus) {
                if (item != null && !item.isBlank() && result.size() < 20) {
                    result.add(limit(item.trim(), 1000));
                }
            }
        }

        for (String item : issueFocus) {
            if (item != null && !item.isBlank() && result.size() < 20) {
                result.add(limit(item.trim(), 1000));
            }
        }

        return result.isEmpty() ? null : result;
    }

    private static String limit(String value, int max) {
        return value.length() <= max ? value : value.substring(0, max - 1) + "…";
    }

    private static MultipartFile docx(String content) {
        byte[] bytes;
        try (XWPFDocument document = new XWPFDocument(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            for (String line : content.split("\\R", -1)) document.createParagraph().createRun().setText(line);
            document.write(out);
            bytes = out.toByteArray();
        } catch (IOException error) {
            throw new AppException(HttpStatus.INTERNAL_SERVER_ERROR, "OPTIMIZE_DOCX_FAILED", "无法生成优化输入 Word");
        }
        return new MultipartFile() {
            public String getName() { return "document"; }
            public String getOriginalFilename() { return "lesson-version.docx"; }
            public String getContentType() { return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"; }
            public boolean isEmpty() { return bytes.length == 0; }
            public long getSize() { return bytes.length; }
            public byte[] getBytes() { return bytes.clone(); }
            public InputStream getInputStream() { return new ByteArrayInputStream(bytes); }
            public void transferTo(File dest) throws IOException { java.nio.file.Files.write(dest.toPath(), bytes); }
        };
    }
}
