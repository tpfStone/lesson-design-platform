package com.zone.lesoongen.application;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import com.zone.lesoongen.domain.job.JobMode;
import com.zone.lesoongen.domain.job.JobStatus;
import com.zone.lesoongen.domain.job.LessonJob;
import com.zone.lesoongen.domain.shared.Ulids;
import com.zone.lesoongen.infrastructure.persistence.LessonArtifactRepository;
import com.zone.lesoongen.infrastructure.persistence.LessonJobEventRepository;
import com.zone.lesoongen.infrastructure.persistence.LessonJobRepository;
import com.zone.lesoongen.infrastructure.persistence.LessonSourceFileRepository;

@SpringBootTest
@ActiveProfiles("test")
class JobClaimConcurrencyTest {
    @Autowired JobStateService states;
    @Autowired LessonJobRepository jobs;
    @Autowired LessonJobEventRepository events;
    @Autowired LessonArtifactRepository artifacts;
    @Autowired LessonSourceFileRepository sources;
    @Autowired Clock clock;

    @BeforeEach
    void resetDatabase() {
        events.deleteAll();
        artifacts.deleteAll();
        sources.deleteAll();
        jobs.deleteAll();
        jobs.saveAll(List.of(job("化学"), job("数学")));
    }

    @Test
    void twoDispatchersCannotClaimBeyondConfiguredConcurrency() throws Exception {
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Boolean> first = pool.submit(() -> claimTogether(ready, start));
            Future<Boolean> second = pool.submit(() -> claimTogether(ready, start));
            ready.await(5, TimeUnit.SECONDS);
            start.countDown();

            int claimed = (first.get(10, TimeUnit.SECONDS) ? 1 : 0)
                    + (second.get(10, TimeUnit.SECONDS) ? 1 : 0);
            assertEquals(1, claimed);
            assertEquals(1, jobs.countByStatusIn(List.of(JobStatus.DISPATCHING)));
            assertEquals(1, jobs.countByStatusIn(List.of(JobStatus.QUEUED)));
        } finally {
            pool.shutdownNow();
        }
    }

    private boolean claimTogether(CountDownLatch ready, CountDownLatch start) throws Exception {
        ready.countDown();
        start.await(5, TimeUnit.SECONDS);
        return states.claimNext().isPresent();
    }

    private LessonJob job(String subject) {
        return new LessonJob(Ulids.next(clock), JobMode.GENERATE, subject, "高一",
                subject + "测试课", 45, "{}", "a".repeat(64),
                "claim-" + subject + "-" + Ulids.next(clock), null, clock);
    }
}
