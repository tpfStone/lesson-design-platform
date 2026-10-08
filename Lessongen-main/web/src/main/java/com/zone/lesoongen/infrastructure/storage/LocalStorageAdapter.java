package com.zone.lesoongen.infrastructure.storage;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.DigestInputStream;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

import org.springframework.stereotype.Component;

import com.zone.lesoongen.application.storage.StoragePort;
import com.zone.lesoongen.application.storage.StoredObject;
import com.zone.lesoongen.config.AppProperties;

@Component
public class LocalStorageAdapter implements StoragePort {
    private final Path root;

    public LocalStorageAdapter(AppProperties properties) throws IOException {
        this.root = properties.storageRoot().toAbsolutePath().normalize();
        Files.createDirectories(root);
    }

    @Override
    public StoredObject store(String storageKey, InputStream input, long maximumBytes) throws IOException {
        Path destination = localPath(storageKey);
        Files.createDirectories(destination.getParent());
        Path temporary = Files.createTempFile(destination.getParent(), ".upload-", ".tmp");
        MessageDigest digest = sha256();
        long total = 0;
        try (DigestInputStream source = new DigestInputStream(input, digest);
                OutputStream output = Files.newOutputStream(temporary)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = source.read(buffer)) >= 0) {
                total += count;
                if (total > maximumBytes) {
                    throw new StorageLimitException("file exceeds configured byte limit");
                }
                output.write(buffer, 0, count);
            }
        } catch (Exception error) {
            Files.deleteIfExists(temporary);
            throw error;
        }
        try {
            Files.move(temporary, destination, StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException ignored) {
            Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING);
        }
        return new StoredObject(storageKey, total, HexFormat.of().formatHex(digest.digest()));
    }

    @Override
    public InputStream open(String storageKey) throws IOException {
        return Files.newInputStream(localPath(storageKey));
    }

    @Override
    public Path localPath(String storageKey) {
        if (storageKey == null || storageKey.isBlank() || Path.of(storageKey).isAbsolute()) {
            throw new IllegalArgumentException("storage key must be a non-empty relative path");
        }
        Path path = root.resolve(storageKey.replace('\\', '/')).normalize();
        if (!path.startsWith(root) || path.equals(root)) {
            throw new IllegalArgumentException("storage key escaped configured root");
        }
        return path;
    }

    @Override
    public boolean exists(String storageKey) {
        return Files.isRegularFile(localPath(storageKey));
    }

    @Override
    public void delete(String storageKey) throws IOException {
        Files.deleteIfExists(localPath(storageKey));
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    public static class StorageLimitException extends IOException {
        public StorageLimitException(String message) {
            super(message);
        }
    }
}
