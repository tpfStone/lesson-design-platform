<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import AppPageHeader from "../components/AppPageHeader.vue";
import BaseCard from "../components/BaseCard.vue";
import { useWorkflowStore } from "../stores/workflow";

const router = useRouter();
const workflow = useWorkflowStore();

const isWorkflowStep = computed(
  () => Boolean(workflow.activeRun && !workflow.isFinished && workflow.currentStep?.id === "F2"),
);
const workflowHasLesson = computed(
  () => Boolean(isWorkflowStep.value && workflow.activeRun?.lessonId && workflow.activeRun?.versionId),
);
const isLaterWorkflowStep = computed(
  () => Boolean(isWorkflowStep.value && (workflow.activeRun?.currentIndex ?? 0) > 0),
);

function optimizeQuery() {
  if (!isWorkflowStep.value) return {};
  return workflowHasLesson.value
    ? {
        lessonId: workflow.activeRun!.lessonId,
        versionId: workflow.activeRun!.versionId,
        workflow: "1",
      }
    : { workflow: "1" };
}

function enterOptimize() {
  void router.push({ path: "/optimize-lesson", query: optimizeQuery() });
}

function enterGenerate() {
  void router.push({ path: "/create/generate", query: isWorkflowStep.value ? { workflow: "1" } : {} });
}

onMounted(() => {
  // A later F2 step already inherits the lesson/version bound by the first
  // workflow step.  It must skip the source-choice screen completely.
  if (isLaterWorkflowStep.value) {
    // Later workflow steps must never show the source-choice screen. In a
    // healthy workflow the lesson/version is already bound by step 1; if the
    // binding is unexpectedly missing, the optimization page will surface a
    // recovery message instead of allowing the teacher to pick a different
    // lesson and silently break workflow continuity.
    void router.replace({ path: "/optimize-lesson", query: optimizeQuery() });
    return;
  }

  // If the first F2 step has already bound a lesson (for example after a
  // refresh/back navigation), resume the optimization page instead of asking
  // the teacher to choose a source again.
  if (isWorkflowStep.value && workflowHasLesson.value) {
    void router.replace({ path: "/optimize-lesson", query: optimizeQuery() });
  }
});
</script>

<template>
  <main class="design-entry">
    <AppPageHeader
      title="设计修改"
      description="选择从已有教案开始优化，或从零生成一份新教案。具体教案在进入对应任务后再确定。"
    />

    <section class="choice-grid" aria-label="选择设计修改方式">
      <BaseCard as="article" class="choice-card">
        <div class="choice-icon" aria-hidden="true">文</div>
        <div class="choice-copy">
          <p class="choice-label">已有教案</p>
          <h2>选择 / 上传教案</h2>
          <p>从“我的教案”选择版本，或上传 DOCX，再进入教案优化设置。</p>
        </div>
        <button type="button" class="v2-button v2-button--primary" @click="enterOptimize">进入教案优化</button>
      </BaseCard>

      <BaseCard as="article" class="choice-card">
        <div class="choice-icon" aria-hidden="true">＋</div>
        <div class="choice-copy">
          <p class="choice-label">新教案</p>
          <h2>生成教案</h2>
          <p>填写学科、年级与教学主题，从零生成一份新的教学设计。</p>
        </div>
        <button type="button" class="v2-button v2-button--secondary" @click="enterGenerate">开始生成</button>
      </BaseCard>
    </section>

    <p v-if="isWorkflowStep" class="workflow-note">
      当前处于工作流中的“设计修改”。如果这是第一步，你将在下一页确定教案；后续步骤会自动继承这份教案及最新正式版本。
    </p>
  </main>
</template>

<style scoped>
.design-entry{display:grid;gap:var(--space-6);color:var(--color-text)}
.choice-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-5)}
.choice-card{min-height:244px;display:grid;grid-template-rows:auto 1fr auto;gap:18px;padding:28px}
.choice-icon{width:44px;height:44px;display:grid;place-items:center;border-radius:var(--radius-md);color:var(--color-primary);background:var(--color-primary-soft);font-weight:800}
.choice-label{margin:0 0 6px;color:var(--color-primary);font-size:12px;font-weight:700}
.choice-copy h2{margin:0;color:var(--color-text);font-size:22px}.choice-copy>p:last-child{margin:10px 0 0;color:var(--color-text-secondary);line-height:1.75}
.choice-card .v2-button{justify-self:start;min-width:132px}
.workflow-note{margin:0;padding:14px 16px;border:1px solid var(--color-primary-border);border-radius:var(--radius-md);color:var(--color-text-secondary);background:var(--color-primary-soft);font-size:13px;line-height:1.7}
@media(max-width:760px){.choice-grid{grid-template-columns:1fr}.choice-card{min-height:220px}}
</style>
