package com.zone.lesoongen.platform;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.platform.PlatformIssueController.IssueContext;
import com.zone.lesoongen.platform.PlatformIssueController.IssueDetail;
import com.zone.lesoongen.platform.PlatformIssueController.IssueEvidence;
import com.zone.lesoongen.platform.PlatformIssueController.IssuePage;
import com.zone.lesoongen.platform.PlatformIssueController.IssueRecommendation;
import com.zone.lesoongen.platform.PlatformIssueController.IssueSummary;
import com.zone.lesoongen.platform.PlatformLessonController.LessonDetail;

@Service
public class PlatformIssueService {
    private static final Set<String> MODULES = Set.of("F1", "F2", "F3", "F4");
    private static final Set<String> STATUSES = Set.of("OPEN", "ACCEPTED", "RESOLVED", "DISMISSED");
    private static final Set<String> SEVERITIES = Set.of("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL");

    private static final String SUMMARY_SELECT = """
            SELECT i.id, i.lesson_id, i.version_id, v.version_number,
                   i.source_module, i.source_run_id, i.source_issue_id,
                   i.category, i.title, i.description, i.severity, i.status,
                   i.confidence, i.section_ref, i.created_at, i.updated_at,
                   (SELECT COUNT(*) FROM platform_issue_evidence e WHERE e.issue_id = i.id) evidence_count,
                   (SELECT COUNT(*) FROM platform_issue_recommendation r WHERE r.issue_id = i.id) recommendation_count
            FROM platform_issue i
            JOIN platform_lesson_version v ON v.id = i.version_id
            """;

    private final JdbcTemplate db;
    private final PlatformLessonService lessons;

    public PlatformIssueService(JdbcTemplate db, PlatformLessonService lessons) {
        this.db = db;
        this.lessons = lessons;
    }

    public IssuePage list(String lessonId, String versionId, String sourceModule,
            String status, String severity, int page, int size) {
        requireVersion(lessonId, versionId);
        if (page < 0 || size < 1 || size > 100) {
            throw bad("ISSUE_PAGE_INVALID", "page 必须大于等于 0，size 必须在 1 到 100 之间");
        }

        String moduleFilter = normalize(sourceModule, MODULES, "sourceModule");
        String statusFilter = normalize(status, STATUSES, "status");
        String severityFilter = normalize(severity, SEVERITIES, "severity");

        StringBuilder where = new StringBuilder(" WHERE i.lesson_id = ? AND i.version_id = ?");
        List<Object> params = new ArrayList<>();
        params.add(lessonId);
        params.add(versionId);
        append(where, params, "i.source_module", moduleFilter);
        append(where, params, "i.status", statusFilter);
        append(where, params, "i.severity", severityFilter);

        Long total = db.queryForObject("SELECT COUNT(*) FROM platform_issue i" + where,
                Long.class, params.toArray());
        long totalElements = total == null ? 0 : total;

        List<Object> pageParams = new ArrayList<>(params);
        pageParams.add(size);
        pageParams.add((long) page * size);
        List<IssueSummary> items = db.query(SUMMARY_SELECT + where
                        + " ORDER BY i.created_at DESC, i.id DESC LIMIT ? OFFSET ?",
                (rs, row) -> summary(rs), pageParams.toArray());
        int totalPages = totalElements == 0 ? 0 : (int) ((totalElements + size - 1) / size);
        return new IssuePage(items, page, size, totalElements, totalPages);
    }

    public IssueDetail detail(String lessonId, String versionId, String issueId) {
        requireVersion(lessonId, versionId);
        IssueSummary issue = db.query(SUMMARY_SELECT
                        + " WHERE i.lesson_id = ? AND i.version_id = ? AND i.id = ?",
                (rs, row) -> summary(rs), lessonId, versionId, issueId)
                .stream().findFirst().orElseThrow(() -> AppException.notFound("公共问题"));

        List<IssueEvidence> evidence = db.query("""
                SELECT id, evidence_type, source_event_id, sequence_number, quote_text,
                       section_ref, payload_json, created_at
                FROM platform_issue_evidence
                WHERE issue_id = ?
                ORDER BY sequence_number ASC, created_at ASC, id ASC
                """, (rs, row) -> evidence(rs), issueId);
        List<IssueRecommendation> recommendations = db.query("""
                SELECT id, title, action_text, target_module, priority, status, created_at
                FROM platform_issue_recommendation
                WHERE issue_id = ?
                ORDER BY CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                         created_at ASC, id ASC
                """, (rs, row) -> recommendation(rs), issueId);
        List<IssueContext> context = db.query("""
                SELECT id, context_type, source_module, source_run_id, reference_id,
                       label, payload_json, created_at
                FROM platform_issue_context
                WHERE issue_id = ?
                ORDER BY created_at ASC, id ASC
                """, (rs, row) -> context(rs), issueId);
        return new IssueDetail(issue, evidence, recommendations, context);
    }

    private void requireVersion(String lessonId, String versionId) {
        LessonDetail detail = lessons.detail(lessonId);
        boolean belongs = detail.versions().stream().anyMatch(version -> version.id().equals(versionId));
        if (!belongs) {
            throw AppException.notFound("教案版本");
        }
    }

    private static String normalize(String value, Set<String> allowed, String field) {
        if (value == null || value.isBlank()) return null;
        String normalized = value.trim().toUpperCase(Locale.ROOT);
        if (!allowed.contains(normalized)) {
            throw bad("ISSUE_FILTER_INVALID", field + " 不是受支持的筛选值");
        }
        return normalized;
    }

    private static void append(StringBuilder where, List<Object> params, String column, String value) {
        if (value == null) return;
        where.append(" AND ").append(column).append(" = ?");
        params.add(value);
    }

    private static IssueSummary summary(ResultSet rs) throws SQLException {
        return new IssueSummary(
                rs.getString("id"), rs.getString("lesson_id"), rs.getString("version_id"),
                rs.getInt("version_number"), rs.getString("source_module"),
                rs.getString("source_run_id"), rs.getString("source_issue_id"),
                rs.getString("category"), rs.getString("title"), rs.getString("description"),
                rs.getString("severity"), rs.getString("status"), rs.getBigDecimal("confidence"),
                rs.getString("section_ref"), rs.getInt("evidence_count"),
                rs.getInt("recommendation_count"), rs.getTimestamp("created_at").toInstant(),
                rs.getTimestamp("updated_at").toInstant());
    }

    private static IssueEvidence evidence(ResultSet rs) throws SQLException {
        int sequence = rs.getInt("sequence_number");
        Integer sequenceNumber = rs.wasNull() ? null : sequence;
        return new IssueEvidence(rs.getString("id"), rs.getString("evidence_type"),
                rs.getString("source_event_id"), sequenceNumber, rs.getString("quote_text"),
                rs.getString("section_ref"), rs.getString("payload_json"),
                rs.getTimestamp("created_at").toInstant());
    }

    private static IssueRecommendation recommendation(ResultSet rs) throws SQLException {
        return new IssueRecommendation(rs.getString("id"), rs.getString("title"),
                rs.getString("action_text"), rs.getString("target_module"),
                rs.getString("priority"), rs.getString("status"),
                rs.getTimestamp("created_at").toInstant());
    }

    private static IssueContext context(ResultSet rs) throws SQLException {
        return new IssueContext(rs.getString("id"), rs.getString("context_type"),
                rs.getString("source_module"), rs.getString("source_run_id"),
                rs.getString("reference_id"), rs.getString("label"),
                rs.getString("payload_json"), rs.getTimestamp("created_at").toInstant());
    }

    private static AppException bad(String code, String message) {
        return new AppException(HttpStatus.BAD_REQUEST, code, message);
    }
}
