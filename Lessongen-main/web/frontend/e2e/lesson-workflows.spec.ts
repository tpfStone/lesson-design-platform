import { expect, test, type Page } from "@playwright/test";

const JOB_ID = "01J00000000000000000000000";

function job(status = "COMPLETED") {
  return {
    jobId: JOB_ID,
    mode: "GENERATE",
    status,
    subject: "化学",
    grade: "高二",
    topic: "官能团",
    durationMinutes: 45,
    currentStage: status === "COMPLETED" ? "finalize" : "critics",
    currentRound: 2,
    progressPercent: status === "RUNNING" ? 52 : 100,
    pipelineStatus: status.toLowerCase(),
    stopReason: status === "NEEDS_HUMAN" ? "rewrite_failed" : "quality_passed",
    bestVersionId: "v1",
    lastVersionId: "v1",
    errorCode: null,
    errorMessage: status === "FAILED" ? "模型服务暂时不可用，请稍后重试" : null,
    usage: {
      modelCallCount: 12,
      inputTokens: 42000,
      outputTokens: 8000,
      estimatedCost: 0.08,
    },
    createdAt: "2026-09-11T07:00:00Z",
    startedAt: "2026-09-11T07:00:01Z",
    finishedAt: status === "RUNNING" ? null : "2026-09-11T07:05:00Z",
    updatedAt: "2026-09-11T07:05:00Z",
    links: { self: "", events: "", result: "", artifacts: "" },
  };
}

const result = {
  jobId: JOB_ID,
  status: "COMPLETED",
  stopReason: "quality_passed",
  bestVersionId: "v1",
  lastVersionId: "v1",
  bestLessonPlan: {
    metadata: {
      subject: "化学",
      grade: "高二",
      topic: "官能团",
      duration_minutes: 45,
    },
    design_thesis: "以结构证据解释性质差异。",
    driving_question: "结构如何决定性质？",
    learning_objectives: [
      {
        objective_id: "obj-1",
        description: "能依据结构识别官能团",
        evidence_of_achievement: "完成分类并说明依据",
      },
    ],
    procedure_steps: [
      {
        step_id: "step-1",
        stage: "证据分类",
        duration_minutes: 15,
        teacher_actions: ["提供分子结构卡片"],
        student_actions: ["分类并陈述证据"],
        assessment: "分类理由",
      },
    ],
  },
  scores: {
    curriculumAlignment: 8,
    knowledgeAccuracy: 9,
    teachingLogic: 8,
    classroomFeasibility: 8.2,
    differentiatedInstruction: 7.8,
    studentEngagement: 8.1,
    assessmentDesign: 8.3,
    languageAndFormat: 8.4,
  },
  overallScore: 8.3,
  scoreNotice: "内部质量信号，不代表正式教学效果评价",
  review: {
    policy: "at_least_one_independent_review",
    reviewed_roles: [
      "subject_critic_v0_1",
      "pedagogy_critic_v0_1",
      "alignment_critic_v0_1",
    ],
    validator_completed: true,
    independent_review_complete: true,
    content_changed: true,
  },
  changes: [
    {
      summary: "补充了结构—性质证据链",
      targetPath: "/procedure_steps/0",
      sourceCritiqueIds: ["ped-001"],
    },
  ],
  unresolvedIssues: [],
  parseWarnings: [],
};

test.beforeEach(async ({ page }) => {
  // Keep long-running JobView tests inside the browser contract boundary. The
  // stream closes after one real SSE frame and advertises a long reconnect delay.
  await page.route("**/api/v1/lesson-jobs/*/events", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `retry: 60000\nevent: job.progress\ndata: ${JSON.stringify({
        sequence: 1,
        eventType: "job.progress",
        stage: "critics",
        roundIndex: 2,
        versionId: "v1",
        progressPercent: 52,
        message: "三类 Critic 正在独立审阅",
        occurredAt: "2026-09-11T07:02:00Z",
      })}\n\n`,
    }),
  );
});

async function mockTerminal(page: Page, status = "COMPLETED") {
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: job(status) }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) =>
    route.fulfill({ json: { ...result, status } }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/artifacts`, (route) =>
    route.fulfill({
      json: [
        {
          artifactId: "01J00000000000000000000001",
          type: status === "FAILED" ? "RECOVERY_MARKDOWN" : "BEST_DOCX",
          displayName:
            status === "FAILED" ? "recovery.md" : "best_lesson_plan.docx",
          mediaType: "application/octet-stream",
          sizeBytes: 1024,
          sha256: "a".repeat(64),
          downloadUrl: `/download/${status.toLowerCase()}`,
        },
      ],
    }),
  );
}

test("dashboard presents both MVP entry points on a real browser", async ({
  page,
}) => {
  await page.route("**/api/v1/lesson-jobs**", (route) =>
    route.fulfill({
      json: { items: [], page: 0, size: 12, totalElements: 0, totalPages: 0 },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /把课程设想变成/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "从零生成" }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "上传 Word 优化" }).first(),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "还没有任务" })).toBeVisible();
});

test("dashboard shows a loading skeleton without inventing task progress", async ({
  page,
}) => {
  await page.route("**/api/v1/lesson-jobs**", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 450));
    await route.fulfill({
      json: {
        items: [job()],
        page: 0,
        size: 12,
        totalElements: 1,
        totalPages: 1,
      },
    });
  });
  await page.goto("/");
  await expect(page.getByLabel("任务加载中")).toBeVisible();
  await expect(page.getByRole("link", { name: /官能团/ })).toBeVisible();
  await expect(page.locator(".job-card").getByRole("progressbar")).toHaveCount(
    0,
  );
});

test("dashboard distinguishes a failed load from an empty history and recovers", async ({
  page,
}) => {
  let requests = 0;
  await page.route("**/api/v1/lesson-jobs**", (route) => {
    requests += 1;
    const selectedMode = new URL(route.request().url()).searchParams.get(
      "mode",
    );
    return requests === 1
      ? route.fulfill({ status: 503, json: { message: "暂不可用" } })
      : route.fulfill({
          json: {
            items: selectedMode === "OPTIMIZE" ? [] : [job()],
            page: 0,
            size: 12,
            totalElements: selectedMode === "OPTIMIZE" ? 0 : 1,
            totalPages: selectedMode === "OPTIMIZE" ? 0 : 1,
          },
        });
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "暂时无法读取近期任务" }),
  ).toBeVisible();
  await expect(page.getByText("还没有任务", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "重试读取" }).click();
  await expect(page.getByRole("link", { name: /官能团/ })).toBeVisible();
  await expect(page.getByText("查看教案", { exact: true })).toBeVisible();
  await page
    .getByRole("combobox", { name: "按模式筛选" })
    .selectOption("OPTIMIZE");
  await expect(
    page.getByRole("heading", { name: "没有符合当前筛选条件的任务" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "清除筛选" }).click();
  await expect(page.getByRole("link", { name: /官能团/ })).toBeVisible();
});

test("history reaches a thirteenth task and filters on the server", async ({
  page,
}) => {
  const entries = Array.from({ length: 13 }, (_, index) => ({
    ...job(),
    jobId: `history-${index + 1}`,
    topic: `教案任务 ${index + 1}`,
    mode: index === 12 ? "OPTIMIZE" : "GENERATE",
  }));
  await page.route("**/api/v1/lesson-jobs**", (route) => {
    const params = new URL(route.request().url()).searchParams;
    const filtered =
      params.get("mode") === "OPTIMIZE" ? entries.slice(12) : entries;
    const pageNumber = Number(params.get("page") || "0");
    return route.fulfill({
      json: {
        items: filtered.slice(pageNumber * 12, (pageNumber + 1) * 12),
        page: pageNumber,
        size: 12,
        totalElements: filtered.length,
        totalPages: Math.ceil(filtered.length / 12),
      },
    });
  });
  await page.goto("/");
  await expect(page.getByText("共 13 条任务")).toBeVisible();
  await expect(page.getByRole("link", { name: /教案任务 13/ })).toHaveCount(0);
  await page.getByRole("button", { name: /加载更多/ }).click();
  await expect(page.getByRole("link", { name: /教案任务 13/ })).toBeVisible();
  await page
    .getByRole("combobox", { name: "按模式筛选" })
    .selectOption("OPTIMIZE");
  await expect(page.getByText("共 1 条任务")).toBeVisible();
  await expect(page.getByRole("link", { name: /教案任务 13/ })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "没有符合当前筛选条件的任务" }),
  ).toHaveCount(0);
});

test("navigation remains usable across narrow and wide viewports", async ({
  page,
}, testInfo) => {
  await page.route("**/api/v1/lesson-jobs**", (route) =>
    route.fulfill({
      json: { items: [], page: 0, size: 12, totalElements: 0, totalPages: 0 },
    }),
  );
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/");
  for (const width of [320, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 720 });
    for (const label of ["生成教案", "优化教案", "历史任务"]) {
      const link = page
        .getByRole("navigation", { name: "主导航" })
        .getByRole("link", { name: label });
      await expect(link).toBeVisible();
      const box = await link.boundingBox();
      expect(box?.height).toBeGreaterThanOrEqual(44);
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    if ([320, 390, 1280].includes(width)) {
      await testInfo.attach(`dashboard-${width}`, {
        body: await page.screenshot(),
        contentType: "image/png",
      });
    }
  }
});

test("forms and result stay within the viewport from 320 to 1440 pixels", async ({
  page,
}) => {
  await mockTerminal(page);
  for (const path of [
    "/create/generate",
    "/create/optimize",
    `/jobs/${JOB_ID}`,
  ]) {
    await page.goto(path);
    for (const width of [320, 390, 768, 1280, 1440]) {
      await page.setViewportSize({ width, height: 844 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth - window.innerWidth,
        ),
      ).toBeLessThanOrEqual(1);
    }
  }
});

test("route changes update the page title and focus the new heading", async ({
  page,
}) => {
  await page.route("**/api/v1/lesson-jobs**", (route) =>
    route.fulfill({
      json: { items: [], page: 0, size: 12, totalElements: 0, totalPages: 0 },
    }),
  );
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("link", { name: "生成教案" })
    .click();
  await expect(
    page.getByRole("heading", { name: "从课程设想开始" }),
  ).toBeFocused();
  await expect(page).toHaveTitle("生成教案 · 灵犀教案");
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("link", { name: "优化教案" })
    .click();
  await expect(
    page.getByRole("heading", { name: "让原教案变得更可教" }),
  ).toBeFocused();
  await expect(page).toHaveTitle("优化教案 · 灵犀教案");
});

test("three required fields create a generate job and open real progress", async ({
  page,
}) => {
  await page.route("**/api/v1/lesson-jobs/generate", async (route) => {
    const payload = route.request().postDataJSON();
    expect(payload).toMatchObject({
      subject: "化学",
      grade: "高二",
      topic: "官能团",
    });
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    await route.fulfill({
      status: 202,
      json: {
        jobId: JOB_ID,
        status: "QUEUED",
        createdAt: "2026-09-11T07:00:00Z",
        links: {},
      },
    });
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: job("RUNNING") }),
  );
  await page.goto("/create/generate");
  await page.getByPlaceholder("如：高中化学").fill("化学");
  await page.getByPlaceholder("如：高二").fill("高二");
  await page.getByPlaceholder("如：官能团与有机物性质的关系").fill("官能团");
  await page.getByRole("button", { name: "开始生成教案" }).click();
  await expect(page).toHaveURL(new RegExp(`/jobs/${JOB_ID}$`));
  await expect(page.getByText("三类 Critic 正在独立审阅")).toBeVisible();
});

test("generate form locates missing fields and keeps optional sections discoverable", async ({
  page,
}) => {
  await page.goto("/create/generate");
  await page.getByRole("button", { name: "开始生成教案" }).click();
  await expect(page.locator("#generate-subject")).toBeFocused();
  await expect(page.getByText("请输入科目。")).toBeVisible();
  await page.locator("#generate-subject").fill("化学");
  await page.getByRole("button", { name: "开始生成教案" }).click();
  await expect(page.locator("#generate-grade")).toBeFocused();
  await page.locator("#generate-grade").fill("高二");
  await page.locator("#generate-topic").fill("官能团");
  await expect(
    page
      .getByRole("navigation", { name: "表单填写路线" })
      .getByText("必填已齐"),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "表单填写路线" })
    .getByRole("link", { name: /风格要求/ })
    .click();
  await expect(page.locator("#generate-advanced")).toHaveAttribute("open", "");
  await expect(page.getByText("草稿已保存在当前浏览器会话")).toBeVisible();
});

test("mobile form does not pin the submit bar over a focused input", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 700 });
  await page.goto("/create/generate");
  await page.locator("#generate-subject").focus();
  expect(
    await page
      .locator(".submit-row")
      .evaluate((element) => getComputedStyle(element).position),
  ).toBe("static");
});

test("mobile generation presents evidence guidance before submission and reveals later sections", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/create/generate");
  await expect(page.locator(".mobile-evidence")).toBeVisible();
  await expect(page.locator(".desktop-evidence")).toBeHidden();
  const positions = await page.evaluate(() => ({
    evidence: document
      .querySelector(".mobile-evidence")
      ?.getBoundingClientRect().top,
    form: document.querySelector(".lesson-form")?.getBoundingClientRect().top,
  }));
  expect(positions.evidence).toBeLessThan(positions.form);
  await expect(page.getByText("第 1 / 4 部分")).toBeVisible();
  await page.getByRole("link", { name: /下一部分/ }).click();
  await expect(page.getByText("第 2 / 4 部分")).toBeVisible();
});

test("completed and needs-human outcomes remain semantically distinct", async ({
  page,
}) => {
  await mockTerminal(page, "COMPLETED");
  await page.goto(`/jobs/${JOB_ID}`);
  await expect(
    page.getByRole("heading", { name: "已完成独立审查并形成修改稿" }),
  ).toBeVisible();
  await expect(page.locator(".connection-indicator")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "下载 Word" })).toHaveAttribute(
    "href",
    "/download/completed",
  );
  await expect(page.getByText("这些分数用于管线内部选优和路由")).toBeVisible();

  await page.unrouteAll({ behavior: "wait" });
  await mockTerminal(page, "NEEDS_HUMAN");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "已形成版本，建议教师复核" }),
  ).toBeVisible();
  await expect(page.getByText("改写环节未能可靠完成")).toBeVisible();
});

test("generated high-score v0 is labelled by actual review evidence", async ({
  page,
}, testInfo) => {
  await mockTerminal(page);
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) =>
    route.fulfill({
      json: {
        ...result,
        review: {
          ...result.review,
          policy: "judge_first_fast_path",
          reviewed_roles: [],
          validator_completed: false,
          independent_review_complete: false,
          content_changed: false,
        },
        changes: [],
      },
    }),
  );
  await page.goto(`/jobs/${JOB_ID}`);
  await expect(
    page.getByRole("heading", { name: "教案已生成，独立审查尚未完成" }),
  ).toBeVisible();
  await expect(page.getByText("不能称为完成三方独立审查")).toBeVisible();
  await testInfo.attach("generate-fast-path-not-reviewed", {
    body: await page.screenshot(),
    contentType: "image/png",
  });

  await page.unrouteAll({ behavior: "wait" });
  await mockTerminal(page);
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) =>
    route.fulfill({
      json: {
        ...result,
        review: { ...result.review, content_changed: false },
        changes: [],
      },
    }),
  );
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "已完成独立审查，教案未改写" }),
  ).toBeVisible();
  await testInfo.attach("generate-independent-review-unchanged", {
    body: await page.screenshot(),
    contentType: "image/png",
  });
});

test("creation shows paid-account errors and allows a retry", async ({
  page,
}) => {
  let calls = 0;
  await page.route("**/api/v1/lesson-jobs/generate", (route) => {
    calls += 1;
    return calls === 1
      ? route.fulfill({
          status: 402,
          contentType: "application/problem+json",
          json: { code: "PROVIDER_PAYMENT_REQUIRED", detail: "模型余额不足" },
        })
      : route.fulfill({
          status: 202,
          json: {
            jobId: JOB_ID,
            status: "QUEUED",
            createdAt: "2026-09-11T07:00:00Z",
            links: {},
          },
        });
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: job("RUNNING") }),
  );
  await page.goto("/create/generate");
  await page.getByPlaceholder("如：高中化学").fill("化学");
  await page.getByPlaceholder("如：高二").fill("高二");
  await page.getByPlaceholder("如：官能团与有机物性质的关系").fill("官能团");
  await page.getByRole("button", { name: "开始生成教案" }).click();
  await expect(page.getByRole("alert")).toContainText("模型余额不足");
  await page.getByRole("button", { name: "开始生成教案" }).click();
  await expect(page).toHaveURL(new RegExp(`/jobs/${JOB_ID}$`));
});

test("failed run never renders a fabricated lesson and exposes recovery", async ({
  page,
}) => {
  await mockTerminal(page, "FAILED");
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/problem+json",
      json: { code: "RESULT_NOT_READY", detail: "任务尚未形成可展示版本" },
    }),
  );
  await page.goto(`/jobs/${JOB_ID}`);
  await expect(
    page.getByRole("heading", { name: "本次任务未完整完成" }),
  ).toBeVisible();
  await expect(page.getByText("没有可展示的完整版本")).toBeVisible();
  await expect(
    page.getByText("系统不会用空白教案冒充结果", { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "重新创建任务" })).toBeVisible();
  await expect(
    page
      .locator(".failed-panel")
      .getByRole("link", { name: /恢复记录 Markdown/ }),
  ).toHaveAttribute("href", "/download/failed");
  await expect(page.locator("body")).not.toContainText("recovery.md");
});

test("optimize validates a DOCX and submits metadata with the original file", async ({
  page,
}) => {
  await page.route("**/api/v1/lesson-jobs/optimize", async (route) => {
    expect(route.request().headers()["content-type"]).toContain(
      "multipart/form-data",
    );
    expect(
      route.request().postDataBuffer()?.includes(Buffer.from("lesson.docx")),
    ).toBeTruthy();
    await route.fulfill({
      status: 202,
      json: {
        jobId: JOB_ID,
        status: "QUEUED",
        createdAt: "2026-09-11T07:00:00Z",
        links: {},
      },
    });
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: job("RUNNING") }),
  );
  await page.goto("/create/optimize");
  await page.locator("input[type=file]").setInputFiles({
    name: "lesson.docx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from([0x50, 0x4b, 0x03, 0x04, 0x01]),
  });
  await page.getByPlaceholder("如：高中化学").fill("化学");
  await page.getByPlaceholder("如：高二").fill("高二");
  await page.getByPlaceholder("如：官能团与有机物性质的关系").fill("官能团");
  await page.getByRole("button", { name: "开始优化教案" }).click();
  await expect(page).toHaveURL(new RegExp(`/jobs/${JOB_ID}$`));
});

test("optimize distinguishes local file checks from server-side Word parsing", async ({
  page,
}) => {
  await page.goto("/create/optimize");
  await page.getByRole("button", { name: "开始优化教案" }).click();
  await expect(page.locator("#optimize-file")).toBeFocused();
  await expect(page.getByText("请先选择可读取的 Word 教案。")).toBeVisible();
  await page.locator("#optimize-file").setInputFiles({
    name: "broken.docx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from("not a Word zip"),
  });
  await expect(
    page.getByText("文件不是有效的 OOXML Word 文档。"),
  ).toBeVisible();
  await expect(page.getByText("SHA-256 已计算")).toHaveCount(0);
  await expect(
    page.getByText("输出采用统一教案模板，不复刻原排版。", { exact: false }),
  ).toBeVisible();
});

test("optimization result distinguishes a real edit from an unchanged draft", async ({
  page,
}) => {
  let changed = true;
  const summary = () => ({
    outcome: changed ? "changed" : "reviewed_unchanged",
    message: changed ? "已形成修改稿。" : "已审查，交付稿未修改。",
    baseline_version_id: "v0",
    selected_version_id: changed ? "v1" : "v0",
    content_changed: changed,
    changed_section_count: changed ? 1 : 0,
    changed_sections: changed
      ? [
          {
            field: "procedure_steps",
            label: "教学过程",
            before: [],
            after: ["新活动"],
          },
        ]
      : [],
    baseline_score: 7.5,
    selected_score: 7.5,
    score_delta: 0,
    score_notice: "同稿分差不算优化。",
    critique_count: 2,
    reviewed_issues: [],
    validation_batch_count: 1,
    rewrite_count: changed ? 1 : 0,
    rounds: [],
    stop_reason: "no_actionable_feedback",
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: { ...job(), mode: "OPTIMIZE" } }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) =>
    route.fulfill({ json: { ...result, optimization: summary() } }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/artifacts`, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto(`/jobs/${JOB_ID}`);
  await expect(
    page.getByRole("heading", { name: "已形成修改稿，建议教师复核" }),
  ).toBeVisible();
  await expect(page.getByText("交付稿有内容变化·待复核")).toBeVisible();
  changed = false;
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "审查已结束，交付稿未修改" }),
  ).toBeVisible();
  await expect(page.getByText("交付稿没有内容变化")).toBeVisible();
});

test("optimization puts real changes before the lesson and scores on narrow screens", async ({
  page,
}) => {
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: { ...job(), mode: "OPTIMIZE" } }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) =>
    route.fulfill({
      json: {
        ...result,
        optimization: {
          outcome: "changed",
          message: "已形成修改稿。",
          baseline_version_id: "v0",
          selected_version_id: "v1",
          content_changed: true,
          changed_section_count: 1,
          changed_sections: [
            {
              field: "procedure_steps",
              label: "教学过程",
              before: ["教师讲解"],
              after: ["学生举证并讨论"],
            },
          ],
          baseline_score: 7.5,
          selected_score: 8.3,
          score_delta: 0.8,
          score_notice: "内部分数不是正式教学成效。",
          critique_count: 2,
          reviewed_issues: [],
          validation_batch_count: 1,
          rewrite_count: 1,
          rounds: [],
          stop_reason: "quality_passed",
        },
      },
    }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/artifacts`, (route) =>
    route.fulfill({
      json: [
        {
          artifactId: "01J00000000000000000000001",
          type: "BEST_DOCX",
          displayName: "best_lesson_plan.docx",
          mediaType: "application/octet-stream",
          sizeBytes: 1024,
          sha256: "a".repeat(64),
          downloadUrl: "/download/revised",
        },
      ],
    }),
  );
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/jobs/${JOB_ID}`);
    await expect(
      page.getByRole("link", { name: "下载修改稿 Word（待复核）" }),
    ).toBeVisible();
    await expect(page.locator(".primary-diff details").first()).toHaveAttribute(
      "open",
      "",
    );
    await expect(page.locator(".primary-diff")).toContainText("教师讲解");
    await expect(page.locator(".primary-diff")).toContainText("学生举证并讨论");
    const positions = await page.evaluate(() => {
      const top = (selector: string) =>
        document.querySelector(selector)?.getBoundingClientRect().top ?? 0;
      return {
        result: top(".result-banner"),
        difference: top(".optimization-panel"),
        lesson: top(".lesson-paper"),
        scores: top(".score-panel"),
        overflow: document.documentElement.scrollWidth - window.innerWidth,
      };
    });
    expect(positions.result).toBeLessThan(positions.difference);
    expect(positions.difference).toBeLessThan(positions.lesson);
    expect(positions.lesson).toBeLessThan(positions.scores);
    expect(positions.overflow).toBeLessThanOrEqual(1);
  }
});

test("Word optimization progress shows only its actual route and unknown metrics honestly", async ({
  page,
}) => {
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({
      json: {
        ...job("RUNNING"),
        mode: "OPTIMIZE",
        currentStage: "docx_normalize",
        progressPercent: null,
        usage: null,
      },
    }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/events`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: "retry: 60000\n\n",
    }),
  );
  await page.goto(`/jobs/${JOB_ID}`);
  await expect(
    page.getByRole("heading", { name: "正在识别 Word 中的教学内容" }),
  ).toBeVisible();
  await expect(page.locator(".progress-heading h2")).toHaveAttribute(
    "aria-live",
    "polite",
  );
  await expect(page.getByText("识别原稿内容")).toBeVisible();
  await expect(page.getByText("设计路线")).toHaveCount(0);
  await expect(page.getByText("形成初稿")).toHaveCount(0);
  await expect(page.getByRole("progressbar")).toHaveCount(0);
  await expect(page.getByText("暂不可用").first()).toBeVisible();
});

test("quality chart renders readable labels and respects reduced motion", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockTerminal(page);
  await page.goto(`/jobs/${JOB_ID}`);
  await page.locator(".radar-slot").scrollIntoViewIfNeeded();
  await expect(page.locator(".radar-svg text")).toHaveCount(8);
  await expect(page.locator(".radar-svg text").first()).toHaveText("课标对齐");
  await expect(page.locator(".radar-svg")).not.toContainText("[object Object]");
  await expect(page.locator(".score-list")).toContainText("知识准确");
  const animation = await page
    .locator(".radar-value-shape")
    .evaluate((node) => getComputedStyle(node).animationName);
  expect(animation).toBe("none");
});

test("missing score and lesson duration stay unknown instead of becoming zero or a guessed class length", async ({
  page,
}) => {
  await mockTerminal(page);
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: { ...job(), durationMinutes: null } }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) =>
    route.fulfill({
      json: {
        ...result,
        overallScore: null,
        scores: { knowledgeAccuracy: 8.2 },
        bestLessonPlan: {
          ...result.bestLessonPlan,
          metadata: {
            ...result.bestLessonPlan.metadata,
            duration_minutes: null,
          },
        },
      },
    }),
  );
  await page.goto(`/jobs/${JOB_ID}`);
  await expect(page.locator(".job-title p")).toContainText("课时待确认");
  await expect(page.locator(".score-panel .overall-score")).toContainText(
    "暂不可用",
  );
  await expect(page.locator(".score-list")).toContainText("知识准确");
  await expect(page.locator(".radar-svg")).toHaveCount(0);
  await expect(page.locator(".chart-fallback")).toContainText("暂不绘制雷达图");
});

test("completed result jumps to the lesson without reloading the route", async ({
  page,
}) => {
  await mockTerminal(page);
  await page.goto(`/jobs/${JOB_ID}`);
  await page.getByRole("link", { name: "直接阅读教案" }).click();
  await expect(page).toHaveURL(new RegExp(`#lesson-content$`));
  await expect(page.locator("#lesson-content")).toBeVisible();
  await expect(page.getByRole("heading", { name: "设计主张" })).toBeVisible();
});

test("mobile live status sits below the full lesson title", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({
      json: { ...job("RUNNING"), topic: "官能团与有机物性质" },
    }),
  );
  await page.goto(`/jobs/${JOB_ID}`);
  const title = page.locator(".job-title");
  const indicator = page.locator(".connection-indicator");
  await expect(title).toBeVisible();
  await expect(indicator).toBeVisible();
  const titleBounds = await title.boundingBox();
  const indicatorBounds = await indicator.boundingBox();
  expect(titleBounds).not.toBeNull();
  expect(indicatorBounds).not.toBeNull();
  expect(indicatorBounds!.y).toBeGreaterThanOrEqual(
    titleBounds!.y + titleBounds!.height,
  );
  expect(titleBounds!.width).toBeGreaterThan(250);
});

test("SSE failure visibly falls back to two-second detail polling", async ({
  page,
}) => {
  let detailCalls = 0;
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) => {
    detailCalls += 1;
    return route.fulfill({ json: job("RUNNING") });
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/events`, (route) =>
    route.abort("failed"),
  );

  await page.goto(`/jobs/${JOB_ID}`);
  await expect(page.getByText("轮询同步")).toBeVisible();
  await expect
    .poll(() => detailCalls, { timeout: 4_500 })
    .toBeGreaterThanOrEqual(2);
});

test("a delayed running detail cannot roll back a terminal SSE refresh", async ({
  page,
}) => {
  let detailCalls = 0;
  let staleResponseReturned = false;
  let releaseStale: (() => void) | undefined;
  const staleGate = new Promise<void>((resolve) => {
    releaseStale = resolve;
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, async (route) => {
    detailCalls += 1;
    if (detailCalls === 1) return route.fulfill({ json: job("RUNNING") });
    if (detailCalls === 2) {
      await staleGate;
      await route.fulfill({ json: job("RUNNING") });
      staleResponseReturned = true;
      return;
    }
    return route.fulfill({ json: job("COMPLETED") });
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/events`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        "retry: 60000",
        ...[2, 3].flatMap((sequence) => [
          "event: job.progress",
          `data: ${JSON.stringify({
            sequence,
            eventType: "job.progress",
            stage: "critics",
            roundIndex: 2,
            versionId: "v1",
            progressPercent: 52,
            message: "三类 Critic 正在独立审阅",
            occurredAt: "2026-09-11T07:02:00Z",
          })}`,
          "",
        ]),
        "",
      ].join("\n"),
    }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) =>
    route.fulfill({ json: result }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/artifacts`, (route) =>
    route.fulfill({ json: [] }),
  );

  await page.goto(`/jobs/${JOB_ID}`);
  try {
    await expect.poll(() => detailCalls).toBeGreaterThanOrEqual(3);
    await expect(
      page.getByRole("heading", { name: "已完成独立审查并形成修改稿" }),
    ).toBeVisible();
  } finally {
    releaseStale?.();
  }
  await expect.poll(() => staleResponseReturned).toBe(true);
  // Let the browser consume the older response, then check both state and result.
  await page.waitForTimeout(250);
  await expect(page.locator(".result-banner.completed")).toBeVisible();
  await expect(page.locator(".progress-layout")).toHaveCount(0);
  await expect(page.getByText("结构如何决定性质？")).toBeVisible();
});

test("a result retry preserves the already loaded download list", async ({
  page,
}) => {
  let resultCalls = 0;
  let artifactCalls = 0;
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: job() }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/artifacts`, (route) => {
    artifactCalls += 1;
    return route.fulfill({
      json: [
        {
          artifactId: "01J00000000000000000000001",
          type: "BEST_DOCX",
          displayName: "best_lesson_plan.docx",
          mediaType: "application/octet-stream",
          sizeBytes: 1024,
          sha256: "a".repeat(64),
          downloadUrl: "/download/recoverable",
        },
      ],
    });
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) => {
    resultCalls += 1;
    return resultCalls === 1
      ? route.fulfill({ status: 503, json: { detail: "结果暂不可用" } })
      : route.fulfill({ json: result });
  });

  await page.goto(`/jobs/${JOB_ID}`);
  await expect(page.getByRole("alert")).toContainText("教案结果暂时无法读取");
  await expect(page.getByRole("link", { name: "下载 Word" })).toHaveAttribute(
    "href",
    "/download/recoverable",
  );
  await page.getByRole("button", { name: "重试读取教案结果" }).click();
  await expect(page.getByText("结构如何决定性质？")).toBeVisible();
  expect(resultCalls).toBe(2);
  expect(artifactCalls).toBe(1);
  await expect(page.getByRole("link", { name: "下载 Word" })).toBeVisible();
});

test("an artifact retry preserves the already loaded lesson result", async ({
  page,
}) => {
  let resultCalls = 0;
  let artifactCalls = 0;
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: job() }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) => {
    resultCalls += 1;
    return route.fulfill({ json: result });
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/artifacts`, (route) => {
    artifactCalls += 1;
    return artifactCalls === 1
      ? route.fulfill({ status: 503, json: { detail: "文件暂不可用" } })
      : route.fulfill({
          json: [
            {
              artifactId: "01J00000000000000000000001",
              type: "BEST_DOCX",
              displayName: "best_lesson_plan.docx",
              mediaType: "application/octet-stream",
              sizeBytes: 1024,
              sha256: "a".repeat(64),
              downloadUrl: "/download/after-retry",
            },
          ],
        });
  });

  await page.goto(`/jobs/${JOB_ID}`);
  await expect(page.getByText("结构如何决定性质？")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("下载文件暂时无法读取");
  await page.getByRole("button", { name: "重试读取下载文件" }).click();
  await expect(page.getByRole("link", { name: "下载 Word" })).toHaveAttribute(
    "href",
    "/download/after-retry",
  );
  expect(artifactCalls).toBe(2);
  expect(resultCalls).toBe(1);
  await expect(page.getByText("结构如何决定性质？")).toBeVisible();
});

test("terminal result sync retries after a temporary backend error", async ({
  page,
}) => {
  let resultCalls = 0;
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: job() }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/artifacts`, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) => {
    resultCalls += 1;
    return resultCalls === 1
      ? route.fulfill({ status: 503, json: { detail: "暂时不可用" } })
      : route.fulfill({ json: result });
  });
  await page.goto(`/jobs/${JOB_ID}`);
  await expect(page.getByRole("alert")).toContainText("教案结果暂时无法读取");
  await expect
    .poll(() => resultCalls, { timeout: 5_000 })
    .toBeGreaterThanOrEqual(2);
  await expect(
    page.getByRole("heading", { name: "已完成独立审查并形成修改稿" }),
  ).toBeVisible();
});

test("missing artifact listing does not hide an otherwise complete lesson", async ({
  page,
}) => {
  await mockTerminal(page);
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/artifacts`, (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/problem+json",
      json: { code: "ARTIFACT_NOT_FOUND", detail: "产物已不可用" },
    }),
  );
  await page.goto(`/jobs/${JOB_ID}`);
  await expect(
    page.getByRole("heading", { name: "已完成独立审查并形成修改稿" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("下载文件列表暂不可用");
  await expect(
    page.getByRole("button", { name: "重试读取下载文件" }),
  ).toBeVisible();
  await expect(page.getByText("结构如何决定性质？")).toBeVisible();
});

test("job detail 401 is visible and can be retried", async ({ page }) => {
  let detailCalls = 0;
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) => {
    detailCalls += 1;
    return detailCalls === 1
      ? route.fulfill({
          status: 401,
          contentType: "application/problem+json",
          json: { detail: "会话无效" },
        })
      : route.fulfill({ json: job("RUNNING") });
  });
  await page.goto(`/jobs/${JOB_ID}`);
  await expect(page.getByRole("alert")).toContainText("会话无效");
  await page.getByRole("button", { name: "重新加载" }).click();
  await expect(page.getByText("三类 Critic 正在独立审阅")).toBeVisible();
});

test("generate form remains keyboard-usable with reduced motion requested", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/create/generate");
  const subject = page.getByPlaceholder("如：高中化学");
  await subject.focus();
  await subject.fill("化学");
  await page.keyboard.press("Tab");
  await expect(page.getByPlaceholder("如：高二")).toBeFocused();
  await expect
    .poll(() =>
      page.evaluate(
        () => matchMedia("(prefers-reduced-motion: reduce)").matches,
      ),
    )
    .toBe(true);
  const transitionDuration = await page
    .locator(".page-shell")
    .evaluate((element) => getComputedStyle(element).transitionDuration);
  const durationsInMilliseconds = transitionDuration.split(",").map((value) => {
    const duration = value.trim();
    return duration.endsWith("ms")
      ? Number.parseFloat(duration)
      : Number.parseFloat(duration) * 1_000;
  });
  expect(Math.max(...durationsInMilliseconds)).toBeLessThanOrEqual(0.01);
});
