package com.zone.lesoongen.application.storage;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;

public interface StoragePort {
    StoredObject store(String storageKey, InputStream input, long maximumBytes) throws IOException;
    InputStream open(String storageKey) throws IOException;
    Path localPath(String storageKey);
    boolean exists(String storageKey);
    void delete(String storageKey) throws IOException;
}
