<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { createGenerate, makeIdempotencyKey, ApiProblem } from "../api/client";
import { useDraftStore } from "../stores/draft";
import LessonFields from "../components/LessonFields.vue";
import EvidenceMeter from "../components/EvidenceMeter.vue";
import FormWayfinder from "../components/FormWayfinder.vue";
import AppPageHeader from "../components/AppPageHeader.vue";

const router = useRouter();
const drafts = useDraftStore();
const submitting = ref(false);
const error = ref("");
const key = ref("");
type FieldName =
  "subject" | "grade" | "topic" | "durationMinutes" | "classSize";
const invalidField = ref<FieldName | null>(null);
const lessonFields = ref<{ commitPending: () => void } | null>(null);
const draftNote = ref(
  "表单信息仅暂存在当前浏览器会话；提交后任务会在后台运行。",
);
let submitted = false;
const complete = computed(
  () =>
    drafts.generate.subject.trim() &&
    drafts.generate.grade.trim() &&
    drafts.generate.topic.trim(),
);
function fieldIsValid(field: FieldName) {
  if (field === "durationMinutes") {
    const value = drafts.generate.durationMinutes;
    return Number.isInteger(value) && value >= 5 && value <= 240;
  }
  if (field === "classSize") {
    const value: unknown = drafts.generate.classSize;
    return (
      value == null ||
      value === "" ||
      (typeof value === "number" &&
        Number.isInteger(value) &&
        value >= 1 &&
        value <= 200)
    );
  }
  return !!drafts.generate[field].trim();
}
watch(
  () => drafts.generate,
  () => {
    if (submitted) return;
    draftNote.value = drafts.persistGenerate()
      ? "草稿已保存在当前浏览器会话；提交后任务会在后台运行。"
      : "本机草稿保存失败，请勿关闭页面；提交仍可继续。";
    key.value = "";
    if (invalidField.value && fieldIsValid(invalidField.value)) {
      invalidField.value = null;
      error.value = "";
    }
  },
  { deep: true },
);
const sections = computed(() => [
  {
    id: "generate-basic",
    label: "基本信息",
    state: complete.value ? "必填已齐" : "3 项必填",
    complete: !!complete.value,
  },
  {
    id: "generate-evidence",
    label: "教学依据",
    state:
      drafts.generate.curriculumStandards?.length ||
      drafts.generate.textbookContent?.trim() ||
      drafts.generate.textbookVersion?.trim()
        ? "已补充"
        : "可选",
  },
  {
    id: "generate-learning",
    label: "学习设计",
    state:
      drafts.generate.learningObjectives?.length ||
      drafts.generate.studentProfile?.trim() ||
      drafts.generate.availableResources?.length
        ? "已补充"
        : "可选",
  },
  { id: "generate-advanced", label: "风格要求", state: "可选" },
]);
async function focusRequired() {
  const invalid = (
    ["subject", "grade", "topic", "durationMinutes", "classSize"] as const
  ).find((field) => !fieldIsValid(field));
  if (!invalid) return false;
  invalidField.value = invalid;
  error.value =
    invalid === "durationMinutes"
      ? "课时请输入 5–240 分钟的整数。"
      : invalid === "classSize"
        ? "班级人数请输入 1–200 的整数，或留空。"
        : "请补齐基本信息中的必填项。";
  await nextTick();
  document.getElementById(`generate-${invalid}`)?.focus();
  return true;
}
async function submit() {
  lessonFields.value?.commitPending();
  error.value = "";
  if (await focusRequired()) return;
  invalidField.value = null;
  submitting.value = true;
  key.value ||= makeIdempotencyKey();
  try {
    const accepted = await createGenerate(drafts.generate, key.value);
    submitted = true;
    drafts.clearGenerate();
    const inWorkflow = new URLSearchParams(window.location.search).get("workflow") === "1";
    await router.push({ path: `/jobs/${accepted.jobId}`, query: inWorkflow ? { workflow: "1" } : {} });
  } catch (reason) {
    error.value =
      reason instanceof ApiProblem ? reason.message : "提交失败，请稍后重试。";
  } finally {
    submitting.value = false;
  }
}
</script>
<template>
  <main class="generate-workspace">
  <AppPageHeader
    title="教案生成"
    description="填写基本信息与教学依据，生成一份可继续修改和使用的教案。三项必填信息齐全后即可开始。"
  />
  <FormWayfinder
    :items="sections"
    :note="submitting ? '正在提交任务，请勿重复操作。' : draftNote"
  />
  <div class="form-layout">
    <EvidenceMeter class="mobile-evidence" :value="drafts.generate" compact />
    <form class="lesson-form surface" novalidate @submit.prevent="submit">
      <LessonFields
        ref="lessonFields"
        v-model="drafts.generate"
        id-prefix="generate"
        :invalid-field="invalidField"
        compact
      />
      <div
        v-if="error"
        id="generate-form-error"
        class="form-error"
        role="alert"
      >
        {{ error }}
      </div>
      <div class="submit-row">
        <p>
          <strong>准备好后开始生成</strong>
          <span>任务会在后台持续运行，离开页面不会中断。</span>
        </p>
        <button class="v2-button v2-button--primary" type="submit" :disabled="submitting">
          <span v-if="submitting" class="button-spinner" />{{
            submitting ? "正在创建任务…" : "开始生成教案"
          }}
        </button>
      </div>
    </form>
    <EvidenceMeter class="desktop-evidence" :value="drafts.generate" />
  </div>
  </main>
</template>

<style scoped>
.generate-workspace { display:grid; gap:var(--space-6); color:var(--color-text); }
.generate-workspace :deep(.wayfinder-wrap) { top:0; z-index:25; margin-inline:-1px; padding:10px 12px 8px; border:1px solid #dce5f2; border-radius:0 0 12px 12px; background:#fff; box-shadow:0 8px 20px rgba(23,43,72,.07); backdrop-filter:none; }
.generate-workspace :deep(.lesson-form),.generate-workspace :deep(.evidence-card) { border-color:#dce5f2; background:#fff; }
.generate-workspace :deep(.evidence-card) { background:#f5f8ff; }
.generate-workspace :deep(.lesson-form input),.generate-workspace :deep(.lesson-form textarea),.generate-workspace :deep(.lesson-form select),.generate-workspace :deep(.chip-editor) { border-color:#cbd8ea; }
.generate-workspace :deep(.form-section),.generate-workspace :deep(.advanced-fields) { border-color:#e4ebf6; }
.generate-workspace :deep(.form-section-title > span),.generate-workspace :deep(.advanced-fields summary > span),.generate-workspace :deep(.chip),.generate-workspace :deep(.evidence-count) { color:var(--color-primary); background:var(--color-primary-soft); }
.generate-workspace :deep(.chip-add button) { color:var(--color-primary); background:#edf4ff; }
.generate-workspace :deep(.lesson-form input:hover),.generate-workspace :deep(.lesson-form textarea:hover),.generate-workspace :deep(.lesson-form select:hover),.generate-workspace :deep(.chip-editor:hover) { border-color:#9eb7e5; }
.generate-workspace :deep(.lesson-form input:focus),.generate-workspace :deep(.lesson-form textarea:focus),.generate-workspace :deep(.lesson-form select:focus),.generate-workspace :deep(.chip-add input:focus) { border-color:var(--color-primary); box-shadow:0 0 0 3px var(--color-primary-soft); }
.generate-workspace :deep(.advanced-fields summary > i),.generate-workspace :deep(.eyebrow),.generate-workspace :deep(.ready span) { color:var(--color-primary); }
.generate-workspace :deep(.meter i) { background:var(--color-primary); }
.generate-workspace :deep(.submit-row) { background:#f5f8ff; border-color:#dce5f2; }
@media(max-width:760px) { .generate-workspace :deep(.wayfinder-wrap) { top:0; } }
</style>
