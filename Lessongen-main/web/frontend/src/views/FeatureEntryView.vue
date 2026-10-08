<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import AppPageHeader from "../components/AppPageHeader.vue";
import LessonSelectorBar, { type LessonOption, type VersionOption } from "../components/LessonSelectorBar.vue";
import { useWorkflowStore } from "../stores/workflow";

const router = useRouter();
const workflow = useWorkflowStore();

const isWorkflowStep = computed(() => Boolean(workflow.activeRun && workflow.currentStep?.id === "F1"));
const workflowHasLesson = computed(() => Boolean(
  isWorkflowStep.value && workflow.activeRun?.lessonId && workflow.activeRun?.versionId,
));

function openBatch() {
  void router.push("/review/batch");
}

function confirmLesson(lesson: LessonOption, version: VersionOption) {
  if (isWorkflowStep.value && !workflow.activeRun?.lessonId) {
    workflow.bindLesson({
      lessonId: lesson.id,
      lessonTitle: lesson.title,
      versionId: version.id,
      versionNumber: version.versionNumber,
    });
  }
  void router.push({
    path: `/lessons/${lesson.id}/annotate`,
    query: {
      version: version.id,
      workflow: isWorkflowStep.value ? "1" : undefined,
    },
  });
}

function enterLockedLesson() {
  const run = workflow.activeRun;
  if (!run?.lessonId || !run.versionId) return;
  void router.push({
    path: `/lessons/${run.lessonId}/annotate`,
    query: { version: run.versionId, workflow: "1" },
  });
}
</script>

<template>
  <main class="review-entry">
    <AppPageHeader title="智能评价" description="对教案进行多维评价、问题诊断与详细批注。">
      <template #actions>
        <button type="button" class="v2-button v2-button--secondary" @click="openBatch">批量与对比</button>
      </template>
    </AppPageHeader>

    <template v-if="workflowHasLesson">
      <LessonSelectorBar
        :initial-lesson-id="workflow.activeRun?.lessonId"
        :initial-version-id="workflow.activeRun?.versionId"
        :show-tools="false"
        locked
      />
      <div class="locked-actions">
        <p>当前工作流已经确定教案，后续步骤不会重新选择版本。</p>
        <button type="button" class="v2-button v2-button--primary" @click="enterLockedLesson">进入智能评价</button>
      </div>
    </template>

    <LessonSelectorBar
      v-else
      :show-tools="false"
      action-label="确认使用此教案"
      @action="confirmLesson"
    />
  </main>
</template>

<style scoped>
.review-entry{display:grid;gap:0;color:var(--color-text)}.locked-actions{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-top:-10px;padding:16px 18px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff}.locked-actions p{margin:0;color:var(--color-text-secondary);font-size:13px}.locked-actions button{flex:none}@media(max-width:680px){.locked-actions{align-items:stretch;flex-direction:column}.locked-actions button{width:100%}}
</style>
