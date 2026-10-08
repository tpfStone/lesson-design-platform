package com.zone.lesoongen.platform;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import com.zone.lesoongen.api.CorrelationIdFilter;
import com.zone.lesoongen.platform.PlatformLessonController.CreateLesson;

import tools.jackson.databind.ObjectMapper;

@SpringBootTest
@ActiveProfiles("test")
class PlatformSimulationApiTest {
    @Autowired WebApplicationContext context;
    @Autowired CorrelationIdFilter correlationIdFilter;
    @Autowired PlatformLessonService lessons;
    @Autowired JdbcTemplate db;
    @Autowired ObjectMapper mapper;

    private MockMvc mvc;
    private String lessonId;
    private String versionId;

    @BeforeEach
    void setup() {
        mvc = MockMvcBuilders.webAppContextSetup(context)
                .addFilters(correlationIdFilter).build();
        var lesson = lessons.create(new CreateLesson(
                "模拟测试教案", "数学", "四年级", "数字编码", 45,
                "教学目标\n理解数字编码。\n\n情境导入\n观察生活中的编码。"));
        lessonId = lesson.lesson().id();
        versionId = lesson.lesson().currentVersionId();
    }

    @Test
    void migrationCreatesSimulationTable() {
        Integer count = db.queryForObject("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'platform_simulation_run'
                """, Integer.class);
        assertEquals(1, count);

        List<String> nullable = db.queryForList("""
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = 'platform_simulation_run'
                  AND column_name IN ('f4_session_id', 'f4_lesson_plan_id')
                ORDER BY column_name
                """, String.class);
        assertEquals(List.of("YES", "YES"), nullable);

        Integer migrated = db.queryForObject("""
                SELECT COUNT(*) FROM flyway_schema_history
                WHERE version = '12' AND success = TRUE
                """, Integer.class);
        assertEquals(1, migrated);
    }

    @Test
    void firstSaveReturns201() throws Exception {
        mvc.perform(post(path()).contentType(MediaType.APPLICATION_JSON).content(payload(record(UUID.randomUUID().toString()), "# summary")))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.lessonId").value(lessonId))
                .andExpect(jsonPath("$.versionId").value(versionId))
                .andExpect(jsonPath("$.completedRounds").value(4))
                .andExpect(jsonPath("$.alreadySaved").value(false));
    }

    @Test
    void urlLessonMismatchReturns400() throws Exception {
        Map<String, Object> record = record(UUID.randomUUID().toString());
        record.put("lessonId", "01MISMATCH00000000000000000");
        mvc.perform(post(path()).contentType(MediaType.APPLICATION_JSON).content(payload(record, "# summary")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("SIMULATION_LESSON_MISMATCH"));
    }

    @Test
    void versionMustBelongToLesson() throws Exception {
        var another = lessons.create(new CreateLesson("另一份教案", "数学", "四年级", "编码", 45, "内容"));
        Map<String, Object> record = record(UUID.randomUUID().toString());
        record.put("versionId", another.lesson().currentVersionId());
        mvc.perform(post(path()).contentType(MediaType.APPLICATION_JSON).content(payload(record, "# summary")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RESOURCE_NOT_FOUND"));
    }

    @Test
    void roundsCountMismatchReturns400() throws Exception {
        Map<String, Object> record = record(UUID.randomUUID().toString());
        record.put("completedRounds", 3);
        mvc.perform(post(path()).contentType(MediaType.APPLICATION_JSON).content(payload(record, "# summary")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("SIMULATION_ROUND_COUNT_MISMATCH"));
    }

    @Test
    void materialCountMismatchReturns400() throws Exception {
        Map<String, Object> record = record(UUID.randomUUID().toString());
        record.put("materialCount", 3);
        mvc.perform(post(path()).contentType(MediaType.APPLICATION_JSON).content(payload(record, "# summary")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("SIMULATION_MATERIAL_COUNT_MISMATCH"));
    }

    @Test
    void sameF3SessionAndSameContentIsIdempotent() throws Exception {
        String f3 = UUID.randomUUID().toString();
        String body = payload(record(f3), "# summary");
        String firstBody = mvc.perform(post(path()).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        Map<?, ?> first = mapper.readValue(firstBody, Map.class);

        String secondBody = mvc.perform(post(path()).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.alreadySaved").value(true))
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        Map<?, ?> second = mapper.readValue(secondBody, Map.class);
        assertEquals(first.get("simulationRunId"), second.get("simulationRunId"));
        Integer rows = db.queryForObject("SELECT COUNT(*) FROM platform_simulation_run WHERE f3_session_id = ?", Integer.class, f3);
        assertEquals(1, rows);
    }

    @Test
    void sameF3SessionWithDifferentContentReturns409() throws Exception {
        String f3 = UUID.randomUUID().toString();
        Map<String, Object> first = record(f3);
        mvc.perform(post(path()).contentType(MediaType.APPLICATION_JSON).content(payload(first, "# summary")))
                .andExpect(status().isCreated());
        Map<String, Object> changed = record(f3);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> rounds = (List<Map<String, Object>>) changed.get("rounds");
        rounds.get(0).put("input", "不同内容");
        mvc.perform(post(path()).contentType(MediaType.APPLICATION_JSON).content(payload(changed, "# summary")))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("SIMULATION_RESULT_CONFLICT"));
    }

    @Test
    void listIsSummaryOnlyAndNewestFirst() throws Exception {
        save(record(UUID.randomUUID().toString()), "# first");
        save(record(UUID.randomUUID().toString()), "# second");
        mvc.perform(get(path()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].simulationRunId").exists())
                .andExpect(jsonPath("$[0].versionNumber").value(0))
                .andExpect(jsonPath("$[0].sessionRecord").doesNotExist())
                .andExpect(jsonPath("$[0].summaryMarkdown").doesNotExist());
    }

    @Test
    void detailReturnsFullRecordAndMarkdown() throws Exception {
        String id = save(record(UUID.randomUUID().toString()), "# exact summary");
        mvc.perform(get(path() + "/" + id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sessionRecord.lessonId").value(lessonId))
                .andExpect(jsonPath("$.sessionRecord.rounds.length()").value(4))
                .andExpect(jsonPath("$.summaryMarkdown").value("# exact summary"));
    }

    @Test
    void jsonAndMarkdownDownloadsMatchStoredContent() throws Exception {
        String id = save(record(UUID.randomUUID().toString()), "# download summary");
        MvcResult json = mvc.perform(get(path() + "/" + id + "/artifacts/json"))
                .andExpect(status().isOk())
                .andExpect(content().contentType(MediaType.APPLICATION_JSON))
                .andExpect(header().string("Content-Disposition", "attachment; filename=simulation-" + id + ".json"))
                .andReturn();
        Map<?, ?> downloaded = mapper.readValue(json.getResponse().getContentAsString(StandardCharsets.UTF_8), Map.class);
        assertEquals(lessonId, downloaded.get("lessonId"));

        mvc.perform(get(path() + "/" + id + "/artifacts/md"))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Disposition", "attachment; filename=simulation-" + id + "-summary.md"))
                .andExpect(content().string("# download summary"));
    }

    @Test
    void simulationFromAnotherLessonIs404() throws Exception {
        String id = save(record(UUID.randomUUID().toString()), "# summary");
        var another = lessons.create(new CreateLesson("第三份教案", "数学", "四年级", "编码", 45, "内容"));
        mvc.perform(get("/api/platform/lessons/" + another.lesson().id() + "/simulations/" + id))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RESOURCE_NOT_FOUND"));
    }

    private String save(Map<String, Object> record, String summary) throws Exception {
        String response = mvc.perform(post(path()).contentType(MediaType.APPLICATION_JSON).content(payload(record, summary)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        return String.valueOf(mapper.readValue(response, Map.class).get("simulationRunId"));
    }

    private String path() {
        return "/api/platform/lessons/" + lessonId + "/simulations";
    }

    private String payload(Map<String, Object> record, String summary) throws Exception {
        return mapper.writeValueAsString(Map.of("sessionRecord", record, "summaryMarkdown", summary));
    }

    private Map<String, Object> record(String f3SessionId) {
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("status", "COMPLETED");
        record.put("startedAt", OffsetDateTime.parse("2026-10-03T00:58:24+08:00").toString());
        record.put("finishedAt", OffsetDateTime.parse("2026-10-03T00:58:25+08:00").toString());
        record.put("lessonId", lessonId);
        record.put("versionId", versionId);
        record.put("f4SessionId", UUID.randomUUID().toString());
        record.put("f4LessonPlanId", UUID.randomUUID().toString());
        record.put("f3SessionId", f3SessionId);
        record.put("requestedRounds", 4);
        record.put("completedRounds", 4);

        List<Map<String, Object>> materials = new ArrayList<>();
        for (int i = 1; i <= 4; i++) materials.add(Map.of("id", i, "title", "材料" + i));
        record.put("materialCount", materials.size());
        record.put("materials", materials);

        List<Map<String, Object>> rounds = new ArrayList<>();
        List<Map<String, Object>> history = new ArrayList<>();
        for (int i = 1; i <= 4; i++) {
            history.add(Map.of("speaker", "user", "function", "user_message", "content", "问题" + i));
            history.add(Map.of("speaker", "teacher", "function", "teach", "content", "[MockLLM] 回复" + i));
            Map<String, Object> round = new LinkedHashMap<>();
            round.put("round", i);
            round.put("input", "问题" + i);
            round.put("response", Map.of("speaker", "teacher", "function", "teach", "content", "[MockLLM] 回复" + i));
            round.put("stateStatus", "active");
            round.put("historyCount", i * 2);
            rounds.add(round);
        }
        record.put("rounds", rounds);
        record.put("finalState", Map.of("status", "active", "history", history));
        record.put("executionBoundary", Map.of(
                "httpChain", "REAL",
                "f4Provider", "mock",
                "f3ModelContent", "MOCK"));
        return record;
    }
}
