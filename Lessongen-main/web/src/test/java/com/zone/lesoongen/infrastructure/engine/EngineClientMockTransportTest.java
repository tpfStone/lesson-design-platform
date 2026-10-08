package com.zone.lesoongen.infrastructure.engine;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.ExpectedCount.times;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.ExpectedCount;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.zone.lesoongen.application.AppException;
import com.zone.lesoongen.infrastructure.engine.EngineContracts.CreateRequest;
import com.zone.lesoongen.infrastructure.engine.EngineContracts.LessonInput;

import tools.jackson.databind.ObjectMapper;

/** Socket-free contract coverage for restricted runners; WireMock still covers real timeouts. */
class EngineClientMockTransportTest {
    @Test
    void writesAuthenticatedSnakeCaseContractAndReadsAcceptedResponse() {
        Harness harness = harness();
        harness.server.expect(once(), requestTo("http://engine.test/internal/v1/runs/generate"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("X-Engine-Token", "engine-test-token"))
                .andExpect(content().string(containsString("\"external_job_id\"")))
                .andExpect(content().string(containsString("\"duration_minutes\":45")))
                .andRespond(withSuccess("""
                        {"engine_run_id":"run-001","external_job_id":"01J00000000000000000000000",
                         "status":"queued","created_at":"2026-09-11T07:00:00Z"}
                        """, MediaType.APPLICATION_JSON));

        assertEquals("run-001", harness.client.submitGenerate(request()).engineRunId());
        harness.server.verify();
    }

    @Test
    void optimizeSendsWordAsMvcMultipartWithoutReactiveStreams() throws IOException {
        Path testDirectory = Path.of("target", "test-tmp");
        Files.createDirectories(testDirectory);
        Path document = Files.createTempFile(testDirectory, "engine-client-", ".docx");
        try {
            Files.writeString(document, "DOCX-TRANSPORT-MARKER");
            Harness harness = harness();
            harness.server.expect(once(), requestTo("http://engine.test/internal/v1/runs/optimize"))
                    .andExpect(method(HttpMethod.POST))
                    .andExpect(header("X-Engine-Token", "engine-test-token"))
                    .andExpect(content().contentTypeCompatibleWith(MediaType.MULTIPART_FORM_DATA))
                    .andExpect(content().string(containsString("name=\"request\"")))
                    .andExpect(content().string(containsString("\"mode\":\"optimize\"")))
                    .andExpect(content().string(containsString("name=\"document\"")))
                    .andExpect(content().string(containsString("DOCX-TRANSPORT-MARKER")))
                    .andRespond(withSuccess("""
                            {"engine_run_id":"run-optimize","external_job_id":"01J00000000000000000000000",
                             "status":"queued","created_at":"2026-09-11T07:00:00Z"}
                            """, MediaType.APPLICATION_JSON));

            assertEquals("run-optimize", harness.client.submitOptimize(request("optimize"), document).engineRunId());
            harness.server.verify();
        } finally {
            Files.deleteIfExists(document);
        }
    }

    @ParameterizedTest
    @CsvSource({"402,MODEL_BALANCE_EXHAUSTED,1", "429,MODEL_RATE_LIMITED,1",
            "503,ENGINE_UNAVAILABLE,3"})
    void retriesOnlyTransientStatusesAndKeepsStablePublicCodes(
            int status, String expectedCode, int expectedCalls) {
        Harness harness = harness();
        ExpectedCount count = expectedCalls == 1 ? once() : times(expectedCalls);
        harness.server.expect(count, requestTo("http://engine.test/internal/v1/runs/generate"))
                .andRespond(withStatus(HttpStatus.valueOf(status))
                        .contentType(MediaType.APPLICATION_PROBLEM_JSON));

        RestClientException failure = assertThrows(RestClientException.class,
                () -> harness.client.submitGenerate(request()));
        AppException translated = EngineClient.translate(failure);

        assertEquals(expectedCode, translated.code());
        harness.server.verify();
    }

    @Test
    void download404BecomesTerminalAppExceptionInsteadOfTransientSyncFailure() {
        Harness harness = harness();
        harness.server.expect(once(), requestTo(
                        "http://engine.test/internal/v1/runs/run-001/artifacts/recovery-plan-json"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND)
                        .contentType(MediaType.APPLICATION_PROBLEM_JSON));

        AppException error = assertThrows(AppException.class,
                () -> harness.client.download("run-001", "recovery-plan-json"));

        assertEquals("ENGINE_ARTIFACT_NOT_FOUND", error.code());
        harness.server.verify();
    }

    @Test
    void download504KeepsRetryingThenSurfacesTransientFailure() {
        Harness harness = harness();
        harness.server.expect(times(3), requestTo(
                        "http://engine.test/internal/v1/runs/run-001/artifacts/best-plan-docx"))
                .andRespond(withStatus(HttpStatus.BAD_GATEWAY)
                        .contentType(MediaType.APPLICATION_PROBLEM_JSON));

        AppException error = assertThrows(AppException.class,
                () -> harness.client.download("run-001", "best-plan-docx"));

        assertEquals("ENGINE_UNAVAILABLE", error.code());
        harness.server.verify();
    }

    private static Harness harness() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("http://engine.test")
                .defaultHeader("X-Engine-Token", "engine-test-token");
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        return new Harness(new EngineClient(builder.build(), new ObjectMapper()), server);
    }

    private static CreateRequest request() {
        return request("generate");
    }

    private static CreateRequest request(String mode) {
        LessonInput task = new LessonInput(mode, "化学", "高一", "酸碱中和",
                45, "", "", "", List.of(), List.of(), "", null, List.of(), "",
                "choose_the_best_fit_for_this_topic", "showcase", List.of(), List.of());
        return new CreateRequest("1", "01J00000000000000000000000", "a".repeat(64), task);
    }

    private record Harness(EngineClient client, MockRestServiceServer server) {
    }
}
