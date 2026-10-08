package com.zone.lesoongen.infrastructure.storage;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.zone.lesoongen.config.AppProperties;

class LocalStorageAdapterTest {
    private Path directory;

    @BeforeEach
    void createWorkspaceLocalDirectory() throws Exception {
        directory = Path.of("target", "test-data", "local-storage", UUID.randomUUID().toString())
                .toAbsolutePath();
        Files.createDirectories(directory);
    }

    @AfterEach
    void removeWorkspaceLocalDirectory() throws Exception {
        if (!Files.exists(directory)) {
            return;
        }
        try (var paths = Files.walk(directory)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    @Test
    void atomicallyStoresAndHashesContent() throws Exception {
        LocalStorageAdapter storage = new LocalStorageAdapter(properties());
        byte[] value = "真实教案".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        var stored = storage.store("jobs/one/result.json", new ByteArrayInputStream(value), 100);
        assertEquals(value.length, stored.sizeBytes());
        assertEquals(64, stored.sha256().length());
        assertArrayEquals(value, Files.readAllBytes(storage.localPath(stored.storageKey())));
    }

    @Test
    void rejectsRootEscapeAndCleansOversizedTemporaryFiles() throws Exception {
        LocalStorageAdapter storage = new LocalStorageAdapter(properties());
        assertThrows(IllegalArgumentException.class, () -> storage.localPath("../secret.env"));
        assertThrows(LocalStorageAdapter.StorageLimitException.class,
                () -> storage.store("jobs/one/large.bin",
                        new ByteArrayInputStream(new byte[32]), 10));
        try (var files = Files.list(directory.resolve("jobs/one"))) {
            assertEquals(0, files.count());
        }
    }


    @Test
    void deletesOnlyResolvedSingleFile() throws Exception {
        LocalStorageAdapter storage = new LocalStorageAdapter(properties());
        storage.store("lessons/one/source/original.docx",
                new ByteArrayInputStream("docx".getBytes(java.nio.charset.StandardCharsets.UTF_8)), 100);
        assertTrue(storage.exists("lessons/one/source/original.docx"));
        storage.delete("lessons/one/source/original.docx");
        assertFalse(storage.exists("lessons/one/source/original.docx"));
        assertThrows(IllegalArgumentException.class, () -> storage.delete("../outside.txt"));
    }

    private AppProperties properties() {
        return new AppProperties("http://127.0.0.1:8001", "test", directory,
                20 * 1024 * 1024, 1, 30, false, "http://127.0.0.1:5173");
    }
}
