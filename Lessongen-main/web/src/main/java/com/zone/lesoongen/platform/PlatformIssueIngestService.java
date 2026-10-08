package com.zone.lesoongen.platform;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.zone.lesoongen.domain.shared.Ulids;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Service
public class PlatformIssueIngestService {
    private final JdbcTemplate db;
    private final ObjectMapper mapper;

    public PlatformIssueIngestService(JdbcTemplate db, ObjectMapper mapper) {
        this.db = db;
        this.mapper = mapper;
    }

    @Transactional
    public int ingestF1(String lessonId, String versionId, String annotationRunId,
            String nativeRunId, Map<?, ?> result) {
        int count = 0;
        Object rubric = result == null ? null : result.get("rubric");
        Object groupsValue = rubric instanceof Map<?, ?> map ? map.get("groups") : null;
        if (!(groupsValue instanceof List<?> groups)) {
            return 0;
        }

        for (int groupIndex = 0; groupIndex < groups.size(); groupIndex++) {
            Object groupValue = groups.get(groupIndex);
            if (!(groupValue instanceof Map<?, ?> group)) continue;
            String category = firstText(group, "name", "title", "维度名称", "一级维度");
            Object itemsValue = group.get("items");
            if (!(itemsValue instanceof List<?> items)) continue;
            for (int itemIndex = 0; itemIndex < items.size(); itemIndex++) {
                Object itemValue = items.get(itemIndex);
                if (!(itemValue instanceof Map<?, ?> item)) continue;
                String dimension = firstText(item, "维度名称", "name", "title", "dimension");
                String grade = firstText(item, "等级", "grade", "level", "档位");
                String section = firstText(item, "位置", "section", "sectionRef");
                Object annotationsValue = firstValue(item, "批注列表", "annotations", "comments");
                if (annotationsValue instanceof List<?> annotations && !annotations.isEmpty()) {
                    for (int noteIndex = 0; noteIndex < annotations.size(); noteIndex++) {
                        Object noteValue = annotations.get(noteIndex);
                        if (!(noteValue instanceof Map<?, ?> note)) continue;
                        String sourceIssueId = "group-" + groupIndex + "-item-" + itemIndex + "-note-" + noteIndex;
                        String title = coalesce(firstText(note, "评价", "问题", "title"),
                                dimension, "智能评审问题");
                        String description = coalesce(firstText(note, "具体分析", "analysis", "description"),
                                firstText(note, "建议", "suggestion"), title);
                        String quote = firstText(note, "原文引用", "quote", "contentQuote");
                        String recommendation = coalesce(firstText(note, "细化建议", "建议", "suggestion"),
                                firstText(item, "建议", "suggestion"));
                        String noteSection = coalesce(firstText(note, "位置", "section", "sectionRef"), section);
                        IssueId issueId = insertIssue(lessonId, versionId, "F1", annotationRunId,
                                sourceIssueId, category, title, description, severityFromF1Grade(grade),
                                confidence(null), noteSection);
                        if (issueId.created()) {
                            insertEvidence(issueId.id(), "ANNOTATION", sourceIssueId, noteIndex + 1,
                                    quote, noteSection, note);
                            if (recommendation != null) {
                                insertRecommendation(issueId.id(), "按评审意见优化教案", recommendation,
                                        "F2", recommendationPriority(issueId.severity()));
                            }
                            insertContext(issueId.id(), "SOURCE_RESULT", "F1", nativeRunId,
                                    annotationRunId, "F1批注任务", item);
                            count++;
                        }
                    }
                } else if (isActionableGrade(grade)) {
                    String sourceIssueId = "group-" + groupIndex + "-item-" + itemIndex;
                    String title = coalesce(dimension, "智能评审维度问题");
                    String description = coalesce(firstText(item, "评价", "具体分析", "analysis", "description"), title);
                    IssueId issueId = insertIssue(lessonId, versionId, "F1", annotationRunId,
                            sourceIssueId, category, title, description, severityFromF1Grade(grade),
                            confidence(null), section);
                    if (issueId.created()) {
                        String recommendation = firstText(item, "建议", "细化建议", "suggestion");
                        if (recommendation != null) {
                            insertRecommendation(issueId.id(), "按评审意见优化教案", recommendation,
                                    "F2", recommendationPriority(issueId.severity()));
                        }
                        insertContext(issueId.id(), "SOURCE_RESULT", "F1", nativeRunId,
                                annotationRunId, "F1评分维度", item);
                        count++;
                    }
                }
            }
        }
        return count;
    }

    @Transactional
    public int ingestF3(String lessonId, String versionId, String simulationRunId,
            String f3SessionId, Map<?, ?> sessionRecord) {
        Object issuesValue = sessionRecord == null ? null : sessionRecord.get("issues");
        if (!(issuesValue instanceof List<?> issues)) {
            return 0;
        }

        List<Map<?, ?>> actionItems = new ArrayList<>();
        Object actionValue = firstValue(sessionRecord, "actionItems", "action_items");
        if (actionValue instanceof List<?> actions) {
            for (Object action : actions) {
                if (action instanceof Map<?, ?> map) actionItems.add(map);
            }
        }

        int count = 0;
        for (int index = 0; index < issues.size(); index++) {
            Object issueValue = issues.get(index);
            if (!(issueValue instanceof Map<?, ?> issue)) continue;
            String nativeIssueId = coalesce(firstText(issue, "nativeIssueId", "id"), "issue-" + index);
            String title = coalesce(firstText(issue, "title"), "课堂模拟问题");
            String description = coalesce(firstText(issue, "problem", "description"), title);
            String category = firstText(issue, "category");
            String section = firstText(issue, "targetLessonSection", "sectionRef");
            String severity = severity(firstText(issue, "severity"));
            BigDecimal confidence = confidence(firstValue(issue, "confidence"));

            IssueId issueId = insertIssue(lessonId, versionId, "F3", f3SessionId, nativeIssueId,
                    category, title, description, severity, confidence, section);
            if (issueId.created()) {
                insertF3Evidence(issueId.id(), issue);
                for (Map<?, ?> action : actionItems) {
                    String source = firstText(action, "sourceIssueId", "source_issue_id");
                    if (source == null || source.equals(nativeIssueId)) {
                        String actionText = firstText(action, "action", "actionText");
                        if (actionText != null) {
                            insertRecommendation(issueId.id(),
                                    coalesce(firstText(action, "title"), "根据课堂模拟调整教案"),
                                    actionText, "F2",
                                    recommendationPriority(firstText(action, "priority")));
                        }
                    }
                }
                String suggested = firstText(issue, "suggestedAction", "suggestion");
                if (suggested != null) {
                    insertRecommendation(issueId.id(), "根据课堂模拟调整教案", suggested,
                            "F2", recommendationPriority(issueId.severity()));
                }
                insertContext(issueId.id(), "SOURCE_RESULT", "F3", f3SessionId,
                        simulationRunId, "F3课堂模拟结果", issue);
                count++;
            }
        }
        return count;
    }
    @Transactional
    public int ingestF4(String lessonId, String versionId, String sessionId, Map<?, ?> currentState) {
        Object sectionsValue = currentState == null ? null : currentState.get("sections");
        if (!(sectionsValue instanceof List<?> sections)) {
            return 0;
        }

        int count = 0;
        for (Object sectionValue : sections) {
            if (!(sectionValue instanceof Map<?, ?> section)) continue;
            String sectionId = firstText(section, "id", "section_id");
            String sectionTitle = firstText(section, "title", "section_title");
            String sectionType = firstText(section, "section_type", "type");
            Object suggestionsValue = section.get("suggestions");
            if (!(suggestionsValue instanceof List<?> suggestions)) continue;

            for (int index = 0; index < suggestions.size(); index++) {
                Object suggestionValue = suggestions.get(index);
                if (!(suggestionValue instanceof Map<?, ?> suggestion)) continue;

                String sourceIssueId = coalesce(firstText(suggestion, "id"), "suggestion-" + index);
                String title = coalesce(firstText(suggestion, "issue"), "引导修订建议");
                String category = coalesce(firstText(suggestion, "issue_type"), "F4_SUGGESTION");
                String sectionRef = coalesce(sectionTitle, sectionType, sectionId);
                String status = statusFromF4Decision(suggestion.get("decision"));

                IssueId issueId = upsertIssue(lessonId, versionId, "F4", sessionId, sourceIssueId,
                        category, title, title, "INFO", confidence(firstValue(suggestion, "confidence")),
                        sectionRef, status);

                if (issueId.created()) {
                    insertEvidence(issueId.id(), "TEXT_SPAN",
                            firstText(suggestion, "generation_id", "round_id"), index + 1,
                            firstText(suggestion, "target_text"), sectionRef, Map.of(
                                    "sectionId", coalesce(sectionId, ""),
                                    "sectionTitle", coalesce(sectionTitle, ""),
                                    "sectionType", coalesce(sectionType, ""),
                                    "suggestion", suggestion));

                    String revision = firstText(suggestion, "revision");
                    if (revision != null) {
                        insertRecommendation(issueId.id(), "按引导修订建议调整教案", revision,
                                "F4", "MEDIUM");
                    }

                    insertContext(issueId.id(), "SOURCE_RESULT", "F4", sessionId,
                            coalesce(firstText(suggestion, "round_id"), sourceIssueId),
                            "F4引导修订建议", Map.of(
                                    "sectionId", coalesce(sectionId, ""),
                                    "sectionTitle", coalesce(sectionTitle, ""),
                                    "sectionType", coalesce(sectionType, ""),
                                    "suggestion", suggestion));
                    count++;
                }
            }
        }
        return count;
    }

    private IssueId insertIssue(String lessonId, String versionId, String sourceModule,
                                String sourceRunId, String sourceIssueId, String category, String title,
                                String description, String severity, BigDecimal confidence, String sectionRef) {
        return upsertIssue(lessonId, versionId, sourceModule, sourceRunId, sourceIssueId,
                category, title, description, severity, confidence, sectionRef, "OPEN");
    }

    private IssueId upsertIssue(String lessonId, String versionId, String sourceModule,
                                String sourceRunId, String sourceIssueId, String category, String title,
                                String description, String severity, BigDecimal confidence, String sectionRef,
                                String status) {
        String existing = db.query("""
            SELECT id FROM platform_issue
            WHERE source_module = ? AND source_run_id = ? AND source_issue_id = ?
            """, (rs, row) -> rs.getString("id"), sourceModule, sourceRunId, sourceIssueId)
                .stream().findFirst().orElse(null);

        if (existing != null) {
            db.update("UPDATE platform_issue SET status = ?, updated_at = ? WHERE id = ?",
                    status, Timestamp.from(Instant.now().truncatedTo(ChronoUnit.MICROS)), existing);
            return new IssueId(existing, severity, false);
        }

        String id = Ulids.next(java.time.Clock.systemUTC());
        Instant now = Instant.now().truncatedTo(ChronoUnit.MICROS);
        db.update("""
            INSERT INTO platform_issue
            (id, lesson_id, version_id, source_module, source_run_id, source_issue_id,
             category, title, description, severity, status, confidence, section_ref,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, id, lessonId, versionId, sourceModule, sourceRunId, sourceIssueId,
                limit(coalesce(category, "GENERAL"), 64), limit(coalesce(title, "问题"), 255),
                coalesce(description, title, "问题"), severity, status, confidence,
                limit(sectionRef, 255), Timestamp.from(now), Timestamp.from(now));

        return new IssueId(id, severity, true);
    }

    private void insertF3Evidence(String issueId, Map<?, ?> issue) {
        Object evidenceValue = issue.get("evidence");
        if (!(evidenceValue instanceof List<?> evidence)) return;
        for (int i = 0; i < evidence.size(); i++) {
            Object itemValue = evidence.get(i);
            if (!(itemValue instanceof Map<?, ?> item)) continue;
            Integer sequence = integer(firstValue(item, "sequence", "sequenceNumber"));
            insertEvidence(issueId, "EVENT_QUOTE", firstText(item, "eventId", "sourceEventId"),
                    sequence == null ? i + 1 : sequence,
                    firstText(item, "contentQuote", "quoteText", "quote"),
                    firstText(item, "sectionRef"), item);
        }
    }

    private void insertEvidence(String issueId, String evidenceType, String sourceEventId,
            Integer sequenceNumber, String quoteText, String sectionRef, Object payload) {
        db.update("""
                INSERT INTO platform_issue_evidence
                (id, issue_id, evidence_type, source_event_id, sequence_number,
                 quote_text, section_ref, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, Ulids.next(java.time.Clock.systemUTC()), issueId, evidenceType,
                limit(sourceEventId, 128), sequenceNumber, quoteText, limit(sectionRef, 255),
                json(payload), Timestamp.from(Instant.now().truncatedTo(ChronoUnit.MICROS)));
    }

    private void insertRecommendation(String issueId, String title, String actionText,
            String targetModule, String priority) {
        db.update("""
                INSERT INTO platform_issue_recommendation
                (id, issue_id, title, action_text, target_module, priority, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'PROPOSED', ?)
                """, Ulids.next(java.time.Clock.systemUTC()), issueId, limit(title, 255),
                actionText, targetModule, priority,
                Timestamp.from(Instant.now().truncatedTo(ChronoUnit.MICROS)));
    }

    private void insertContext(String issueId, String contextType, String sourceModule,
            String sourceRunId, String referenceId, String label, Object payload) {
        db.update("""
                INSERT INTO platform_issue_context
                (id, issue_id, context_type, source_module, source_run_id,
                 reference_id, label, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, Ulids.next(java.time.Clock.systemUTC()), issueId, contextType,
                sourceModule, limit(sourceRunId, 128), limit(referenceId, 255),
                limit(label, 255), json(payload),
                Timestamp.from(Instant.now().truncatedTo(ChronoUnit.MICROS)));
    }

    private String json(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (JacksonException error) {
            return "{}";
        }
    }

    private static boolean isActionableGrade(String grade) {
        return grade != null && !"A".equalsIgnoreCase(grade.trim());
    }

    private static String severityFromF1Grade(String grade) {
        if (grade == null) return "LOW";
        return switch (grade.trim().toUpperCase(Locale.ROOT)) {
            case "C" -> "HIGH";
            case "B" -> "MEDIUM";
            case "A" -> "INFO";
            default -> "LOW";
        };
    }

    private static String severity(String value) {
        if (value == null) return "MEDIUM";
        return switch (value.trim().toUpperCase(Locale.ROOT)) {
            case "CRITICAL" -> "CRITICAL";
            case "HIGH", "高" -> "HIGH";
            case "LOW", "低" -> "LOW";
            case "INFO" -> "INFO";
            default -> "MEDIUM";
        };
    }

    private static String statusFromF4Decision(Object decisionValue) {
        if (decisionValue instanceof Map<?, ?> decision) {
            String value = firstText(decision, "decision");
            if ("ACCEPT".equalsIgnoreCase(value)) return "ACCEPTED";
            if ("REJECT".equalsIgnoreCase(value)) return "DISMISSED";
        }
        return "OPEN";
    }

    private static String recommendationPriority(String value) {
        if (value == null) return "MEDIUM";
        return switch (value.trim().toUpperCase(Locale.ROOT)) {
            case "CRITICAL", "HIGH", "高" -> "HIGH";
            case "LOW", "低", "INFO" -> "LOW";
            default -> "MEDIUM";
        };
    }

    private static BigDecimal confidence(Object value) {
        if (!(value instanceof Number number)) return null;
        double numeric = number.doubleValue();
        if (numeric < 0 || numeric > 1) return null;
        return BigDecimal.valueOf(numeric).setScale(4, java.math.RoundingMode.HALF_UP);
    }

    private static Integer integer(Object value) {
        if (!(value instanceof Number number)) return null;
        return number.intValue();
    }

    private static Object firstValue(Map<?, ?> map, String... keys) {
        for (String key : keys) {
            Object value = map.get(key);
            if (value != null) return value;
        }
        return null;
    }

    private static String firstText(Map<?, ?> map, String... keys) {
        Object value = firstValue(map, keys);
        return value instanceof String text && !text.isBlank() ? text.trim() : null;
    }

    private static String coalesce(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) return value.trim();
        }
        return null;
    }

    private static String limit(String value, int max) {
        if (value == null) return null;
        return value.length() <= max ? value : value.substring(0, max);
    }

    private record IssueId(String id, String severity, boolean created) {}
}
