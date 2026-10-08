package com.zone.lesoongen.platform;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/platform/optimizations")
public class PlatformOptimizeHistoryController {
    private final PlatformOptimizeService service;

    public PlatformOptimizeHistoryController(PlatformOptimizeService service) { this.service = service; }

    @GetMapping
    public List<PlatformOptimizeService.History> list() { return service.history(); }
}
