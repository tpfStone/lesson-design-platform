package com.zone.lesoongen.application.storage;

public record StoredObject(String storageKey, long sizeBytes, String sha256) {
}
