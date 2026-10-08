package com.zone.lesoongen.platform;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;

import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.context.WebApplicationContext;

import com.zone.lesoongen.api.CorrelationIdFilter;
import com.zone.lesoongen.application.storage.StoragePort;
import com.zone.lesoongen.platform.PlatformLessonController.CreateLesson;

import tools.jackson.databind.ObjectMapper;

@SpringBootTest
@ActiveProfiles("test")
class PlatformLessonImportApiTest {
    private static final String DOCX_MEDIA =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

    @Autowired WebApplicationContext context;
    @Autowired CorrelationIdFilter correlationIdFilter;
    @Autowired JdbcTemplate db;
    @Autowired ObjectMapper mapper;
    @Autowired PlatformLessonImportService imports;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired StoragePort storage;

    private MockMvc mvc;

    @BeforeEach
    void setup() {
        mvc = MockMvcBuilders.webAppContextSetup(context)
                .addFilters(correlationIdFilter).build();
    }

    @Test
    void migrationCreatesSourceDocumentTable() {
        Integer count = db.queryForObject("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'platform_lesson_source_document'
                """, Integer.class);
        assertEquals(1, count);
    }

    @Test
    void migrationCreatesVersionStructureTable() {
        Integer count = db.queryForObject("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'platform_lesson_version_structure'
                """, Integer.class);
        assertEquals(1, count);
    }

    @Test
    void previewExtractsParagraphsAndTableWithoutPersistingLesson() throws Exception {
        byte[] docx = docxWithTextAndTable();
        MockMultipartFile file = new MockMultipartFile("file", "课堂教案.docx", DOCX_MEDIA, docx);
        Integer before = db.queryForObject("SELECT COUNT(*) FROM platform_lesson", Integer.class);

        mvc.perform(multipart("/api/platform/lessons/imports/docx/preview").file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.originalFilename").value("课堂教案.docx"))
                .andExpect(jsonPath("$.sizeBytes").value(docx.length))
                .andExpect(jsonPath("$.extractedContent").value(org.hamcrest.Matchers.containsString("教学目标")))
                .andExpect(jsonPath("$.extractedContent").value(org.hamcrest.Matchers.containsString("教师活动 | 学生活动")))
                .andExpect(jsonPath("$.structuredContent.schemaVersion").value("1.0"))
                .andExpect(jsonPath("$.structuredContent.blocks[2].type").value("teaching_process"))
                .andExpect(jsonPath("$.contentLength").isNumber());

        Integer after = db.queryForObject("SELECT COUNT(*) FROM platform_lesson", Integer.class);
        assertEquals(before, after);
    }

    @Test
    void previewRejectsFakeDocxAndEmptyTextDocx() throws Exception {
        MockMultipartFile fake = new MockMultipartFile("file", "fake.docx", DOCX_MEDIA,
                "not a zip".getBytes(StandardCharsets.UTF_8));
        mvc.perform(multipart("/api/platform/lessons/imports/docx/preview").file(fake))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code").value("INVALID_DOCX"));

        MockMultipartFile empty = new MockMultipartFile("file", "empty.docx", DOCX_MEDIA, emptyDocx());
        mvc.perform(multipart("/api/platform/lessons/imports/docx/preview").file(empty))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("DOCX_EMPTY_CONTENT"));
    }

    @Test
    void previewRejectsOversizedFileBeforeParsing() throws Exception {
        byte[] oversized = new byte[20 * 1024 * 1024 + 1];
        oversized[0] = 'P'; oversized[1] = 'K'; oversized[2] = 3; oversized[3] = 4;
        MockMultipartFile file = new MockMultipartFile("file", "large.docx", DOCX_MEDIA, oversized);
        mvc.perform(multipart("/api/platform/lessons/imports/docx/preview").file(file))
                .andExpect(status().isPayloadTooLarge())
                .andExpect(jsonPath("$.code").value("DOCX_TOO_LARGE"));
    }

    @Test
    void confirmedImportCreatesV0MetadataAndDownloadableOriginal() throws Exception {
        byte[] original = docxWithTextAndTable();
        MockMultipartFile file = new MockMultipartFile("file", "原始教案.docx", DOCX_MEDIA, original);
        String confirmedContent = "用户确认后的正文\n\n教学目标：掌握小数加减法。";

        MvcResult create = mvc.perform(multipart("/api/platform/lessons/imports/docx")
                        .file(file)
                        .param("title", "小数的加法和减法")
                        .param("subject", "数学")
                        .param("grade", "四年级")
                        .param("topic", "小数加减法")
                        .param("durationMinutes", "45")
                        .param("content", confirmedContent))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.lesson.id").exists())
                .andExpect(jsonPath("$.lesson.currentVersionId").exists())
                .andExpect(jsonPath("$.versions[0].versionNumber").value(0))
                .andExpect(jsonPath("$.versions[0].sourceModule").value("IMPORT_DOCX"))
                .andExpect(jsonPath("$.versions[0].content").value(confirmedContent))
                .andReturn();

        Map<?, ?> body = mapper.readValue(create.getResponse().getContentAsString(StandardCharsets.UTF_8), Map.class);
        Map<?, ?> lesson = (Map<?, ?>) body.get("lesson");
        String lessonId = String.valueOf(lesson.get("id"));
        String versionId = String.valueOf(lesson.get("currentVersionId"));

        mvc.perform(get("/api/platform/lessons/{lessonId}/source-document", lessonId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.lessonId").value(lessonId))
                .andExpect(jsonPath("$.versionId").value(versionId))
                .andExpect(jsonPath("$.originalFilename").value("原始教案.docx"))
                .andExpect(jsonPath("$.sizeBytes").value(original.length))
                .andExpect(jsonPath("$.sha256").value(sha256(original)));

        MvcResult download = mvc.perform(get("/api/platform/lessons/{lessonId}/source-document/file", lessonId))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Disposition", org.hamcrest.Matchers.containsString("attachment")))
                .andReturn();
        assertArrayEquals(original, download.getResponse().getContentAsByteArray());
        assertEquals(sha256(original), sha256(download.getResponse().getContentAsByteArray()));
    }

    @Test
    void docxImportCanSaveWithoutReenteringBasicMetadata() throws Exception {
        byte[] original = docxWithTextAndTable();
        MockMultipartFile file = new MockMultipartFile("file", "已有完整教案.docx", DOCX_MEDIA, original);

        mvc.perform(multipart("/api/platform/lessons/imports/docx").file(file))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.lesson.title").value("已有完整教案"))
                .andExpect(jsonPath("$.lesson.subject").value(""))
                .andExpect(jsonPath("$.lesson.grade").value(""))
                .andExpect(jsonPath("$.lesson.topic").value("已有完整教案"))
                .andExpect(jsonPath("$.versions[0].versionNumber").value(0))
                .andExpect(jsonPath("$.versions[0].sourceModule").value("IMPORT_DOCX"))
                .andExpect(jsonPath("$.versions[0].content").value(org.hamcrest.Matchers.containsString("教学目标")));
    }

    @Test
    void docxBodyOrderAndTeachingTableArePreservedInVersionDocument() throws Exception {
        byte[] original = docxWithParagraphTableParagraph();
        MockMultipartFile file = new MockMultipartFile("file", "顺序教案.docx", DOCX_MEDIA, original);
        MvcResult created = mvc.perform(multipart("/api/platform/lessons/imports/docx").file(file))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.versions[0].content",
                        org.hamcrest.Matchers.containsString("课前说明")))
                .andReturn();
        Map<?, ?> body = mapper.readValue(created.getResponse().getContentAsString(StandardCharsets.UTF_8), Map.class);
        Map<?, ?> lesson = (Map<?, ?>) body.get("lesson");
        String lessonId = String.valueOf(lesson.get("id"));
        String versionId = String.valueOf(lesson.get("currentVersionId"));
        String content = String.valueOf(((Map<?, ?>) ((java.util.List<?>) body.get("versions")).get(0)).get("content"));
        String teachingHeader =
        "教学环节与教师活动 | 学生学习任务与产出 | 评价重点与调控";

        assertTrue(content.indexOf("课前说明") < content.indexOf(teachingHeader));
        assertTrue(content.indexOf(teachingHeader) < content.indexOf("课后反思"));
        mvc.perform(get("/api/platform/lessons/{lessonId}/versions/{versionId}/document", lessonId, versionId))
                .andDo(org.springframework.test.web.servlet.result.MockMvcResultHandlers.print())
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.parseStatus").value("PARSED"))
                .andExpect(jsonPath("$.parserName").value("APACHE_POI_DOCX"))
                .andExpect(jsonPath("$.document.blocks[0].text").value("课前说明"))
                .andExpect(jsonPath("$.document.blocks[1].type").value("teaching_process"))
                .andExpect(jsonPath("$.document.blocks[1].teachingProcess.rows[0].teacherActivity").value("导入问题"))
                .andExpect(jsonPath("$.document.blocks[1].teachingProcess.rows[0].studentActivity").value("合作探究"))
                .andExpect(jsonPath("$.document.blocks[2].text").value("课后反思"));
    }

    @Test
    void confirmedEditedTextUsesMatchingFallbackStructureInsteadOfStaleDocxTable() throws Exception {
        byte[] original = docxWithTextAndTable();
        MockMultipartFile file = new MockMultipartFile("file", "编辑确认.docx", DOCX_MEDIA, original);
        MvcResult created = mvc.perform(multipart("/api/platform/lessons/imports/docx")
                        .file(file).param("content", "教师确认后的唯一正文"))
                .andExpect(status().isCreated()).andReturn();
        Map<?, ?> body = mapper.readValue(created.getResponse().getContentAsString(StandardCharsets.UTF_8), Map.class);
        Map<?, ?> lesson = (Map<?, ?>) body.get("lesson");
        mvc.perform(get("/api/platform/lessons/{lessonId}/versions/{versionId}/document",
                        lesson.get("id"), lesson.get("currentVersionId")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.parseStatus").value("EDITED_FALLBACK"))
                .andExpect(jsonPath("$.document.blocks[0].text").value("教师确认后的唯一正文"))
                .andExpect(jsonPath("$.document.blocks.length()").value(1));
    }

    @Test
    void textImportStillUsesImportTextAndHasNoSourceDocument() throws Exception {
        String json = """
                {"title":"手工教案","subject":"数学","grade":"四年级","topic":"口算","durationMinutes":40,"content":"手工粘贴正文"}
                """;
        MvcResult created = mvc.perform(post("/api/platform/lessons")
                        .contentType(MediaType.APPLICATION_JSON).content(json))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.versions[0].sourceModule").value("IMPORT_TEXT"))
                .andReturn();
        Map<?, ?> body = mapper.readValue(created.getResponse().getContentAsString(StandardCharsets.UTF_8), Map.class);
        String lessonId = String.valueOf(((Map<?, ?>) body.get("lesson")).get("id"));
        mvc.perform(get("/api/platform/lessons/{lessonId}/source-document", lessonId))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("SOURCE_DOCUMENT_NOT_FOUND"));
    }

    @Test
    void transactionRollbackCleansNewlyStoredOriginal() throws Exception {
        byte[] docx = docxWithTextAndTable();
        MockMultipartFile file = new MockMultipartFile("file", "rollback.docx", DOCX_MEDIA, docx);
        TransactionTemplate template = new TransactionTemplate(transactionManager);
        String lessonId = template.execute(status -> {
            var created = imports.importDocx(file, new CreateLesson(
                    "回滚测试", "数学", "四年级", "回滚", 40, "确认后的正文"));
            String id = created.lesson().id();
            assertTrue(storage.exists("lessons/" + id + "/source/original.docx"));
            status.setRollbackOnly();
            return id;
        });
        assertFalse(storage.exists("lessons/" + lessonId + "/source/original.docx"));
        Integer rows = db.queryForObject("SELECT COUNT(*) FROM platform_lesson WHERE id = ?", Integer.class, lessonId);
        assertEquals(0, rows);
    }

    @Test
    void twoImportsWithSameFilenameCreateDifferentLessonsWithoutOverwrite() throws Exception {
        byte[] docx = docxWithTextAndTable();
        String first = importLesson(docx, "same.docx", "第一份");
        String second = importLesson(docx, "same.docx", "第二份");
        assertNotEquals(first, second);
        Integer rows = db.queryForObject("SELECT COUNT(*) FROM platform_lesson_source_document WHERE original_filename = 'same.docx'", Integer.class);
        assertEquals(2, rows);
    }

    private String importLesson(byte[] docx, String filename, String title) throws Exception {
        MockMultipartFile file = new MockMultipartFile("file", filename, DOCX_MEDIA, docx);
        MvcResult result = mvc.perform(multipart("/api/platform/lessons/imports/docx")
                        .file(file)
                        .param("title", title)
                        .param("subject", "数学")
                        .param("grade", "四年级")
                        .param("topic", "测试")
                        .param("durationMinutes", "40")
                        .param("content", "确认后的正文"))
                .andExpect(status().isCreated()).andReturn();
        Map<?, ?> body = mapper.readValue(result.getResponse().getContentAsString(StandardCharsets.UTF_8), Map.class);
        return String.valueOf(((Map<?, ?>) body.get("lesson")).get("id"));
    }

    private static byte[] docxWithTextAndTable() throws Exception {
        try (XWPFDocument document = new XWPFDocument(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.createParagraph().createRun().setText("教学目标");
            document.createParagraph().createRun().setText("理解小数加减法的算理。");
            XWPFTable table = document.createTable(2, 2);
            table.getRow(0).getCell(0).setText("教师活动");
            table.getRow(0).getCell(1).setText("学生活动");
            table.getRow(1).getCell(0).setText("提出问题");
            table.getRow(1).getCell(1).setText("合作探究");
            document.write(output);
            return output.toByteArray();
        }
    }

    private static byte[] emptyDocx() throws Exception {
        try (XWPFDocument document = new XWPFDocument(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.write(output);
            return output.toByteArray();
        }
    }

    private static byte[] docxWithParagraphTableParagraph() throws Exception {
        try (XWPFDocument document = new XWPFDocument(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.createParagraph().createRun().setText("课前说明");
            XWPFTable table = document.createTable(2, 3);
            table.getRow(0).getCell(0).setText("教学环节与教师活动");
            table.getRow(0).getCell(1).setText("学生学习任务与产出");
            table.getRow(0).getCell(2).setText("评价重点与调控");
            table.getRow(1).getCell(0).setText("导入问题");
            table.getRow(1).getCell(1).setText("合作探究");
            table.getRow(1).getCell(2).setText("观察证据");
            document.createParagraph().createRun().setText("课后反思");
            document.write(output);
            return output.toByteArray();
        }
    }

    private static String sha256(byte[] value) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
    }
}
