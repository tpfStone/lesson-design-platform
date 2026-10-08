package com.zone.lesoongen.platform;

import java.util.ArrayList;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class PlatformIssueContextService {
    private final JdbcTemplate db;

    public PlatformIssueContextService(JdbcTemplate db) {
        this.db = db;
    }

    public List<String> optimizationFocus(String lessonId, String versionId) {
        return issues(lessonId, versionId, List.of("F1", "F3", "F4"), 8, 900).stream()
                .map(item -> "[公共问题][" + item.sourceModule() + "] " + item.text())
                .toList();
    }

    public String f4AdditionalContext(String lessonId, String versionId) {
        List<IssueLine> items = issues(lessonId, versionId, List.of("F1", "F2", "F3"), 8, 420);
        if (items.isEmpty()) return null;
        StringBuilder text = new StringBuilder("以下为其他模块已发现但尚未解决的公共问题，请在本轮引导修订时优先参考：");
        for (int i = 0; i < items.size(); i++) {
            IssueLine item = items.get(i);
            text.append("\n").append(i + 1).append(". [").append(item.sourceModule()).append("] ")
                    .append(item.text());
        }
        return limit(text.toString(), 3900);
    }

    private List<IssueLine> issues(String lessonId, String versionId, List<String> modules,
            int maxItems, int maxChars) {
        String placeholders = String.join(",", modules.stream().map(ignored -> "?").toList());
        List<Object> params = new ArrayList<>();
        params.add(lessonId);
        params.add(versionId);
        params.addAll(modules);
        params.add(maxItems);

        return db.query("""
                SELECT i.source_module, i.severity, i.title, i.description, i.section_ref,
                       (SELECT r.action_text FROM platform_issue_recommendation r
                        WHERE r.issue_id = i.id
                        ORDER BY CASE r.priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                                 r.created_at ASC, r.id ASC LIMIT 1) recommendation
                FROM platform_issue i
                WHERE i.lesson_id = ? AND i.version_id = ?
                  AND i.status IN ('OPEN', 'ACCEPTED')
                  AND i.source_module IN (""" + placeholders + """
                  )
                ORDER BY CASE i.severity
                           WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                           WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 ELSE 5 END,
                         i.created_at DESC, i.id DESC
                LIMIT ?
                """, (rs, row) -> {
                    String section = rs.getString("section_ref");
                    String recommendation = rs.getString("recommendation");
                    StringBuilder line = new StringBuilder();

                    if (section != null && !section.isBlank()) {
                        line.append("环节：").append(section).append("；");
                    }

                    line.append("问题：").append(rs.getString("title"));

                    String description = rs.getString("description");
                    if (description != null && !description.isBlank()
                            && !description.equals(rs.getString("title"))) {
                        line.append("；说明：").append(description);
                    }

                    if (recommendation != null && !recommendation.isBlank()) {
                        line.append("；建议：").append(recommendation);
                    }

                    line.append("；严重程度：").append(rs.getString("severity"));
                    return new IssueLine(rs.getString("source_module"), limit(line.toString(), maxChars));
                }, params.toArray());
    }

    private static String limit(String value, int max) {
        if (value == null || value.length() <= max) return value;
        return value.substring(0, max - 1) + "…";
    }

    private record IssueLine(String sourceModule, String text) {}
}