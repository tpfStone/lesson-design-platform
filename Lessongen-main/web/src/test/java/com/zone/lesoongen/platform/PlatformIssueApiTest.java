package com.zone.lesoongen.platform;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.sql.Timestamp;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import com.zone.lesoongen.api.CorrelationIdFilter;
import com.zone.lesoongen.domain.shared.Ulids;
import com.zone.lesoongen.platform.PlatformLessonController.CreateLesson;

@SpringBootTest
@ActiveProfiles("test")
class PlatformIssueApiTest {
    @Autowired WebApplicationContext context;
    @Autowired CorrelationIdFilter correlationIdFilter;
    @Autowired PlatformLessonService lessons;
    @Autowired PlatformIssueIngestService issueIngest;
    @Autowired JdbcTemplate db;

    private MockMvc mvc;
    private String lessonId;
    private String versionId;

    @BeforeEach
    void setup() {
        mvc = MockMvcBuilders.webAppContextSetup(context)
                .addFilters(correlationIdFilter).build();
        var lesson = lessons.create(new CreateLesson(
                "公共问题测试", "数学", "七年级", "一次函数", 45, "教学内容"));
        lessonId = lesson.lesson().id();
        versionId = lesson.lesson().currentVersionId();
    }

    @Test
    void migrationCreatesAllIssueTables() {
        Integer count = db.queryForObject("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name IN ('platform_issue', 'platform_issue_evidence',
                                     'platform_issue_recommendation', 'platform_issue_context')
                """, Integer.class);
        assertEquals(4, count);
    }

    @Test
    void emptyVersionReturnsEmptyPageWithoutError() throws Exception {
        mvc.perform(get(path()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(0))
                .andExpect(jsonPath("$.totalElements").value(0))
                .andExpect(jsonPath("$.totalPages").value(0));
    }

    @Test
    void listSupportsFiltersAndPagination() throws Exception {
        insertIssue("F3", "HIGH", "OPEN", "课堂参与不足");
        insertIssue("F1", "LOW", "RESOLVED", "目标表述不清");

        mvc.perform(get(path()).queryParam("sourceModule", "f3")
                        .queryParam("status", "open").queryParam("severity", "high")
                        .queryParam("page", "0").queryParam("size", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.items[0].sourceModule").value("F3"))
                .andExpect(jsonPath("$.items[0].title").value("课堂参与不足"))
                .andExpect(jsonPath("$.totalElements").value(1))
                .andExpect(jsonPath("$.totalPages").value(1));
    }

    @Test
    void detailReturnsEvidenceRecommendationsAndContext() throws Exception {
        String issueId = insertIssue("F3", "MEDIUM", "OPEN", "反馈不够具体");
        Instant now = Instant.now().truncatedTo(ChronoUnit.MICROS);
        db.update("""
                INSERT INTO platform_issue_evidence
                (id, issue_id, evidence_type, source_event_id, sequence_number,
                 quote_text, section_ref, payload_json, created_at)
                VALUES (?, ?, 'EVENT_QUOTE', 'event-8', 8, '学生回答后教师直接进入下一题',
                        '课堂练习', '{"verified":true}', ?)
                """, id(), issueId, Timestamp.from(now));
        db.update("""
                INSERT INTO platform_issue_recommendation
                (id, issue_id, title, action_text, target_module, priority, status, created_at)
                VALUES (?, ?, '补充形成性反馈', '在练习后说明答案依据并追问学生。',
                        'F2', 'HIGH', 'PROPOSED', ?)
                """, id(), issueId, Timestamp.from(now));
        db.update("""
                INSERT INTO platform_issue_context
                (id, issue_id, context_type, source_module, source_run_id,
                 reference_id, label, payload_json, created_at)
                VALUES (?, ?, 'SOURCE_RESULT', 'F3', 'session-real-1',
                        'event-8', '课堂模拟事件', '{"eventId":"event-8"}', ?)
                """, id(), issueId, Timestamp.from(now));

        mvc.perform(get(path() + "/" + issueId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.issue.issueId").value(issueId))
                .andExpect(jsonPath("$.issue.evidenceCount").value(1))
                .andExpect(jsonPath("$.evidence[0].sourceEventId").value("event-8"))
                .andExpect(jsonPath("$.recommendations[0].targetModule").value("F2"))
                .andExpect(jsonPath("$.context[0].sourceModule").value("F3"));
    }

    @Test
    void issueFromAnotherVersionIsNotVisible() throws Exception {
        String issueId = insertIssue("F1", "LOW", "OPEN", "问题");
        var changed = lessons.addVersion(lessonId,
                new PlatformLessonController.NewVersion(versionId, "新版本内容"));
        String nextVersion = changed.lesson().currentVersionId();
        mvc.perform(get("/api/platform/lessons/" + lessonId + "/versions/"
                        + nextVersion + "/issues/" + issueId))
                .andExpect(status().isNotFound());
    }

    @Test
    void invalidFilterAndPageAreRejected() throws Exception {
        mvc.perform(get(path()).queryParam("sourceModule", "F9"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("ISSUE_FILTER_INVALID"));
        mvc.perform(get(path()).queryParam("size", "101"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("ISSUE_PAGE_INVALID"));
    }

    @Test
    void unknownLessonOrVersionReturns404() throws Exception {
        mvc.perform(get("/api/platform/lessons/01MISSING00000000000000000/versions/"
                        + versionId + "/issues"))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/platform/lessons/" + lessonId
                        + "/versions/01MISSING00000000000000000/issues"))
                .andExpect(status().isNotFound());
    }

    @Test
    void ingestF1AnnotationsCreatesIdempotentIssues() throws Exception {
        Map<String, Object> result = Map.of("rubric", Map.of("groups", List.of(
                Map.of("name", "目标设计", "items", List.of(
                        Map.of("维度名称", "目标可评价性", "等级", "C", "批注列表", List.of(
                                Map.of("位置", "教学目标", "原文引用", "理解一次函数",
                                        "具体分析", "目标缺少可观察行为",
                                        "建议", "改为可判断的学习表现"))))))));

        assertEquals(1, issueIngest.ingestF1(lessonId, versionId,
                "anno-run-1", "native-f1-run-1", result));
        assertEquals(0, issueIngest.ingestF1(lessonId, versionId,
                "anno-run-1", "native-f1-run-1", result));

        mvc.perform(get(path()).queryParam("sourceModule", "F1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.items[0].sourceModule").value("F1"))
                .andExpect(jsonPath("$.items[0].severity").value("HIGH"))
                .andExpect(jsonPath("$.items[0].evidenceCount").value(1))
                .andExpect(jsonPath("$.items[0].recommendationCount").value(1));
    }

    @Test
    void ingestF3IssuesCreatesEvidenceAndRecommendations() throws Exception {
        Map<String, Object> record = Map.of(
                "issues", List.of(Map.of(
                        "nativeIssueId", "issue-1",
                        "category", "classroom_interaction",
                        "severity", "HIGH",
                        "title", "追问不足",
                        "problem", "学生回答后缺少追问",
                        "targetLessonSection", "课堂练习",
                        "confidence", 0.86,
                        "evidence", List.of(Map.of(
                                "eventId", "event-3",
                                "sequence", 3,
                                "speaker", "teacher",
                                "contentQuote", "好，下一题")),
                        "suggestedAction", "在学生回答后补充为什么的追问")),
                "actionItems", List.of(Map.of(
                        "sourceIssueId", "issue-1",
                        "action", "增加一处追问和同伴互评",
                        "targetLessonSection", "课堂练习",
                        "priority", "HIGH")));

        assertEquals(1, issueIngest.ingestF3(lessonId, versionId,
                "simulation-run-1", "f3-session-1", record));
        assertEquals(0, issueIngest.ingestF3(lessonId, versionId,
                "simulation-run-1", "f3-session-1", record));

        mvc.perform(get(path()).queryParam("sourceModule", "F3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.items[0].sourceModule").value("F3"))
                .andExpect(jsonPath("$.items[0].sourceRunId").value("f3-session-1"))
                .andExpect(jsonPath("$.items[0].severity").value("HIGH"))
                .andExpect(jsonPath("$.items[0].evidenceCount").value(1))
                .andExpect(jsonPath("$.items[0].recommendationCount").value(2));
    }

    private String insertIssue(String module, String severity, String status, String title) {
        String issueId = id();
        Instant now = Instant.now().truncatedTo(ChronoUnit.MICROS);
        db.update("""
                INSERT INTO platform_issue
                (id, lesson_id, version_id, source_module, source_run_id, source_issue_id,
                 category, title, description, severity, status, confidence, section_ref,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'PEDAGOGY', ?, ?, ?, ?, 0.9000,
                        '教学过程', ?, ?)
                """, issueId, lessonId, versionId, module, "run-" + issueId,
                "native-" + issueId, title, title + "的详细说明", severity, status,
                Timestamp.from(now), Timestamp.from(now));
        return issueId;
    }

    private String path() {
        return "/api/platform/lessons/" + lessonId + "/versions/" + versionId + "/issues";
    }

    private static String id() {
        return Ulids.next(java.time.Clock.systemUTC());
    }
}
