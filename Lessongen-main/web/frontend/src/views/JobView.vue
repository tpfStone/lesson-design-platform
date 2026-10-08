<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import axios from "axios";
import { connectJobEvents, getJob } from "../api/client";
import { useConnectionStore } from "../stores/connection";
import { useJobStore } from "../stores/jobs";
import { terminalStatuses, type JobEvent } from "../types/api";
import AppPageHeader from "../components/AppPageHeader.vue";
import BaseCard from "../components/BaseCard.vue";
import TaskProgressPanel from "../components/TaskProgressPanel.vue";
import QualityStatusCard from "../components/QualityStatusCard.vue";
import ResultDownloadPanel, { type DownloadFile } from "../components/ResultDownloadPanel.vue";
import ScorePanel from "../components/ScorePanel.vue";
import LessonPreview from "../components/LessonPreview.vue";
import ReviewDocumentPreview from "../components/ReviewDocumentPreview.vue";
import OptimizationPanel from "../components/OptimizationPanel.vue";
import { useWorkflowStore } from "../stores/workflow";

const props = defineProps<{ jobId: string }>();
const route = useRoute();
const workflow = useWorkflowStore();
const store = useJobStore();
const connection = useConnectionStore();

const linkedLessonId = computed(() => typeof route.query.lessonId === "string" ? route.query.lessonId : "");
const inWorkflow = computed(() => Boolean(route.query.workflow === "1" && workflow.activeRun && !workflow.isFinished));
const optimizeLink = ref<{ sourceVersionId: string; savedVersionId: string | null } | null>(null);

interface ReviewDraft {
  lessonId: string;
  jobId: string;
  sourceVersionId: string;
  sourceVersionNumber: number;
  originalContent: string;
  candidateContent: string | null;
  candidateSource: string | null;
  jobStatus: string;
  savedVersionId: string | null;
}
const review = ref<ReviewDraft | null>(null);
const reviewLoading = ref(false);
const saveBusy = ref(false);
const autoSaveBusy = ref(false);
const autoSaveAttempted = ref(false);
const saveError = ref("");

interface GeneratedLessonSave {
  lessonId: string;
  versionId: string;
  versionNumber: number;
  title: string;
}
interface PlatformLessonDetail {
  lesson: { id: string; title: string; currentVersionId: string };
  versions: Array<{ id: string; versionNumber: number }>;
}
const generatedLesson = ref<GeneratedLessonSave | null>(null);
const generationSaveBusy = ref(false);
const generationSaveAttempted = ref(false);
const generationSaveError = ref("");
const generatedLessonIsWorkflowBound = computed(() => Boolean(
  generatedLesson.value && workflow.activeRun?.lessonId === generatedLesson.value.lessonId,
));

const events = ref<JobEvent[]>([]);
const loadError = ref("");
let stopEvents: (() => void) | undefined;
let polling: number | undefined;
let terminalLoaded = false;
let terminalDataInFlight: Promise<boolean> | undefined;
let active = true;
let requestSequence = 0;
let appliedSequence = 0;

const job = computed(() => store.current);
const terminal = computed(() => !!job.value && terminalStatuses.includes(job.value.status));
const reviewedAndSaved = computed(() => job.value?.mode === "OPTIMIZE" && !!optimizeLink.value?.savedVersionId);
const overallScore = computed(() => {
  const value = store.result?.overallScore;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
});
const qualityPassed = computed(() => overallScore.value != null && overallScore.value >= 8);
// The quality gate uses the raw score. Keep the one-decimal display from
// rounding a score below 8 (for example 7.96) up to a misleading 8.0.
const displayedQualityScore = computed(() =>
  overallScore.value == null ? null : Math.floor(overallScore.value * 10) / 10,
);
const optimizationChanged = computed(() => Boolean(store.result?.optimization?.content_changed));
const sourceVersionLabel = computed(() => review.value ? `V${review.value.sourceVersionNumber}` : "当前版本");

const primaryArtifact = computed(() => store.artifacts.find(item => item.type === "BEST_DOCX"));
const revisedCandidateArtifact = computed(() => store.artifacts.find(item => item.type === "REVISED_CANDIDATE_DOCX"));
const downloadFiles = computed<DownloadFile[]>(() => {
  if (!terminal.value) return [];
  const files: DownloadFile[] = [];
  if (job.value?.mode === "OPTIMIZE" && reviewedAndSaved.value && linkedLessonId.value && optimizeLink.value?.savedVersionId) {
    files.push({
      key: "saved-docx",
      label: `${job.value.topic || "教案"}_设计修改.docx`,
      href: `/api/platform/lessons/${encodeURIComponent(linkedLessonId.value)}/versions/${encodeURIComponent(optimizeLink.value.savedVersionId)}/export/docx`,
    });
  } else if (primaryArtifact.value) {
    files.push({ key: primaryArtifact.value.artifactId, label: job.value?.mode === "OPTIMIZE" ? "本次修改稿 Word" : "生成教案 Word", href: primaryArtifact.value.downloadUrl });
  }
  if (job.value?.mode === "OPTIMIZE" && !qualityPassed.value && revisedCandidateArtifact.value && revisedCandidateArtifact.value.artifactId !== primaryArtifact.value?.artifactId) {
    files.push({ key: revisedCandidateArtifact.value.artifactId, label: "可参考的其他修改方案 Word", href: revisedCandidateArtifact.value.downloadUrl });
  }
  return files;
});

const optimizePhases = ["理解教案内容", "分析主要问题", "生成改进方案", "检查修改质量", "完成优化"];
const generatePhases = ["理解教学要求", "形成教学设计", "完善课堂活动", "检查教案质量", "完成生成"];
function phaseIndex(stage?: string | null) {
  const value = (stage || "").toLowerCase();
  if (/final|export/.test(value)) return 4;
  if (/judge|critic|validator|verifier|pairwise|review/.test(value)) return 3;
  if (/writer|rewriter|rewrite/.test(value)) return 2;
  if (/architect|analysis|plan/.test(value)) return 1;
  return 0;
}
const currentPhaseIndex = computed(() => terminal.value ? 4 : phaseIndex(job.value?.currentStage));
const phases = computed(() => job.value?.mode === "GENERATE" ? generatePhases : optimizePhases);
const progressMessage = computed(() => {
  const index = currentPhaseIndex.value;
  if (job.value?.mode === "GENERATE") {
    return [
      "正在读取教学主题和你提供的教学依据。",
      "正在组织教学目标、内容结构和整体教学路线。",
      "正在完善课堂活动、提问与评价设计。",
      "正在检查教案的完整性、可实施性与内部质量。",
      "正在整理最终教案和可下载结果。",
    ][index] || "正在处理教案生成任务。";
  }
  return [
    "正在理解当前教案的结构、教学目标和课堂安排。",
    "正在结合已有上下文分析最值得优先处理的问题。",
    "正在生成并完善本次教案修改方案。",
    "正在检查修改后的整体质量和可能的退步风险。",
    "正在整理本次设计修改结果。",
  ][index] || "正在进行设计修改。";
});
const displayProgress = computed(() => {
  const value = job.value?.progressPercent;
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : undefined;
});

function friendlyError(reason: unknown, fallback: string) {
  if (!axios.isAxiosError(reason)) return fallback;
  return (reason.response?.data as { detail?: string } | undefined)?.detail || fallback;
}

function textValue(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}
function stringList(value: unknown) {
  return Array.isArray(value) ? value.map(item => textValue(item)).filter(Boolean) : [];
}
function lessonPlanToText(plan: Record<string, unknown>) {
  const metadata = (plan.metadata && typeof plan.metadata === "object" ? plan.metadata : {}) as Record<string, unknown>;
  const lines: string[] = [];
  const pushSection = (title: string, content: string | string[]) => {
    const items = Array.isArray(content) ? content.filter(Boolean) : [content].filter(Boolean);
    if (!items.length) return;
    lines.push(title, ...items, "");
  };

  const subject = textValue(metadata.subject) || job.value?.subject || "";
  const grade = textValue(metadata.grade) || job.value?.grade || "";
  const topic = textValue(metadata.topic) || job.value?.topic || "教案";
  const duration = typeof metadata.duration_minutes === "number" ? metadata.duration_minutes : job.value?.durationMinutes;
  lines.push(`${subject ? `${subject} ` : ""}${topic} 教案`.trim());
  if (grade) lines.push(`年级：${grade}`);
  if (duration) lines.push(`课时：${duration} 分钟`);
  if (textValue(metadata.textbook_version)) lines.push(`教材版本：${textValue(metadata.textbook_version)}`);
  lines.push("");

  pushSection("一、设计主张", textValue(plan.design_thesis));
  pushSection("二、核心问题", textValue(plan.driving_question));
  pushSection("三、内容分析", textValue(plan.content_analysis));
  pushSection("四、学情分析", textValue(plan.student_analysis));

  const objectives = Array.isArray(plan.learning_objectives) ? plan.learning_objectives as Array<Record<string, unknown>> : [];
  if (objectives.length) {
    pushSection("五、学习目标与达成证据", objectives.map((item, index) => {
      const description = textValue(item.description);
      const evidence = textValue(item.evidence_of_achievement);
      return `${index + 1}. ${description}${evidence ? `\n   达成证据：${evidence}` : ""}`;
    }));
  }
  pushSection("六、教学重点", stringList(plan.key_points).map((item, index) => `${index + 1}. ${item}`));
  pushSection("七、教学难点", stringList(plan.difficult_points).map((item, index) => `${index + 1}. ${item}`));

  const steps = Array.isArray(plan.procedure_steps) ? plan.procedure_steps as Array<Record<string, unknown>> : [];
  if (steps.length) {
    const stepLines: string[] = [];
    steps.forEach((step, index) => {
      const stage = textValue(step.stage) || `环节 ${index + 1}`;
      const minutes = typeof step.duration_minutes === "number" ? `（${step.duration_minutes} 分钟）` : "";
      stepLines.push(`${index + 1}. ${stage}${minutes}`);
      const teacher = stringList(step.teacher_actions);
      const students = stringList(step.student_actions);
      if (teacher.length) stepLines.push(`   教师活动：${teacher.join("；")}`);
      if (students.length) stepLines.push(`   学生活动：${students.join("；")}`);
      const questions = Array.isArray(step.questions) ? step.questions as Array<Record<string, unknown>> : [];
      const questionText = questions.map(item => textValue(item.question)).filter(Boolean);
      if (questionText.length) stepLines.push(`   关键问题：${questionText.join("；")}`);
      if (textValue(step.assessment)) stepLines.push(`   观察证据：${textValue(step.assessment)}`);
    });
    pushSection("八、教学过程", stepLines);
  }

  pushSection("九、评价设计", textValue(plan.assessment_plan));
  pushSection("十、差异化支持", textValue(plan.differentiation));
  pushSection("十一、作业设计", textValue(plan.homework));
  pushSection("十二、板书设计", textValue(plan.board_design));

  return lines.join("\n").trim();
}

function generatedLessonStorageKey() {
  return `platform-generated-lesson-${props.jobId}`;
}
function restoreGeneratedLesson() {
  try {
    const raw = window.localStorage.getItem(generatedLessonStorageKey());
    if (!raw) return;
    const saved = JSON.parse(raw) as GeneratedLessonSave;
    if (saved.lessonId && saved.versionId) generatedLesson.value = saved;
  } catch { /* ignore unavailable or malformed browser storage */ }
}
async function saveGeneratedLesson() {
  if (generationSaveBusy.value || generatedLesson.value || !store.result || !job.value || job.value.mode !== "GENERATE" || job.value.status !== "COMPLETED") return;
  const plan = store.result.bestLessonPlan as Record<string, unknown>;
  const metadata = (plan.metadata && typeof plan.metadata === "object" ? plan.metadata : {}) as Record<string, unknown>;
  const title = textValue(metadata.topic) || job.value.topic || "生成教案";
  const subject = textValue(metadata.subject) || job.value.subject;
  const grade = textValue(metadata.grade) || job.value.grade;
  const topic = textValue(metadata.topic) || job.value.topic;
  const rawDuration = typeof metadata.duration_minutes === "number" ? metadata.duration_minutes : job.value.durationMinutes;
  const durationMinutes = typeof rawDuration === "number" && Number.isInteger(rawDuration) && rawDuration >= 5 && rawDuration <= 240 ? rawDuration : null;
  const content = lessonPlanToText(plan);
  if (!subject?.trim() || !grade?.trim() || !topic?.trim() || !content) {
    generationSaveError.value = "生成结果缺少保存教案所需的基本信息，请先下载结果文件并保留本次任务。";
    return;
  }

  generationSaveBusy.value = true;
  generationSaveAttempted.value = true;
  generationSaveError.value = "";
  try {
    const detail = (await axios.post<PlatformLessonDetail>("/api/platform/lessons", {
      title, subject, grade, topic, durationMinutes, content,
    })).data;
    const versionId = detail.lesson.currentVersionId;
    const version = detail.versions.find(item => item.id === versionId) || detail.versions[detail.versions.length - 1];
    if (!detail.lesson.id || !versionId || !version) throw new Error("generated lesson save response is incomplete");
    generatedLesson.value = {
      lessonId: detail.lesson.id, versionId, versionNumber: version.versionNumber, title: detail.lesson.title || title,
    };
    try { window.localStorage.setItem(generatedLessonStorageKey(), JSON.stringify(generatedLesson.value)); } catch { /* server save remains valid */ }
  } catch (reason) {
    generationSaveError.value = friendlyError(reason, "教案已经生成，但暂时无法保存到“我的教案”。请稍后重试，不会重新运行模型。");
  } finally {
    generationSaveBusy.value = false;
  }
}
function retryGeneratedLessonSave() {
  generationSaveAttempted.value = false;
  void saveGeneratedLesson();
}
function useGeneratedLessonInWorkflow() {
  if (!generatedLesson.value || route.query.workflow !== "1" || !workflow.activeRun || workflow.currentStep?.id !== "F2") return;
  workflow.bindLesson({
    lessonId: generatedLesson.value.lessonId,
    lessonTitle: generatedLesson.value.title,
    versionId: generatedLesson.value.versionId,
    versionNumber: generatedLesson.value.versionNumber,
  });
  workflow.completeStep("F2");
}
async function maybeSaveGeneratedLesson() {
  if (generationSaveAttempted.value || generatedLesson.value || !terminal.value || !store.result || job.value?.mode !== "GENERATE" || job.value.status !== "COMPLETED") return;
  await saveGeneratedLesson();
}

async function loadReview() {
  if (!linkedLessonId.value || !optimizeLink.value || reviewLoading.value || review.value || job.value?.status === "FAILED") return;
  reviewLoading.value = true;
  saveError.value = "";
  try {
    review.value = (await axios.get<ReviewDraft>(
      `/api/platform/lessons/${encodeURIComponent(linkedLessonId.value)}/optimizations/${encodeURIComponent(props.jobId)}/review`,
    )).data;
  } catch (reason) {
    saveError.value = friendlyError(reason, "暂时无法读取本次修改稿，请稍后重试。");
  } finally {
    reviewLoading.value = false;
  }
}

async function saveVersion(content: string, automatic = false): Promise<boolean> {
  if (!linkedLessonId.value || !optimizeLink.value || !review.value || !content.trim() || saveBusy.value || autoSaveBusy.value) return false;
  if (automatic) autoSaveBusy.value = true; else saveBusy.value = true;
  saveError.value = "";
  try {
    const saved = (await axios.post<{ versionId: string; versionNumber: number; unchanged: boolean }>(
      `/api/platform/lessons/${encodeURIComponent(linkedLessonId.value)}/optimizations/${encodeURIComponent(props.jobId)}/review`,
      { expectedVersionId: review.value.sourceVersionId, content, confirmed: true },
    )).data;
    optimizeLink.value.savedVersionId = saved.versionId;
    if (workflow.activeRun?.lessonId === linkedLessonId.value && workflow.currentStep?.id === "F2") {
      workflow.updateVersion(saved.versionId, saved.versionNumber);
      workflow.completeStep("F2");
    }
    return true;
  } catch (reason) {
    saveError.value = friendlyError(reason, "暂时无法保存本次修改稿，请稍后重试。");
    return false;
  } finally {
    autoSaveBusy.value = false;
    saveBusy.value = false;
  }
}

async function maybeFinishOptimize() {
  if (autoSaveAttempted.value || job.value?.mode !== "OPTIMIZE" || !terminal.value || !store.result || !optimizeLink.value) return;
  if (job.value.status === "FAILED") return;

  if (!optimizationChanged.value) {
    autoSaveAttempted.value = true;
    if (workflow.activeRun?.lessonId === linkedLessonId.value && workflow.currentStep?.id === "F2") workflow.completeStep("F2");
    return;
  }

  if (!qualityPassed.value || !review.value?.candidateContent || optimizeLink.value.savedVersionId) return;
  autoSaveAttempted.value = true;
  const saved = await saveVersion(review.value.candidateContent, true);
  if (!saved) autoSaveAttempted.value = false;
}

async function sync() {
  const requestId = ++requestSequence;
  try {
    const next = await getJob(props.jobId);
    if (!active || requestId < appliedSequence) return null;
    if (terminal.value && !terminalStatuses.includes(next.status)) return job.value;
    appliedSequence = requestId;
    store.current = next;
    connection.touched();
    loadError.value = "";
    if (terminalStatuses.includes(next.status)) {
      stopEvents?.();
      stopEvents = undefined;
    }
    if (terminalStatuses.includes(next.status) && !terminalLoaded) {
      terminalDataInFlight ||= store.loadTerminalData(props.jobId, next.status === "FAILED");
      const loaded = await terminalDataInFlight;
      terminalDataInFlight = undefined;
      if (!active) return null;
      terminalLoaded = loaded;
      if (terminalLoaded && polling) {
        window.clearInterval(polling);
        polling = undefined;
      }
    }
    return next;
  } catch (reason) {
    if (active && requestId === requestSequence) loadError.value = friendlyError(reason, "暂时无法读取任务，请稍后重试。");
    return null;
  }
}
function received(event: JobEvent) {
  if (!active || terminal.value) return;
  if (!events.value.some(item => item.sequence === event.sequence)) events.value.push(event);
  events.value.sort((a, b) => a.sequence - b.sequence);
  void sync();
}
function ensureUpdates(next: NonNullable<typeof job.value>) {
  if (!terminalStatuses.includes(next.status) && !stopEvents) {
    stopEvents = connectJobEvents(props.jobId, received, value => connection.setLive(value));
  }
  if (!terminalLoaded && !polling) {
    polling = window.setInterval(() => {
      if ((terminal.value && !terminalLoaded) || connection.mode !== "live") void sync();
    }, 2000);
  }
}
function settleTerminalData() {
  terminalLoaded = store.resultReady && store.artifactsReady;
  if (terminalLoaded && polling) {
    window.clearInterval(polling);
    polling = undefined;
  }
}
async function retryResult() {
  await store.loadResult(props.jobId, job.value?.status === "FAILED");
  if (active) settleTerminalData();
}
async function retryArtifacts() {
  await store.loadArtifacts(props.jobId);
  if (active) settleTerminalData();
}
async function resume() {
  const next = await sync();
  if (next) ensureUpdates(next);
}

onMounted(async () => {
  active = true;
  restoreGeneratedLesson();
  store.resetCurrent();
  connection.reset();
  if (linkedLessonId.value) {
    try {
      optimizeLink.value = (await axios.get<{ sourceVersionId: string; savedVersionId: string | null }>(
        `/api/platform/lessons/${encodeURIComponent(linkedLessonId.value)}/optimizations/${encodeURIComponent(props.jobId)}`,
      )).data;
    } catch {
      optimizeLink.value = null;
    }
  }
  const initial = await sync();
  if (initial) ensureUpdates(initial);
});
watch([terminal, optimizeLink], ([ready, link]) => {
  if (ready && job.value?.mode === "OPTIMIZE" && job.value.status !== "FAILED" && link) void loadReview();
}, { immediate: true });
watch([terminal, () => store.result, review, optimizeLink], () => { void maybeFinishOptimize(); }, { deep: false });
watch([terminal, () => store.result], () => { void maybeSaveGeneratedLesson(); }, { deep: false });
onBeforeUnmount(() => {
  active = false;
  requestSequence += 1;
  stopEvents?.();
  if (polling) window.clearInterval(polling);
  store.resetCurrent();
});
</script>

<template>
  <main class="f2-job-page">
    <AppPageHeader
      :title="job?.mode === 'GENERATE' ? '教案生成' : '设计修改'"
      :description="job ? `${job.topic} · ${job.subject} · ${job.grade}` : '正在读取任务状态……'"
    >
      <template #actions>
        <RouterLink class="v2-button v2-button--secondary" to="/tasks">查看任务记录</RouterLink>
      </template>
    </AppPageHeader>

    <BaseCard v-if="loadError && !job" class="error-card">
      <h2>暂时无法打开任务</h2>
      <p>{{ loadError }}</p>
      <button type="button" class="v2-button v2-button--secondary" @click="resume">重新加载</button>
    </BaseCard>

    <template v-else-if="job">
      <p v-if="loadError" class="sync-alert" role="alert">任务同步暂时中断，页面保留上次读取的状态。<button type="button" @click="resume">重新同步</button></p>

      <template v-if="!terminal">
        <TaskProgressPanel
          :title="phases[currentPhaseIndex] || '正在处理'"
          :message="progressMessage"
          :progress="displayProgress"
        >
          <ol class="phase-list" aria-label="任务阶段">
            <li v-for="(phase,index) in phases" :key="phase" :class="{ done:index<currentPhaseIndex, current:index===currentPhaseIndex }">
              <span>{{ index < currentPhaseIndex ? '✓' : index + 1 }}</span>
              <strong>{{ phase }}</strong>
            </li>
          </ol>
          <p class="leave-note">任务保存在服务端。你可以离开此页面，稍后从“任务记录”回到同一个任务。</p>
        </TaskProgressPanel>
      </template>

      <template v-else>
        <template v-if="job.mode === 'OPTIMIZE'">
          <QualityStatusCard
            v-if="job.status !== 'FAILED' && store.result"
            :title="qualityPassed ? '质量检查通过' : '已完成优化，但尚未达到建议使用标准'"
            :description="qualityPassed ? '已达到建议使用标准，本次优化结果可作为正式修改稿查看。' : '建议教师结合重点提示复核后使用。'"
            :status="displayedQualityScore == null ? '分数暂不可用' : `${displayedQualityScore.toFixed(1)} / 10`"
            :attention="!qualityPassed"
          />

          <BaseCard v-else-if="job.status === 'FAILED'" class="failed-card">
            <h2>本次设计修改没有完成</h2>
            <p>{{ job.errorMessage || '任务运行未完整完成，原教案不会因此改变。请稍后重试。' }}</p>
          </BaseCard>

          <BaseCard v-if="autoSaveBusy" class="save-state-card">
            <strong>质量检查已通过，正在自动保存新版本……</strong>
          </BaseCard>
          <BaseCard v-else-if="!optimizationChanged && job.status !== 'FAILED'" class="save-state-card saved">
            <div>
              <strong>本次未产生新的教案版本</strong>
              <p>正文没有发生实际变化，当前仍使用 {{ sourceVersionLabel }}；任务结果已经保存在任务记录中。</p>
            </div>
          </BaseCard>
          <BaseCard v-else-if="reviewedAndSaved && optimizeLink" class="save-state-card saved">
            <div>
              <strong>{{ optimizeLink.savedVersionId === optimizeLink.sourceVersionId ? '本次没有产生新的正文版本' : '修改稿已保存到“我的教案”' }}</strong>
              <p>{{ optimizeLink.savedVersionId === optimizeLink.sourceVersionId ? `当前仍使用 ${sourceVersionLabel}。` : '原版本已保留，后续工作流会自动使用当前最新正式版本。' }}</p>
            </div>
            <RouterLink class="v2-button v2-button--secondary" :to="{ path:`/lessons/${linkedLessonId}`, query:{ version:optimizeLink.savedVersionId || optimizeLink.sourceVersionId } }">查看教案</RouterLink>
          </BaseCard>

          <BaseCard v-if="qualityPassed && optimizationChanged && review?.candidateContent && !reviewedAndSaved && saveError" class="manual-save-card retry-save-card">
            <div>
              <p class="section-label">版本保存</p>
              <h2>修改已经完成，但新版本还没有保存成功</h2>
              <p>任务结果不会丢失。你可以重新尝试保存，不会重新运行模型。</p>
            </div>
            <button type="button" class="v2-button v2-button--primary" :disabled="saveBusy || autoSaveBusy" @click="saveVersion(review.candidateContent)">{{ saveBusy || autoSaveBusy ? '正在保存…' : '重新保存新版本' }}</button>
          </BaseCard>
          <p v-if="saveError" class="sync-alert" role="alert">{{ saveError }}</p>

          <section v-if="store.result" class="result-layout">
            <div class="result-main">
              <OptimizationPanel v-if="store.result.optimization" :summary="store.result.optimization" />

              <BaseCard v-if="!qualityPassed && (store.result.unresolvedIssues.length || store.result.parseWarnings.length)" class="attention-card">
                <p class="section-label">建议重点关注</p>
                <h2>这些内容仍建议教师复核</h2>
                <ul>
                  <li v-for="item in [...store.result.unresolvedIssues, ...store.result.parseWarnings].slice(0,8)" :key="item">{{ item }}</li>
                </ul>
              </BaseCard>

              <BaseCard v-if="!qualityPassed && review?.candidateContent && !reviewedAndSaved" class="manual-save-card">
                <div>
                  <p class="section-label">本次修改稿</p>
                  <h2>需要的话，可以保存为一个新的教案版本</h2>
                  <p>当前结果已保存在任务记录中，但不会自动替换“我的教案”的当前版本。</p>
                </div>
                <details>
                  <summary>预览本次修改稿</summary>
                  <div class="candidate-preview"><ReviewDocumentPreview :content="review.candidateContent" /></div>
                </details>
                <button type="button" class="v2-button v2-button--primary" :disabled="saveBusy" @click="saveVersion(review.candidateContent)">{{ saveBusy ? '正在保存…' : inWorkflow ? '保存为新版本并继续工作流' : '保存本次修改稿为新版本' }}</button>
              </BaseCard>

              <BaseCard v-if="reviewLoading" class="save-state-card">正在读取本次修改稿……</BaseCard>
              <BaseCard v-if="review && !review.candidateContent && optimizationChanged && !reviewLoading" class="attention-card"><p>本次任务没有提供可安全保存的修改稿，请保留原版本并结合任务结果人工复核。</p></BaseCard>

              <details v-if="review?.candidateContent && qualityPassed" class="candidate-drawer">
                <summary>查看已通过质量检查的完整修改稿</summary>
                <div class="candidate-preview"><ReviewDocumentPreview :content="review.candidateContent" /></div>
              </details>
            </div>
            <!--
            <aside class="quality-aside" v-if="store.result">
              <ScorePanel :scores="store.result.scores" :overall="displayedQualityScore" />
            </aside>
            -->
          </section>
        </template>

        <template v-else>
          <QualityStatusCard
            v-if="job.status !== 'FAILED'"
            title="教案生成完成"
            description="生成结果已经保存在本次任务中；系统会同时把完整教案保存到“我的教案”。"
            :status="overallScore == null ? '已完成' : `${overallScore.toFixed(1)} / 10`"
          />
          <BaseCard v-else class="failed-card"><h2>本次教案生成没有完成</h2><p>{{ job.errorMessage || '请检查输入后重新尝试。' }}</p></BaseCard>

          <BaseCard v-if="generationSaveBusy" class="save-state-card">
            <strong>正在保存到“我的教案”……</strong>
          </BaseCard>
          <BaseCard v-else-if="generatedLesson" class="save-state-card saved generated-save-card">
            <div>
              <strong>已保存到“我的教案”</strong>
              <p>已创建 V{{ generatedLesson.versionNumber }}，刷新或重新进入“我的教案”仍可找到这份教案。</p>
            </div>
            <div class="save-actions">
              <RouterLink class="v2-button v2-button--secondary" :to="{ path:`/lessons/${generatedLesson.lessonId}`, query:{ version:generatedLesson.versionId } }">查看教案</RouterLink>
              <button v-if="inWorkflow && workflow.currentStep?.id === 'F2' && !generatedLessonIsWorkflowBound" type="button" class="v2-button v2-button--primary" @click="useGeneratedLessonInWorkflow">使用此教案继续工作流</button>
              <RouterLink v-else-if="inWorkflow && generatedLessonIsWorkflowBound && !workflow.isFinished && workflow.currentDestination" class="v2-button v2-button--primary" :to="workflow.currentDestination">进入下一步</RouterLink>
            </div>
          </BaseCard>
          <BaseCard v-else-if="generationSaveError" class="manual-save-card retry-save-card">
            <div>
              <p class="section-label">保存教案</p>
              <h2>教案已经生成，但还没有进入“我的教案”</h2>
              <p>{{ generationSaveError }}</p>
            </div>
            <button type="button" class="v2-button v2-button--primary" :disabled="generationSaveBusy" @click="retryGeneratedLessonSave">重新保存到“我的教案”</button>
          </BaseCard>

          <section v-if="store.result" class="generated-result"><LessonPreview :plan="store.result.bestLessonPlan" /></section>
        </template>

        <p v-if="store.resultError" class="sync-alert" role="alert">{{ store.resultError }} <button type="button" @click="retryResult">重新读取</button></p>
        <p v-if="store.artifactWarning" class="sync-alert" role="alert">{{ store.artifactWarning }} <button type="button" @click="retryArtifacts">重新读取文件</button></p>

        <ResultDownloadPanel :files="downloadFiles" />
      </template>
    </template>

    <div v-else class="loading-card v2-card" role="status">正在读取任务……</div>

  </main>
</template>

<style scoped>
.f2-job-page{display:grid;gap:var(--space-6);color:var(--color-text)}
.error-card,.failed-card,.loading-card{padding:24px}.error-card h2,.failed-card h2{margin:0 0 8px;font-size:20px}.error-card p,.failed-card p{margin:0 0 16px;color:var(--color-text-secondary);line-height:1.7}
.sync-alert{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:0;padding:12px 14px;border:1px solid #efd59b;border-radius:var(--radius-md);color:var(--color-attention);background:var(--color-attention-soft);font-size:13px}.sync-alert button{border:0;color:var(--color-primary);background:transparent;font-weight:700;cursor:pointer}
.phase-list{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:22px 0 0;padding:0;list-style:none}.phase-list li{display:flex;align-items:center;gap:8px;min-width:0;padding:10px;border-radius:var(--radius-md);color:var(--color-text-muted);background:var(--color-surface-soft)}.phase-list li>span{width:24px;height:24px;display:grid;place-items:center;flex:none;border:1px solid #cad5e5;border-radius:50%;font-size:11px;font-weight:800}.phase-list li strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.phase-list li.done,.phase-list li.current{color:var(--color-primary);background:var(--color-primary-soft)}.phase-list li.done>span{border-color:var(--color-primary);color:#fff;background:var(--color-primary)}.phase-list li.current>span{border:2px solid var(--color-primary);color:var(--color-primary);background:#fff}.leave-note{margin:16px 0 0;color:var(--color-text-secondary);font-size:13px;line-height:1.65}
.save-state-card{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:18px 20px}.save-state-card strong{color:var(--color-text)}.save-state-card p{margin:5px 0 0;color:var(--color-text-secondary);font-size:13px}.save-state-card.saved{border-color:var(--color-primary-border);background:var(--color-primary-soft)}.save-actions{display:flex;align-items:center;justify-content:flex-end;gap:10px;flex:none}
.result-layout{display:grid;grid-template-columns:minmax(0,1fr);gap:20px;align-items:start}.result-main{display:grid;gap:20px}.quality-aside{position:sticky;top:calc(var(--header-height) + 20px)}
.attention-card,.manual-save-card{padding:22px}.section-label{margin:0;color:var(--color-primary);font-size:12px;font-weight:700}.attention-card h2,.manual-save-card h2{margin:6px 0 10px;font-size:20px}.attention-card ul{margin:12px 0 0;padding-left:20px;color:var(--color-text-secondary);line-height:1.75}.manual-save-card>div>p:last-child{margin:0;color:var(--color-text-secondary);line-height:1.7}.manual-save-card details,.candidate-drawer{margin-top:16px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff}.manual-save-card summary,.candidate-drawer>summary{padding:13px 15px;color:var(--color-primary);font-weight:700;cursor:pointer}.manual-save-card .v2-button{margin-top:16px}.candidate-preview{max-height:520px;overflow:auto;border-top:1px solid var(--color-border)}.candidate-preview :deep(.review-paper){box-shadow:none}
.generated-result{overflow:hidden;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff;box-shadow:var(--shadow-subtle)}
@media(max-width:900px){.result-layout{grid-template-columns:1fr}.quality-aside{position:static}.phase-list{grid-template-columns:1fr}.phase-list li strong{white-space:normal}}
@media(max-width:680px){.sync-alert,.save-state-card{align-items:stretch;flex-direction:column}.save-actions{align-items:stretch;flex-direction:column}.save-state-card .v2-button{width:100%}}
</style>
