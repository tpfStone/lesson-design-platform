<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import axios from "axios";
import { RouterLink, useRoute, useRouter } from "vue-router";
import AppPageHeader from "../components/AppPageHeader.vue";
import LessonSelectorBar, { type LessonOption, type VersionOption } from "../components/LessonSelectorBar.vue";
import { bridgeRequest } from "../features/navigation/bridge";
import { useWorkflowStore } from "../stores/workflow";

const route = useRoute();
const router = useRouter();
const workflow = useWorkflowStore();
const preferredLessonId = computed(() => typeof route.query.lessonId === "string" ? route.query.lessonId : "");
const preferredVersionId = computed(() => typeof route.query.versionId === "string" ? route.query.versionId : "");
const busy = ref(false);
const autoStarting = ref(false);
const error = ref("");

const isWorkflowStep = computed(() => Boolean(
  route.query.workflow === "1" && workflow.activeRun && !workflow.isFinished && workflow.currentStep?.id === "F4",
));
const isLaterWorkflowStep = computed(() => Boolean(
  isWorkflowStep.value && (workflow.activeRun?.currentIndex ?? 0) > 0,
));
const hasBoundWorkflowLesson = computed(() => Boolean(
  workflow.activeRun?.lessonId && workflow.activeRun?.versionId,
));
const missingWorkflowLesson = computed(() => Boolean(
  isLaterWorkflowStep.value && !hasBoundWorkflowLesson.value,
));

async function startNavigation(lesson: LessonOption, version: VersionOption) {
  if (busy.value) return;
  if (isWorkflowStep.value && workflow.activeRun && ((workflow.activeRun.currentIndex ?? 0) === 0 || !workflow.activeRun.lessonId)) {
    workflow.bindLesson({
      lessonId: lesson.id,
      lessonTitle: lesson.title,
      versionId: version.id,
      versionNumber: version.versionNumber,
    });
  }

  busy.value = true;
  error.value = "";
  const storageKey = `platform.workflow.f4.${lesson.id}.${version.id}`;
  const requestKey = window.localStorage.getItem(storageKey) || crypto.randomUUID();
  try {
    window.localStorage.setItem(storageKey, requestKey);
    const result = await bridgeRequest<{ sessionId: string }>(`/lessons/${encodeURIComponent(lesson.id)}/sessions`, {
      versionId: version.id,
      requestKey,
      subject: lesson.subject || "未指定学科",
      grade: lesson.grade || "未指定年级",
      topic: lesson.topic || lesson.title,
    });
    const workflowQuery = isWorkflowStep.value ? "&workflow=1" : "";
    const target = `/platform/navigation?session=${encodeURIComponent(result.sessionId)}${workflowQuery}`;
    if (isWorkflowStep.value) workflow.rememberPath("F4", target);
    window.localStorage.removeItem(storageKey);
    await router.push(target);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "暂时无法进入协同共析，请稍后重试。";
  } finally {
    busy.value = false;
  }
}

async function startBoundWorkflowLesson() {
  const run = workflow.activeRun;
  if (!run?.lessonId || !run.versionId || !isLaterWorkflowStep.value) return;
  autoStarting.value = true;
  error.value = "";
  try {
    const detail = (await axios.get<{ lesson: LessonOption; versions: VersionOption[] }>(
      `/api/platform/lessons/${encodeURIComponent(run.lessonId)}`,
    )).data;
    const version = detail.versions.find(item => item.id === run.versionId);
    if (!version) throw new Error("工作流绑定的教案版本已不存在，请返回工作流检查当前版本。");
    await startNavigation(detail.lesson, version);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "无法读取工作流教案。";
  } finally {
    autoStarting.value = false;
  }
}

onMounted(() => {
  if (route.query.autostart === "1" && isLaterWorkflowStep.value && hasBoundWorkflowLesson.value) {
    void startBoundWorkflowLesson();
  }
});
</script>

<template>
  <main class="navigation-entry-page">
    <AppPageHeader
      title="协同共析"
      description="逐节查看教学建议，由教师决定采纳或保留原稿，并把修订结果保存为新的教案版本。"
    />

    <p v-if="error" class="entry-error" role="alert">{{ error }}</p>

    <section v-if="autoStarting" class="entry-state v2-card" aria-live="polite">
      <span class="state-mark">协</span>
      <div>
        <strong>正在载入本次工作流教案</strong>
        <p>已沿用前一步确定的教案和最新版本，无需再次选择。</p>
      </div>
    </section>

    <section v-else-if="missingWorkflowLesson" class="entry-state entry-state--attention v2-card">
      <span class="state-mark">!</span>
      <div>
        <strong>暂时无法继续当前工作流</strong>
        <p>这是工作流的后续步骤，但没有找到前一步绑定的教案。请返回工作流恢复正确状态，不要重新选择另一份教案。</p>
        <RouterLink class="v2-button v2-button--secondary" to="/workflows">返回工作流</RouterLink>
      </div>
    </section>

    <template v-else>
      <LessonSelectorBar
        :initial-lesson-id="preferredLessonId || workflow.activeRun?.lessonId"
        :initial-version-id="preferredVersionId || workflow.activeRun?.versionId"
        :action-label="busy ? '正在进入……' : isWorkflowStep ? '确认并开始共析' : '开始共析'"
        :action-busy="busy"
        @action="startNavigation"
      />
    </template>

    <p class="recovery-link">已有未完成的协同共析？<RouterLink to="/platform/navigation">恢复上次进度 →</RouterLink></p>
  </main>
</template>

<style scoped>
.navigation-entry-page{display:grid;gap:18px;color:var(--color-text)}
.entry-error{margin:0;padding:12px 14px;border:1px solid #f1c5c8;border-radius:var(--radius-md);color:var(--color-danger);background:var(--color-danger-soft)}
.entry-state{display:flex;align-items:flex-start;gap:15px;padding:22px}.entry-state--attention{border-color:#ead49e;background:var(--color-attention-soft)}
.state-mark{display:grid;place-items:center;flex:none;width:38px;height:38px;border-radius:10px;color:#fff;background:var(--color-primary);font-weight:800}.entry-state--attention .state-mark{background:var(--color-attention)}
.entry-state strong{display:block;margin:2px 0 5px;font-size:16px}.entry-state p{margin:0 0 14px;color:var(--color-text-secondary);font-size:13px;line-height:1.7}
.recovery-link{margin:0;color:var(--color-text-secondary);font-size:13px;line-height:1.7}.recovery-link a{color:var(--color-primary);font-weight:700}
</style>
