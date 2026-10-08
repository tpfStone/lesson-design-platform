package com.zone.lesoongen.platform;

import java.util.UUID;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

@RestController
@RequestMapping("/api/platform/navigation")
public class PlatformNavigationBridgeController {
    private final PlatformNavigationBridgeService bridge;
    public PlatformNavigationBridgeController(PlatformNavigationBridgeService bridge) { this.bridge = bridge; }

    public record Start(@NotBlank @Size(max = 26) String versionId, @NotNull UUID requestKey,
            @Size(max = 100) String subject, @Size(max = 100) String grade,
            @Size(max = 200) String topic) {}
    public record Save(@Size(max = 26) String expectedVersionId, @NotNull UUID roundId,
            @NotBlank @Pattern(regexp = "[0-9a-f]{64}") String expectedContentSha256) {}

    @PostMapping("/lessons/{lessonId}/sessions")
    public PlatformNavigationBridgeService.Started start(@PathVariable("lessonId") String lessonId,
            @Valid @RequestBody Start input) {
        return bridge.start(lessonId, input.versionId(), input.requestKey(),
                input.subject(), input.grade(), input.topic());
    }

    @GetMapping("/sessions/{sessionId}/binding")
    public PlatformNavigationBridgeService.BindingContext binding(@PathVariable("sessionId") UUID sessionId) {
        return bridge.context(sessionId.toString());
    }

    @PostMapping("/sessions/{sessionId}/writeback")
    public PlatformNavigationBridgeService.Saved save(@PathVariable("sessionId") UUID sessionId,
            @Valid @RequestBody Save input) {
        return bridge.save(sessionId.toString(), input);
    }
    @PostMapping("/sessions/{sessionId}/issues/sync")
    public PlatformNavigationBridgeService.IssueSyncResult syncIssues(@PathVariable("sessionId") UUID sessionId) {
        return bridge.syncIssues(sessionId.toString());
    }
}
