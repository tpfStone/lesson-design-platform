package com.zone.lesoongen.platform;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.ByteArrayOutputStream;
import java.util.List;

import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

class DocxLessonExtractorTest {
    private static final String DOCX_MEDIA =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

    @Test
    void singleSevenByFourTeachingTableStaysWholeAndProducesSixProcessRows() throws Exception {
        byte[] docx;
        try (XWPFDocument document = new XWPFDocument();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.createParagraph().createRun().setText("六、教学过程");
            XWPFTable table = document.createTable(7, 4);
            setRow(table, 0, "环节与时间", "教师活动", "学生活动 / 可能反应", "评价与证据");
            setProcessRow(table, 1, "1. 情境导入", 5);
            setProcessRow(table, 2, "2. 小组探究", 12);
            setProcessRow(table, 3, "3. 汇报归纳", 8);
            setProcessRow(table, 4, "4. 练习应用", 9);
            setProcessRow(table, 5, "5. 开放挑战", 4);
            setProcessRow(table, 6, "6. 总结与作业", 2);
            document.write(output);
            docx = output.toByteArray();
        }

        var file = new MockMultipartFile("file", "小学数学_三角形的面积.docx", DOCX_MEDIA, docx);
        var extracted = new DocxLessonExtractor().extract(file, 20L * 1024 * 1024);
        var processBlock = extracted.structuredContent().blocks().stream()
                .filter(block -> "teaching_process".equals(block.type()))
                .findFirst().orElseThrow();

        assertEquals(7, processBlock.tableRows().size());
        assertNotNull(processBlock.teachingProcess());
        assertEquals(6, processBlock.teachingProcess().rows().size());
        assertEquals(List.of("情境导入", "小组探究", "汇报归纳", "练习应用", "开放挑战", "总结与作业"),
                processBlock.teachingProcess().rows().stream().map(LessonDocument.TeachingProcessRow::title).toList());
        assertEquals(List.of(5, 12, 8, 9, 4, 2),
                processBlock.teachingProcess().rows().stream()
                        .map(LessonDocument.TeachingProcessRow::durationMinutes).toList());
        assertEquals("教师活动 1", processBlock.teachingProcess().rows().get(0).teacherActivity());
        assertEquals("学生活动 1", processBlock.teachingProcess().rows().get(0).studentActivity());
        assertEquals("评价证据 1", processBlock.teachingProcess().rows().get(0).evaluation());
    }

    private static void setProcessRow(XWPFTable table, int row, String title, int minutes) {
        var firstCell = table.getRow(row).getCell(0);
        firstCell.setText(title);
        firstCell.addParagraph().createRun().setText(minutes + "分钟");
        setCell(table, row, 1, "教师活动 " + row);
        setCell(table, row, 2, "学生活动 " + row);
        setCell(table, row, 3, "评价证据 " + row);
    }

    private static void setRow(XWPFTable table, int row, String... values) {
        for (int column = 0; column < values.length; column++) setCell(table, row, column, values[column]);
    }

    private static void setCell(XWPFTable table, int row, int column, String value) {
        table.getRow(row).getCell(column).setText(value);
    }
}
