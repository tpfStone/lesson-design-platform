package com.zone.lesoongen.api;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.lang.reflect.RecordComponent;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.Set;

import com.fasterxml.jackson.annotation.JsonProperty;

import org.junit.jupiter.api.Test;

import com.zone.lesoongen.api.dto.LessonRequests;
import com.zone.lesoongen.infrastructure.engine.EngineContracts;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class ContractFixtureTest {
    private final ObjectMapper mapper = new ObjectMapper();
    private final Path fixtures = Path.of("specs", "001-lesson-plan-web", "contracts", "fixtures");

    @Test
    void publicCamelCaseFixturesStayReadable() throws Exception {
        LessonRequests.Generate request = mapper.readValue(
                Files.readString(fixtures.resolve("public-generate-request.json")),
                LessonRequests.Generate.class);
        JsonNode accepted = mapper.readTree(
                Files.readString(fixtures.resolve("public-job-accepted.json")));

        assertEquals("官能团与有机物性质", request.topic());
        assertEquals(45, request.durationMinutes());
        assertEquals("QUEUED", accepted.get("status").asText());
        assertTrue(accepted.get("links").get("events").asText().endsWith("/events"));
    }

    @Test
    void internalSnakeCaseFixturesStayReadableByJavaAdapter() throws Exception {
        EngineContracts.CreateRequest request = mapper.readValue(
                Files.readString(fixtures.resolve("engine-generate-request.json")),
                EngineContracts.CreateRequest.class);
        EngineContracts.Accepted accepted = mapper.readValue(
                Files.readString(fixtures.resolve("engine-run-accepted.json")),
                EngineContracts.Accepted.class);

        assertEquals("01J00000000000000000000000", request.externalJobId());
        assertEquals(45, request.task().durationMinutes());
        assertEquals("20260911-070000-化学-高二-官能团-000001", accepted.engineRunId());
    }

    @Test
    void pythonRequiredEngineFieldsAndStatusesStayReadableByJava() throws Exception {
        Path contract = Path.of("..", "specs", "002-project-improvement", "contracts", "engine-models.json");
        JsonNode models = mapper.readTree(Files.readString(contract)).path("models");
        assertWireFields(models.path("CreateRunRequest"), EngineContracts.CreateRequest.class);
        assertWireFields(models.path("CreateRunRequest").path("$defs").path("EngineLessonInput"),
                EngineContracts.LessonInput.class);
        assertWireFields(models.path("RunAccepted"), EngineContracts.Accepted.class);
        assertWireFields(models.path("RunSnapshot"), EngineContracts.Snapshot.class);
        assertWireFields(models.path("RunSnapshot").path("$defs").path("EngineUsage"),
                EngineContracts.Usage.class);
        assertWireFields(models.path("EngineEventPage"), EngineContracts.EventPage.class);
        assertWireFields(models.path("EngineArtifact"), EngineContracts.Artifact.class);
        assertWireFields(models.path("EngineResult"), EngineContracts.Result.class);
        JsonNode statusValues = models.path("RunSnapshot").path("$defs")
                .path("EngineRunStatus").path("enum");
        Set<String> pythonStatuses = new HashSet<>();
        statusValues.forEach(value -> pythonStatuses.add(value.asText()));
        assertEquals(Set.of("queued", "preprocessing", "running", "exporting",
                "completed", "needs_human", "failed"), pythonStatuses);
    }

    private static void assertWireFields(JsonNode schema, Class<?> recordType) {
        assertFalse(schema.isMissingNode(), "Missing Python schema for " + recordType.getSimpleName());
        Set<String> javaFields = new HashSet<>();
        for (RecordComponent component : recordType.getRecordComponents()) {
            JsonProperty property = component.getAnnotation(JsonProperty.class);
            if (property == null) property = component.getAccessor().getAnnotation(JsonProperty.class);
            javaFields.add(property == null || property.value().isBlank()
                    ? component.getName() : property.value());
        }
        for (JsonNode field : schema.path("required")) {
            assertTrue(javaFields.contains(field.asText()), () ->
                    recordType.getSimpleName() + " cannot read required Python field " + field.asText());
        }
    }
}
