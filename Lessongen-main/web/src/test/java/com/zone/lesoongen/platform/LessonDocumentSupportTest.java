package com.zone.lesoongen.platform;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.List;

import org.junit.jupiter.api.Test;

class LessonDocumentSupportTest {
    @Test
    void recognizesChineseFormalTeachingProcessHeaders() {
        var process = LessonDocumentSupport.teachingProcess(List.of(
                List.of("教学环节与教师活动", "学生学习任务与产出", "评价重点与调控"),
                List.of("导入 · 5分钟\n创设情境", "观察并回答", "检查已有经验")));

        assertNotNull(process);
        assertEquals(1, process.rows().size());
        assertEquals(5, process.rows().get(0).durationMinutes());
        assertEquals("观察并回答", process.rows().get(0).studentActivity());
    }

    @Test
    void recognizesCompactAndEnglishTeachingProcessHeaders() {
        var chinese = LessonDocumentSupport.teachingProcess(List.of(
                List.of("教师活动", "学生活动"),
                List.of("提出问题", "合作探究")));
        var english = LessonDocumentSupport.teachingProcess(List.of(
                List.of("Teacher Activities", "Student Activities", "Assessment"),
                List.of("Model the task", "Discuss in pairs", "Exit ticket")));

        assertNotNull(chinese);
        assertNotNull(english);
        assertEquals("Discuss in pairs", english.rows().get(0).studentActivity());
        assertEquals("Exit ticket", english.rows().get(0).evaluation());
    }

    @Test
    void preservesSeparateSectionAndTeacherColumns() {
        var process = LessonDocumentSupport.teachingProcess(List.of(
                List.of("教学环节", "教师活动", "学生活动", "设计意图"),
                List.of("新课导入（5分钟）", "展示情境", "观察回答", "诊断经验")));

        assertNotNull(process);
        assertEquals("新课导入", process.rows().get(0).title());
        assertEquals("展示情境", process.rows().get(0).teacherActivity());
        assertEquals("观察回答", process.rows().get(0).studentActivity());
        assertEquals("诊断经验", process.rows().get(0).evaluation());
    }

    @Test
    void plainTextProjectionPreservesBlockOrder() {
        LessonDocument document = LessonDocumentSupport.fromPlainText("""
                一、教学目标
                理解基本概念。

                教师活动 | 学生活动
                提出问题 | 合作探究

                二、课后反思
                """);

        assertEquals(List.of("heading", "paragraph", "teaching_process", "heading"),
                document.blocks().stream().map(LessonDocument.Block::type).toList());
        String projected = LessonDocumentSupport.renderText(document);
        assertEquals(true, projected.indexOf("教学目标") < projected.indexOf("教师活动 | 学生活动"));
        assertEquals(true, projected.indexOf("教师活动 | 学生活动") < projected.indexOf("课后反思"));
    }
}
