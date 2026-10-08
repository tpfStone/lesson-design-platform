package com.zone.lesoongen.platform;

import java.util.List;

/**
 * Versioned, ordered representation of a lesson plan.
 *
 * <p>The legacy {@code platform_lesson_version.content} remains the compatibility projection.
 * This document is the loss-reduced source for Web rendering and future F3/F4/export adapters.</p>
 */
public record LessonDocument(String schemaVersion, List<Block> blocks) {
    public static final String SCHEMA_VERSION = "1.0";

    public LessonDocument {
        schemaVersion = schemaVersion == null || schemaVersion.isBlank() ? SCHEMA_VERSION : schemaVersion;
        blocks = blocks == null ? List.of() : List.copyOf(blocks);
    }

    public record Block(
            String id,
            String type,
            Integer level,
            String text,
            Boolean ordered,
            List<String> items,
            List<List<String>> tableRows,
            TeachingProcess teachingProcess) {
        public Block {
            items = items == null ? List.of() : List.copyOf(items);
            tableRows = tableRows == null ? List.of() : tableRows.stream()
                    .map(row -> row == null ? List.<String>of() : List.copyOf(row))
                    .toList();
        }
    }

    public record TeachingProcess(List<String> columns, List<TeachingProcessRow> rows) {
        public TeachingProcess {
            columns = columns == null ? List.of() : List.copyOf(columns);
            rows = rows == null ? List.of() : List.copyOf(rows);
        }
    }

    public record TeachingProcessRow(
            int sourceRowIndex,
            String title,
            Integer durationMinutes,
            String teacherActivity,
            String studentActivity,
            String evaluation,
            List<String> extraCells) {
        public TeachingProcessRow {
            extraCells = extraCells == null ? List.of() : List.copyOf(extraCells);
        }
    }
}
