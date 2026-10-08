package com.zone.lesoongen.platform;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFRun;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.apache.poi.xwpf.usermodel.XWPFTableCell;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.application.LessonResultService;
import com.zone.lesoongen.domain.artifact.ArtifactType;
import com.zone.lesoongen.platform.PlatformLessonController.LessonVersion;

@RestController
@RequestMapping("/api/platform/lessons")
public class PlatformLessonExportController {
    private static final MediaType DOCX = MediaType.parseMediaType(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
    private static final Pattern HEADING = Pattern.compile("^(#{1,3})\\s+(.+)$");
    private static final Pattern SECTION = Pattern.compile("^[一二三四五六七八九十]+[、．.]\\s*[^。]{1,28}$");
    private static final Pattern NATIVE_F2_JOB = Pattern.compile("^f2:([^:]+)(:teacher-reviewed)?$");

    private final PlatformLessonService lessons;
    private final LessonResultService results;

    public PlatformLessonExportController(PlatformLessonService lessons, LessonResultService results) {
        this.lessons = lessons;
        this.results = results;
    }

    @GetMapping("/{lessonId}/versions/{versionId}/export/docx")
    public ResponseEntity<byte[]> exportDocx(@PathVariable String lessonId, @PathVariable String versionId)
            throws IOException {
        var detail = lessons.detail(lessonId);
        var version = detail.versions().stream().filter(v -> v.id().equals(versionId)).findFirst()
                .orElseThrow(() -> new AppException(HttpStatus.NOT_FOUND, "RESOURCE_NOT_FOUND", "教案版本不存在"));

        // F2 原生版本优先复用任务本身生成的漂亮 Word。
        // 不仅检查 jobId，还会把候选 Word 重新抽取为纯文本，与当前 version.content 比较。
        // 只有正文一致时才返回原生 Word，避免 teacher-reviewed / 历史 artifact 内容错版。
        byte[] bytes = nativeF2Docx(version);
        if (bytes == null) {
            bytes = fallbackDocx(detail.lesson().title(), version.versionNumber(), version.content());
        }

        String filename = detail.lesson().title().replaceAll("[\\p{Cntrl}\\\\/:*?\"<>|]", "_");
        if (filename.isBlank()) filename = "教案";
        String disposition = ContentDisposition.attachment()
                .filename(filename + "-V" + version.versionNumber() + ".docx", StandardCharsets.UTF_8)
                .build().toString();
        return ResponseEntity.ok().contentType(DOCX).contentLength(bytes.length)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition).body(bytes);
    }

    private byte[] nativeF2Docx(LessonVersion version) {
        String reference = version.nativeReference();
        if (reference == null || reference.isBlank()) return null;

        Matcher matcher = NATIVE_F2_JOB.matcher(reference.trim());
        if (!matcher.matches()) return null;

        String jobId = matcher.group(1);
        boolean teacherReviewed = matcher.group(2) != null;

        try {
            var available = results.artifacts(jobId);

            // 自动保存的 F2 版本来自 BEST_DOCX。
            // teacher-reviewed 版本通常来自 revised_candidate；若当时没有 candidate，也可能来自 BEST_DOCX。
            List<ArtifactType> preferred = teacherReviewed
                    ? List.of(ArtifactType.REVISED_CANDIDATE_DOCX, ArtifactType.BEST_DOCX)
                    : List.of(ArtifactType.BEST_DOCX);

            for (ArtifactType type : preferred) {
                var artifact = available.stream()
                        .filter(item -> item.type() == type)
                        .findFirst()
                        .orElse(null);
                if (artifact == null) continue;

                var download = results.download(jobId, artifact.artifactId());
                byte[] bytes;
                try (var input = download.resource().getInputStream()) {
                    bytes = input.readAllBytes();
                }

                String artifactContent = extractDocxText(bytes);
                if (sameContent(artifactContent, version.content())) {
                    return bytes;
                }
            }
        } catch (RuntimeException | IOException ignored) {
            // 原生产物不存在、已清理、解析失败或正文不一致时，不阻断下载；
            // 继续使用当前版本正文导出，保证“下载内容一定对应当前 version”。
            return null;
        }
        return null;
    }

    /**
     * 必须和 PlatformOptimizeService.readDocx(...) 的正文抽取规则保持一致：
     * 段落按正文顺序写入；表格按行展开，单元格之间使用 tab。
     */
    private static String extractDocxText(byte[] bytes) throws IOException {
        try (var input = new ByteArrayInputStream(bytes);
                var document = new XWPFDocument(input)) {
            List<String> lines = new ArrayList<>();
            for (var element : document.getBodyElements()) {
                if (element instanceof XWPFParagraph paragraph) {
                    lines.add(paragraph.getText());
                } else if (element instanceof XWPFTable table) {
                    for (var row : table.getRows()) {
                        lines.add(row.getTableCells().stream()
                                .map(cell -> cell.getText())
                                .reduce((a, b) -> a + "\t" + b)
                                .orElse(""));
                    }
                }
            }
            return String.join("\n", lines).trim();
        }
    }

    private static boolean sameContent(String left, String right) {
        if (left == null || right == null) return false;
        return normalizeNewlines(left).trim().equals(normalizeNewlines(right).trim());
    }

    private static String normalizeNewlines(String value) {
        return value.replace("\r\n", "\n").replace('\r', '\n');
    }

    private static byte[] fallbackDocx(String title, int versionNumber, String content) throws IOException {
        try (var document = new XWPFDocument(); var output = new ByteArrayOutputStream()) {
            addParagraph(document, title, 18, true, true);
            addParagraph(document, "教案版本 V" + versionNumber, 10, false, false);
            appendContent(document, content);
            document.write(output);
            return output.toByteArray();
        }
    }

    private static void appendContent(XWPFDocument document, String content) {
        String[] lines = content.split("\\R", -1);
        for (int index = 0; index < lines.length; index++) {
            String line = lines[index].trim();
            if (line.isBlank()) continue;
            if (line.startsWith("> 运行 ") || line.startsWith("> 运行`")) continue;
            Matcher heading = HEADING.matcher(line);
            if (heading.matches()) {
                int depth = heading.group(1).length();
                addParagraph(document, clean(heading.group(2)), depth == 1 ? 16 : depth == 2 ? 14 : 12, true,
                        depth == 1);
                continue;
            }
            if (line.startsWith("|") && line.endsWith("|")) {
                List<List<String>> rows = new ArrayList<>();
                while (index < lines.length && lines[index].trim().startsWith("|")
                        && lines[index].trim().endsWith("|")) {
                    List<String> cells = tableCells(lines[index].trim());
                    if (!cells.stream().allMatch(cell -> cell.matches(":?-{3,}:?"))) rows.add(cells);
                    index++;
                }
                index--;
                addTable(document, rows);
                continue;
            }
            if (line.startsWith(">")) {
                addParagraph(document, clean(line.substring(1).trim()), 10, false, false);
            } else if (line.matches("^[-*]\\s+.*")) {
                addParagraph(document, "• " + clean(line.substring(2)), 11, false, false);
            } else if (SECTION.matcher(line).matches()) {
                addParagraph(document, clean(line), 14, true, false);
            } else {
                addParagraph(document, clean(line), 11, false, false);
            }
        }
    }

    private static List<String> tableCells(String line) {
        List<String> cells = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        for (int index = 1; index < line.length() - 1; index++) {
            char ch = line.charAt(index);
            if (ch == '\\' && index + 1 < line.length() - 1 && line.charAt(index + 1) == '|') {
                current.append('|');
                index++;
            } else if (ch == '|') {
                cells.add(clean(current.toString()));
                current.setLength(0);
            } else {
                current.append(ch);
            }
        }
        cells.add(clean(current.toString()));
        return cells;
    }

    private static void addTable(XWPFDocument document, List<List<String>> rows) {
        if (rows.isEmpty()) return;
        int columns = rows.stream().mapToInt(List::size).max().orElse(1);
        XWPFTable table = document.createTable(rows.size(), columns);
        for (int row = 0; row < rows.size(); row++) {
            for (int column = 0; column < rows.get(row).size(); column++) {
                XWPFTableCell cell = table.getRow(row).getCell(column);
                cell.removeParagraph(0);
                XWPFParagraph paragraph = cell.addParagraph();
                paragraph.setSpacingAfter(80);
                XWPFRun run = paragraph.createRun();
                run.setFontFamily("Microsoft YaHei");
                run.setFontSize(10);
                run.setBold(row == 0);
                String[] parts = rows.get(row).get(column).split("\\n", -1);
                for (int partIndex = 0; partIndex < parts.length; partIndex++) {
                    if (partIndex > 0) run.addBreak();
                    run.setText(parts[partIndex]);
                }
            }
        }
        document.createParagraph().setSpacingAfter(120);
    }

    private static String clean(String value) {
        return value.trim().replaceAll("(?i)<br\\s*/?>", "\n")
                .replaceAll("\\*\\*(.*?)\\*\\*", "$1")
                .replaceAll("`([^`]*)`", "$1");
    }

    private static void addParagraph(XWPFDocument document, String text, int size, boolean bold, boolean centered) {
        XWPFParagraph paragraph = document.createParagraph();
        paragraph.setSpacingAfter(size >= 14 ? 190 : 100);
        if (centered) paragraph.setAlignment(org.apache.poi.xwpf.usermodel.ParagraphAlignment.CENTER);
        XWPFRun run = paragraph.createRun();
        run.setFontFamily("Microsoft YaHei");
        run.setFontSize(size);
        run.setBold(bold);
        String[] parts = text.split("\\n", -1);
        for (int index = 0; index < parts.length; index++) {
            if (index > 0) run.addBreak();
            run.setText(parts[index]);
        }
    }
}
