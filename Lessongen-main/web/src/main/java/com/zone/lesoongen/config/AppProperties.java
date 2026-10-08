package com.zone.lesoongen.config;

import java.nio.file.Path;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String engineBaseUrl,
        String engineInternalToken,
        Path storageRoot,
        long maxUploadBytes,
        int maxConcurrentJobs,
        int artifactRetentionDays,
        boolean schedulingEnabled,
        String frontendOrigin) {
}
