package com.zone.lesoongen.infrastructure.persistence;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.SQLException;

import javax.sql.DataSource;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.FlywayException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mysql.MySQLContainer;

@SpringBootTest(properties = {
        "app.scheduling-enabled=false",
        "app.engine-internal-token=test-only-token"
})
@Testcontainers(disabledWithoutDocker = true)
class MySqlMigrationTest {
    @Container
    @ServiceConnection
    static final MySQLContainer MYSQL = new MySQLContainer("mysql:8.0.44")
            .withDatabaseName("lesoongen")
            .withUsername("lesoongen")
            .withPassword("test-password");

    @Autowired
    DataSource dataSource;

    @Test
    void flywayCreatesTheProductionTablesAndConstraints() throws SQLException {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        Integer tableCount = jdbc.queryForObject("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name IN ('lesson_job', 'lesson_source_file', 'lesson_artifact', 'lesson_job_event')
                """, Integer.class);
        assertEquals(4, tableCount);

        Integer jsonColumns = jdbc.queryForObject("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE() AND data_type = 'json'
                  AND column_name IN ('request_snapshot', 'parse_warnings', 'event_payload')
                """, Integer.class);
        assertEquals(3, jsonColumns);

        Integer nullableF4Columns = jdbc.queryForObject("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'platform_simulation_run'
                  AND column_name IN ('f4_session_id', 'f4_lesson_plan_id')
                  AND is_nullable = 'YES'
                """, Integer.class);
        assertEquals(2, nullableF4Columns);

        assertThrows(Exception.class, () -> jdbc.update("""
                INSERT INTO lesson_source_file
                  (id, job_id, kind, original_filename, media_type, size_bytes, sha256,
                   storage_key, parse_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP(6))
                """, "01J00000000000000000000000", "01J99999999999999999999999",
                "ORIGINAL_LESSON_DOCX", "lesson.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                1, "0".repeat(64), "jobs/test/input.docx", "PENDING"));
    }

    @Test
    void invalidFollowUpMigrationFailsLoudly(@TempDir Path migrationDirectory) throws Exception {
        Files.writeString(
                migrationDirectory.resolve("V4__intentionally_invalid.sql"),
                "THIS IS NOT VALID MYSQL SQL;");

        Flyway invalidFlyway = Flyway.configure()
                .dataSource(dataSource)
                .locations(
                        "classpath:db/migration",
                        "classpath:db/vendor/mysql",
                        "filesystem:" + migrationDirectory.toAbsolutePath().toString().replace('\\', '/'))
                .load();

        assertThrows(FlywayException.class, invalidFlyway::migrate);
    }
}
