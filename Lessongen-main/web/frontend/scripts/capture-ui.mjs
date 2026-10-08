import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "vite";

const jobId = "01J00000000000000000000000";
const outputDirectory = process.env.LESSONGEN_UI_AUDIT_DIR
  ? resolve(process.env.LESSONGEN_UI_AUDIT_DIR)
  : fileURLToPath(new URL("../../docs/ui-audit", import.meta.url));

const job = {
  jobId,
  mode: "GENERATE",
  status: "COMPLETED",
  subject: "化学",
  grade: "高二",
  topic: "官能团与有机物性质",
  durationMinutes: 45,
  currentStage: "finalize",
  currentRound: 2,
  progressPercent: 100,
  pipelineStatus: "completed",
  stopReason: "quality_passed",
  bestVersionId: "v1",
  lastVersionId: "v1",
  errorCode: null,
  errorMessage: null,
  usage: {
    modelCallCount: 12,
    inputTokens: 42000,
    outputTokens: 8000,
    estimatedCost: 0.08,
  },
  createdAt: "2026-09-15T07:00:00Z",
  startedAt: "2026-09-15T07:00:01Z",
  finishedAt: "2026-09-15T07:05:00Z",
  updatedAt: "2026-09-15T07:05:00Z",
  links: { self: "", events: "", result: "", artifacts: "" },
};

const result = {
  jobId,
  status: "COMPLETED",
  stopReason: "quality_passed",
  bestVersionId: "v1",
  lastVersionId: "v1",
  bestLessonPlan: {
    metadata: {
      subject: "化学",
      grade: "高二",
      topic: "官能团与有机物性质",
      duration_minutes: 45,
    },
    design_thesis: "以结构证据解释性质差异，并用可观察产出检验理解。",
    driving_question: "分子结构中的官能团如何影响物质性质？",
    learning_objectives: [
      {
        objective_id: "obj-1",
        description: "能依据结构特征识别常见官能团",
        evidence_of_achievement: "完成结构分类并说明判断依据",
      },
      {
        objective_id: "obj-2",
        description: "能用官能团解释典型有机物的性质差异",
        evidence_of_achievement: "基于证据完成预测与反驳",
      },
    ],
    procedure_steps: [
      {
        step_id: "step-1",
        stage: "证据分类",
        duration_minutes: 15,
        teacher_actions: ["提供分子结构卡片与性质证据"],
        student_actions: ["小组分类并陈述结构依据"],
        assessment: "分类理由与证据链",
      },
      {
        step_id: "step-2",
        stage: "预测与验证",
        duration_minutes: 20,
        teacher_actions: ["追问反例并组织同伴质疑"],
        student_actions: ["预测性质、回应质疑并修正解释"],
        assessment: "解释是否同时使用结构和实验事实",
      },
    ],
  },
  scores: {
    curriculumAlignment: 8.1,
    knowledgeAccuracy: 9,
    teachingLogic: 8.4,
    differentiatedInstruction: 7.8,
    classroomFeasibility: 8.5,
    studentEngagement: 8.2,
    assessmentDesign: 8,
    languageAndFormat: 8.3,
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
    {
      summary: "增加同伴质疑与形成性评价",
      targetPath: "/procedure_steps/1",
      sourceCritiqueIds: ["align-001"],
    },
  ],
  unresolvedIssues: ["正式课标条目仍需教师补充核验"],
  parseWarnings: [],
};

const optimization = {
  outcome: "changed",
  message: "已形成内容修改稿，请教师核对原稿与交付稿。",
  baseline_version_id: "v0",
  selected_version_id: "v1",
  content_changed: true,
  changed_section_count: 1,
  changed_sections: [
    {
      field: "procedure_steps",
      label: "教学过程",
      before: ["教师讲解后学生完成练习"],
      after: ["学生比较结构证据、讨论反例，再解释性质差异"],
    },
  ],
  baseline_score: 7.5,
  selected_score: 8.3,
  score_delta: 0.8,
  score_notice: "内部评分仅用于筛选候选版本，不代表真实课堂效果。",
  critique_count: 5,
  reviewed_issues: [],
  validation_batch_count: 1,
  rewrite_count: 1,
  rounds: [],
  stop_reason: "quality_passed",
};

async function installRoutes(context, scenario) {
  const isOptimize = [
    "optimize",
    "unchanged",
    "needs-human",
    "failed",
  ].includes(scenario);
  const isFailed = scenario === "failed";
  const isUnchanged = scenario === "unchanged";
  const isNeedsHuman = scenario === "needs-human";
  const scenarioJob = {
    ...job,
    mode: isOptimize ? "OPTIMIZE" : "GENERATE",
    status: isFailed ? "FAILED" : isNeedsHuman ? "NEEDS_HUMAN" : "COMPLETED",
    stopReason: isFailed
      ? "rewrite_failed"
      : isUnchanged
        ? "no_actionable_feedback"
        : isNeedsHuman
          ? "max_rounds"
          : "quality_passed",
    errorMessage: isFailed ? "改写未通过结构校验，原稿仍可取回。" : null,
  };
  const scenarioOptimization = isUnchanged
    ? {
        ...optimization,
        outcome: "reviewed_unchanged",
        message: "已完成审查，但交付稿没有内容变化。",
        selected_version_id: "v0",
        content_changed: false,
        changed_section_count: 0,
        changed_sections: [],
        selected_score: 7.5,
        score_delta: 0,
        rewrite_count: 0,
        stop_reason: "no_actionable_feedback",
      }
    : optimization;
  await context.route(/\/api\/v1\/lesson-jobs(?:\?.*)?$/, (route) =>
    route.fulfill({
      json: {
        items: [job],
        page: 0,
        size: 12,
        totalElements: 1,
        totalPages: 1,
      },
    }),
  );
  await context.route(`**/api/v1/lesson-jobs/${jobId}`, (route) =>
    route.fulfill({ json: scenarioJob }),
  );
  await context.route(`**/api/v1/lesson-jobs/${jobId}/result`, (route) =>
    isFailed
      ? route.fulfill({ status: 404, json: { detail: "没有完整结果" } })
      : route.fulfill({
          json: isOptimize
            ? { ...result, optimization: scenarioOptimization }
            : result,
        }),
  );
  await context.route(`**/api/v1/lesson-jobs/${jobId}/artifacts`, (route) =>
    route.fulfill({
      json: [
        {
          artifactId: "01J00000000000000000000001",
          type: isFailed ? "ORIGINAL_DOCX" : "BEST_DOCX",
          displayName: isFailed
            ? "uploaded_original.docx"
            : "best_lesson_plan.docx",
          mediaType:
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          sizeBytes: 46781,
          sha256: "a".repeat(64),
          downloadUrl: "/api/v1/artifacts/01J00000000000000000000001/content",
        },
      ],
    }),
  );
  await context.route(`**/api/v1/lesson-jobs/${jobId}/events`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: "retry: 60000\n\n",
    }),
  );
}

async function capture(
  browser,
  viewport,
  path,
  fileName,
  scenario = "generate",
) {
  const context = await browser.newContext({ viewport });
  await installRoutes(context, scenario);
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:4173${path}`, {
    waitUntil: "networkidle",
  });
  if (
    path.startsWith("/jobs/") &&
    (await page.locator(".radar-slot").count())
  ) {
    await page.locator(".radar-slot").scrollIntoViewIfNeeded();
    await page.locator(".radar-svg").waitFor();
    await page.evaluate(() => window.scrollTo(0, 0));
  }
  await page.screenshot({
    path: `${outputDirectory}/${fileName}`,
    fullPage: true,
  });
  await context.close();
}

await mkdir(outputDirectory, { recursive: true });
const server = await preview({
  preview: { host: "127.0.0.1", port: 4173, strictPort: true },
});
const browser = await chromium.launch({ channel: "msedge" });

try {
  await capture(
    browser,
    { width: 1440, height: 1000 },
    "/",
    "01-dashboard-desktop.png",
  );
  await capture(
    browser,
    { width: 1440, height: 1000 },
    "/create/generate",
    "02-generate-desktop.png",
  );
  await capture(
    browser,
    { width: 1440, height: 1000 },
    "/create/optimize",
    "03-optimize-desktop.png",
  );
  await capture(
    browser,
    { width: 1440, height: 1000 },
    `/jobs/${jobId}`,
    "04-result-desktop.png",
  );
  await capture(
    browser,
    { width: 390, height: 844 },
    `/jobs/${jobId}`,
    "05-result-mobile.png",
  );
  await capture(
    browser,
    { width: 768, height: 1024 },
    "/",
    "06-dashboard-tablet.png",
  );
  await capture(
    browser,
    { width: 390, height: 844 },
    "/create/generate",
    "07-generate-mobile.png",
  );
  await capture(
    browser,
    { width: 1440, height: 1000 },
    `/jobs/${jobId}`,
    "08-optimize-result-desktop.png",
    "optimize",
  );
  await capture(
    browser,
    { width: 390, height: 844 },
    `/jobs/${jobId}`,
    "10-optimize-unchanged-mobile.png",
    "unchanged",
  );
  await capture(
    browser,
    { width: 390, height: 844 },
    `/jobs/${jobId}`,
    "11-optimize-needs-human-mobile.png",
    "needs-human",
  );
  await capture(
    browser,
    { width: 390, height: 844 },
    `/jobs/${jobId}`,
    "12-optimize-failed-mobile.png",
    "failed",
  );
  await capture(
    browser,
    { width: 390, height: 844 },
    `/jobs/${jobId}`,
    "09-optimize-result-mobile.png",
    "optimize",
  );
} finally {
  await browser.close();
  await server.close();
}

console.log(`UI audit screenshots written to ${outputDirectory}`);
