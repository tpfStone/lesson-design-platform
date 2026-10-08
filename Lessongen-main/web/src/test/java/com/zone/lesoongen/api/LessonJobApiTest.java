package com.zone.lesoongen.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.context.WebApplicationContext;

@SpringBootTest
@ActiveProfiles("test")
class LessonJobApiTest {
    @Autowired WebApplicationContext context;
    @Autowired CorrelationIdFilter correlationIdFilter;
    private MockMvc mvc;

    @BeforeEach
    void setup() {
        mvc = MockMvcBuilders.webAppContextSetup(context)
                .addFilters(correlationIdFilter).build();
    }

    @Test
    void acceptsGenerateAndReplaysSameIdempotentRequest() throws Exception {
        String key = "api-test-same-request-0001";
        String body = """
                {"subject":"化学","grade":"高二","topic":"官能团","durationMinutes":45,
                 "curriculumStandards":[],"learningObjectives":[],"availableResources":[]}
                """;
        String first = mvc.perform(post("/api/v1/lesson-jobs/generate")
                        .header("Idempotency-Key", key).contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isAccepted()).andExpect(jsonPath("$.status").value("QUEUED"))
                .andReturn().getResponse().getContentAsString();
        String second = mvc.perform(post("/api/v1/lesson-jobs/generate")
                        .header("Idempotency-Key", key).contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isAccepted()).andReturn().getResponse().getContentAsString();
        org.junit.jupiter.api.Assertions.assertEquals(first, second);
    }

    @Test
    void rejectsIdempotencyConflictAndReturnsProblemDetail() throws Exception {
        String key = "api-test-conflicting-0001";
        mvc.perform(post("/api/v1/lesson-jobs/generate").header("Idempotency-Key", key)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"subject\":\"数学\",\"grade\":\"高一\",\"topic\":\"函数\"}"))
                .andExpect(status().isAccepted());
        mvc.perform(post("/api/v1/lesson-jobs/generate").header("Idempotency-Key", key)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"subject\":\"数学\",\"grade\":\"高一\",\"topic\":\"集合\"}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("IDEMPOTENCY_KEY_CONFLICT"));
    }

    @Test
    void validatesFieldsAndSupportsPagedHistory() throws Exception {
        mvc.perform(post("/api/v1/lesson-jobs/generate")
                        .header("Idempotency-Key", "api-test-validation-0001")
                        .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
        mvc.perform(get("/api/v1/lesson-jobs").param("page", "0").param("size", "12"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.items").isArray());
    }

    @Test
    void optimizeRejectsFakeDocxBeforeItCanEnterTheQueue() throws Exception {
        MockMultipartFile request = new MockMultipartFile("request", "", "application/json",
                "{\"subject\":\"英语\",\"grade\":\"八年级\",\"topic\":\"邀请与回复\"}"
                        .getBytes(java.nio.charset.StandardCharsets.UTF_8));
        MockMultipartFile document = new MockMultipartFile("document", "lesson.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "not an OOXML package".getBytes(java.nio.charset.StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/v1/lesson-jobs/optimize")
                        .file(request).file(document)
                        .header("Idempotency-Key", "api-test-invalid-docx-0001"))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code").value("INVALID_DOCX"));
    }

    @Test
    void actuatorInfoExposesNonSecretBuildFingerprint() throws Exception {
        mvc.perform(get("/actuator/info"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.lessongen.build-commit").exists())
                .andExpect(jsonPath("$.lessongen.build-dirty").exists())
                .andExpect(jsonPath("$.lessongen.runtime").exists());
    }
}
