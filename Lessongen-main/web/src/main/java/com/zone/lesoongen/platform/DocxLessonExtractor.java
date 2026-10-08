package com.zone.lesoongen.platform;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import org.apache.poi.xwpf.usermodel.IBodyElement;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.apache.poi.xwpf.usermodel.XWPFTableCell;
import org.apache.poi.xwpf.usermodel.XWPFTableRow;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.platform.LessonDocument.Block;

/** Extracts readable DOCX body text without OCR and rejects malformed/non-DOCX uploads. */
@Component
public class DocxLessonExtractor {
    public static final int MAX_CONTENT_CHARS = 100_000;
    private static final int MAX_ZIP_ENTRIES = 10_000;
    private static final long MAX_DECLARED_ENTRY_BYTES = 64L * 1024 * 1024;
    private static final long MAX_EXPANDED_BYTES = 128L * 1024 * 1024;

    public record ExtractedDocument(
            String originalFilename,
            long sizeBytes,
            String extractedContent,
            LessonDocument structuredContent,
            List<String> warnings) {
    }

    public ExtractedDocument extract(MultipartFile file, long maximumBytes) {
        String filename = safeFilename(file == null ? null : file.getOriginalFilename());
        if (file == null || file.isEmpty() || !filename.toLowerCase(Locale.ROOT).endsWith(".docx")) {
            throw new AppException(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "INVALID_DOCX",
                    "请选择真正的 .docx 教案文件");
        }
        if (file.getSize() > maximumBytes) {
            throw new AppException(HttpStatus.PAYLOAD_TOO_LARGE, "DOCX_TOO_LARGE",
                    "Word 文件超过 20 MiB 限制");
        }

        byte[] bytes;
        try {
            bytes = file.getBytes();
        } catch (IOException error) {
            throw new AppException(HttpStatus.BAD_REQUEST, "DOCX_READ_FAILED", "无法读取上传文件");
        }
        if (bytes.length == 0 || bytes.length > maximumBytes) {
            throw new AppException(bytes.length > maximumBytes ? HttpStatus.PAYLOAD_TOO_LARGE : HttpStatus.BAD_REQUEST,
                    bytes.length > maximumBytes ? "DOCX_TOO_LARGE" : "DOCX_READ_FAILED",
                    bytes.length > maximumBytes ? "Word 文件超过 20 MiB 限制" : "无法读取上传文件");
        }
        validateOoxmlPackage(bytes);

        List<String> warnings = new ArrayList<>();
        LessonDocument structured;
        try (XWPFDocument document = new XWPFDocument(new ByteArrayInputStream(bytes))) {
            List<Block> blocks = new ArrayList<>();
            List<String> pendingList = new ArrayList<>();
            Boolean pendingOrdered = null;
            int nextId = 1;
            for (IBodyElement element : document.getBodyElements()) {
                if (element instanceof XWPFParagraph paragraph) {
                    String text = normalize(paragraph.getText());
                    if (text.isBlank()) {
                        if (!pendingList.isEmpty()) {
                            blocks.add(listBlock(nextId++, pendingOrdered, pendingList));
                            pendingList.clear();
                            pendingOrdered = null;
                        }
                        continue;
                    }
                    Boolean ordered = listKind(paragraph);
                    if (ordered != null) {
                        if (pendingOrdered != null && !pendingOrdered.equals(ordered)) {
                            blocks.add(listBlock(nextId++, pendingOrdered, pendingList));
                            pendingList.clear();
                        }
                        pendingOrdered = ordered;
                        pendingList.add(text);
                        continue;
                    }
                    if (!pendingList.isEmpty()) {
                        blocks.add(listBlock(nextId++, pendingOrdered, pendingList));
                        pendingList.clear();
                        pendingOrdered = null;
                    }
                    Integer headingLevel = headingLevel(paragraph, text);
                    blocks.add(new Block("b" + nextId++, headingLevel == null ? "paragraph" : "heading",
                            headingLevel, text, null, List.of(), List.of(), null));
                } else if (element instanceof XWPFTable table) {
                    if (!pendingList.isEmpty()) {
                        blocks.add(listBlock(nextId++, pendingOrdered, pendingList));
                        pendingList.clear();
                        pendingOrdered = null;
                    }
                    blocks.add(LessonDocumentSupport.tableBlock("b" + nextId++, tableRows(table)));
                }
            }
            if (!pendingList.isEmpty()) blocks.add(listBlock(nextId, pendingOrdered, pendingList));
            structured = new LessonDocument(LessonDocument.SCHEMA_VERSION, blocks);
            if (!document.getAllPictures().isEmpty()) {
                warnings.add("检测到图片；当前只提取可读取文字，不执行 OCR。");
            }
        } catch (AppException error) {
            throw error;
        } catch (Exception error) {
            throw new AppException(HttpStatus.BAD_REQUEST, "DOCX_READ_FAILED",
                    "Word 文件损坏或无法解析，请重新导出为标准 .docx 后再试");
        }

        String content = LessonDocumentSupport.renderText(structured);
        if (content.isBlank()) {
            throw new AppException(HttpStatus.UNPROCESSABLE_ENTITY, "DOCX_EMPTY_CONTENT",
                    "未从 Word 文件中读取到正文；仅图片或空白文档暂不支持");
        }
        if (content.length() > MAX_CONTENT_CHARS) {
            throw new AppException(HttpStatus.UNPROCESSABLE_ENTITY, "DOCX_CONTENT_TOO_LONG",
                    "提取后的教案正文超过 100000 字符限制");
        }
        return new ExtractedDocument(filename, bytes.length, content, structured, List.copyOf(warnings));
    }

    static String safeFilename(String input) {
        String value = input == null ? "lesson.docx" : input.replace('\\', '/');
        value = value.substring(value.lastIndexOf('/') + 1).replaceAll("[\\r\\n\"]", "_").trim();
        if (value.isBlank()) {
            value = "lesson.docx";
        }
        return value.substring(0, Math.min(value.length(), 200));
    }

    private static void validateOoxmlPackage(byte[] bytes) {
        if (bytes.length < 4 || bytes[0] != 'P' || bytes[1] != 'K' || bytes[2] != 3 || bytes[3] != 4) {
            throw invalidDocx("文件不是有效的 OOXML Word 包");
        }
        boolean contentTypes = false;
        boolean documentXml = false;
        int entries = 0;
        long expandedBytes = 0;
        byte[] buffer = new byte[8192];
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(bytes))) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                entries++;
                if (entries > MAX_ZIP_ENTRIES) {
                    throw invalidDocx("Word 文件内部条目异常过多");
                }
                if (entry.getSize() > MAX_DECLARED_ENTRY_BYTES) {
                    throw new AppException(HttpStatus.PAYLOAD_TOO_LARGE, "DOCX_TOO_LARGE",
                            "Word 文件解压后的单个内容过大");
                }
                String name = entry.getName().replace('\\', '/');
                contentTypes |= "[Content_Types].xml".equals(name);
                documentXml |= "word/document.xml".equals(name);
                int count;
                long entryBytes = 0;
                while ((count = zip.read(buffer)) >= 0) {
                    entryBytes += count;
                    expandedBytes += count;
                    if (entryBytes > MAX_DECLARED_ENTRY_BYTES || expandedBytes > MAX_EXPANDED_BYTES) {
                        throw new AppException(HttpStatus.PAYLOAD_TOO_LARGE, "DOCX_TOO_LARGE",
                                "Word 文件解压后的内容超过安全限制");
                    }
                }
                zip.closeEntry();
            }
        } catch (AppException error) {
            throw error;
        } catch (IOException | RuntimeException error) {
            throw invalidDocx("文件不是有效的 DOCX 压缩包");
        }
        if (!contentTypes || !documentXml) {
            throw invalidDocx("文件缺少标准 DOCX 文档结构");
        }
    }

    private static AppException invalidDocx(String message) {
        return new AppException(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "INVALID_DOCX", message);
    }

    private static List<List<String>> tableRows(XWPFTable table) {
        List<List<String>> rows = new ArrayList<>();
        for (XWPFTableRow row : table.getRows()) {
            List<String> cells = new ArrayList<>();
            for (XWPFTableCell cell : row.getTableCells()) {
                List<String> paragraphs = cell.getParagraphs().stream()
                        .map(XWPFParagraph::getText)
                        .map(DocxLessonExtractor::normalize)
                        .filter(text -> !text.isBlank())
                        .toList();
                String cellText = String.join(" / ", paragraphs);
                if (cellText.isBlank()) {
                    cellText = normalize(cell.getText());
                }
                cells.add(cellText);
            }
            if (cells.stream().anyMatch(text -> !text.isBlank())) rows.add(List.copyOf(cells));
        }
        return List.copyOf(rows);
    }

    private static Block listBlock(int id, Boolean ordered, List<String> items) {
        return new Block("b" + id, "list", null, null, Boolean.TRUE.equals(ordered),
                List.copyOf(items), List.of(), null);
    }

    /** null means regular paragraph; false/true mean unordered/ordered list. */
    private static Boolean listKind(XWPFParagraph paragraph) {
        if (paragraph.getNumID() == null) return null;
        String format = paragraph.getNumFmt();
        if (format == null) return false;
        return !format.toLowerCase(Locale.ROOT).contains("bullet");
    }

    private static Integer headingLevel(XWPFParagraph paragraph, String text) {
        String style = paragraph.getStyle();
        if (style != null) {
            String normalized = style.toLowerCase(Locale.ROOT).replace(" ", "");
            java.util.regex.Matcher english = java.util.regex.Pattern.compile("heading([1-6])").matcher(normalized);
            if (english.find()) return Integer.valueOf(english.group(1));
            java.util.regex.Matcher chinese = java.util.regex.Pattern.compile("标题([1-6])").matcher(style);
            if (chinese.find()) return Integer.valueOf(chinese.group(1));
        }
        return LessonDocumentSupport.looksLikeHeading(text)
                ? LessonDocumentSupport.inferredHeadingLevel(text) : null;
    }

    private static String normalize(String value) {
        return LessonDocumentSupport.normalize(value);
    }
}
