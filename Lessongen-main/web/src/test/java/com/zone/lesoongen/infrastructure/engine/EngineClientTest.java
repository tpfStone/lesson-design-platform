package com.zone.lesoongen.infrastructure.engine;

import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.equalTo;
import static com.github.tomakehurst.wiremock.client.WireMock.post;
import static com.github.tomakehurst.wiremock.client.WireMock.postRequestedFor;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.core.WireMockConfiguration;
import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.infrastructure.engine.EngineContracts.CreateRequest;
import com.zone.lesoongen.infrastructure.engine.EngineContracts.LessonInput;

import tools.jackson.databind.ObjectMapper;

class EngineClientTest {
    private static WireMockServer server;
    private EngineClient client;

    @BeforeAll
    static void startServer() {
        server = new WireMockServer(WireMockConfiguration.options().dynamicPort());
        try {
            server.start();
        } catch (RuntimeException unavailableLoopback) {
            // Some locked-down Windows runners disallow the selector's loopback pipe. Keep the
            // contract test enabled in normal developer/CI environments and report an honest skip.
            assumeTrue(false, "local loopback sockets unavailable: "
                    + unavailableLoopback.getClass().getSimpleName());
        }
    }

    @AfterAll
    static void stopServer() {
        if (server != null && server.isRunning()) {
            server.stop();
        }
    }

    @BeforeEach
    void resetServer() {
        server.resetAll();
        client = clientWithTimeout(Duration.ofSeconds(2));
    }

    @Test
    void createIsAuthenticatedAndSafeToRepeatWithTheSameExternalId() {
        server.stubFor(post("/internal/v1/runs/generate").willReturn(aResponse()
                .withStatus(202).withHeader("Content-Type", "application/json")
                .withBody("""
                        {"engine_run_id":"run-001","external_job_id":"01J00000000000000000000000",
                         "status":"queued","created_at":"2026-09-11T07:00:00Z"}
                        """)));

        assertEquals("run-001", client.submitGenerate(request()).engineRunId());
        assertEquals("run-001", client.submitGenerate(request()).engineRunId());
        server.verify(2, postRequestedFor(urlEqualTo("/internal/v1/runs/generate"))
                .withHeader("X-Engine-Token", equalTo("engine-test-token")));
    }

    @ParameterizedTest
    @CsvSource({"402,MODEL_BALANCE_EXHAUSTED", "429,MODEL_RATE_LIMITED", "503,ENGINE_UNAVAILABLE"})
    void translatesStableUpstreamErrorCodes(int status, String expectedCode) {
        server.stubFor(post("/internal/v1/runs/generate")
                .willReturn(aResponse().withStatus(status).withHeader("Content-Type", "application/problem+json")
                        .withBody("{\"code\":\"UPSTREAM_DETAIL_MUST_NOT_LEAK\"}")));

        RestClientException failure = assertThrows(RestClientException.class,
                () -> client.submitGenerate(request()));
        AppException translated = EngineClient.translate(failure);
        assertEquals(expectedCode, translated.code());
    }

    @Test
    void mapsReadTimeoutToEngineUnavailable() {
        server.stubFor(post("/internal/v1/runs/generate")
                .willReturn(aResponse().withFixedDelay(500).withStatus(202)));
        EngineClient shortTimeout = clientWithTimeout(Duration.ofMillis(50));

        RestClientException failure = assertThrows(RestClientException.class,
                () -> shortTimeout.submitGenerate(request()));
        assertEquals("ENGINE_UNAVAILABLE", EngineClient.translate(failure).code());
    }

    private EngineClient clientWithTimeout(Duration timeout) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(timeout);
        factory.setReadTimeout(timeout);
        RestClient restClient = RestClient.builder().baseUrl(server.baseUrl())
                .requestFactory(factory)
                .defaultHeader("X-Engine-Token", "engine-test-token")
                .build();
        return new EngineClient(restClient, new ObjectMapper());
    }

    private static CreateRequest request() {
        LessonInput task = new LessonInput("generate", "化学", "高一", "酸碱中和",
                45, "", "", "", List.of(), List.of(), "", null, List.of(), "",
                "choose_the_best_fit_for_this_topic", "showcase", List.of(), List.of());
        return new CreateRequest("1", "01J00000000000000000000000", "a".repeat(64), task);
    }
}
