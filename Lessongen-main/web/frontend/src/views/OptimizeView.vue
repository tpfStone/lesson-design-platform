<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ApiProblem, createOptimize, makeIdempotencyKey } from "../api/client";
import { useDraftStore } from "../stores/draft";
import LessonFields from "../components/LessonFields.vue";
import ChipInput from "../components/ChipInput.vue";
import FormWayfinder from "../components/FormWayfinder.vue";

const router = useRouter();
const drafts = useDraftStore();
const file = ref<File | null>(null);
const fileError = ref("");
const digest = ref("");
const dragging = ref(false);
const checking = ref(false);
const submitting = ref(false);
const error = ref("");
const key = ref("");
type FieldName =
  "subject" | "grade" | "topic" | "durationMinutes" | "classSize";
type PendingChipInput = { commitPending: () => void };
const invalidField = ref<FieldName | null>(null);
const lessonFields = ref<PendingChipInput | null>(null);
const optimizationFocusInput = ref<PendingChipInput | null>(null);
const mustPreserveInput = ref<PendingChipInput | null>(null);
const draftNote = ref(
  "表单信息仅暂存在当前浏览器会话；Word 文件刷新后需重新选择。",
);
let submitted = false;
let selection = 0;
function fieldIsValid(field: FieldName) {
  if (field === "durationMinutes") {
    const value = drafts.optimize.durationMinutes;
    return Number.isInteger(value) && value >= 5 && value <= 240;
  }
  if (field === "classSize") {
    const value: unknown = drafts.optimize.classSize;
    return (
      value == null ||
      value === "" ||
      (typeof value === "number" &&
        Number.isInteger(value) &&
        value >= 1 &&
        value <= 200)
    );
  }
  return !!drafts.optimize[field].trim();
}
watch(
  () => drafts.optimize,
  () => {
    if (submitted) return;
    draftNote.value = drafts.persistOptimize()
      ? "表单草稿已保存在当前浏览器会话；Word 文件刷新后需重新选择。"
      : "本机草稿保存失败，请勿关闭页面；Word 文件不会自动保留。";
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
    id: "optimize-upload",
    label: "上传原稿",
    state: checking.value ? "检查中" : file.value ? "已选择" : "必选 Word",
    complete: !!file.value,
  },
  {
    id: "optimize-basic",
    label: "基本信息",
    state:
      drafts.optimize.subject.trim() &&
      drafts.optimize.grade.trim() &&
      drafts.optimize.topic.trim()
        ? "必填已齐"
        : "3 项必填",
    complete: !!(
      drafts.optimize.subject.trim() &&
      drafts.optimize.grade.trim() &&
      drafts.optimize.topic.trim()
    ),
  },
  {
    id: "optimize-evidence",
    label: "教学依据",
    state:
      drafts.optimize.curriculumStandards?.length ||
      drafts.optimize.textbookContent?.trim()
        ? "已补充"
        : "可选",
  },
  {
    id: "optimize-learning",
    label: "学习设计",
    state:
      drafts.optimize.learningObjectives?.length ||
      drafts.optimize.studentProfile?.trim()
        ? "已补充"
        : "可选",
  },
  { id: "optimize-advanced", label: "风格要求", state: "可选" },
  {
    id: "optimize-boundary",
    label: "优化边界",
    state:
      drafts.optimize.optimizationFocus?.length ||
      drafts.optimize.mustPreserveContent?.length
        ? "已补充"
        : "可选",
  },
]);
const size = computed(() =>
  file.value ? `${(file.value.size / 1024 / 1024).toFixed(2)} MiB` : "",
);
async function choose(candidate?: File) {
  const currentSelection = ++selection;
  fileError.value = "";
  error.value = "";
  digest.value = "";
  file.value = null;
  key.value = "";
  if (!candidate) {
    checking.value = false;
    return;
  }
  checking.value = true;
  try {
    if (!candidate.name.toLowerCase().endsWith(".docx")) {
      fileError.value = "只支持 .docx 格式。";
      return;
    }
    if (candidate.size > 20 * 1024 * 1024) {
      fileError.value = "文件不能超过 20 MiB。";
      return;
    }
    const magic = new Uint8Array(await candidate.slice(0, 4).arrayBuffer());
    if (currentSelection !== selection) return;
    if (
      magic.length !== 4 ||
      magic[0] !== 0x50 ||
      magic[1] !== 0x4b ||
      magic[2] !== 0x03 ||
      magic[3] !== 0x04
    ) {
      fileError.value = "文件不是有效的 OOXML Word 文档。";
      return;
    }
    const hash = await crypto.subtle.digest(
      "SHA-256",
      await candidate.arrayBuffer(),
    );
    if (currentSelection !== selection) return;
    digest.value = Array.from(new Uint8Array(hash))
      .map((value) => value.toString(16).padStart(2, "0"))
      .join("");
    file.value = candidate;
  } catch {
    if (currentSelection === selection)
      fileError.value = "无法完成本机文件检查，请重新选择 Word。";
  } finally {
    if (currentSelection === selection) checking.value = false;
  }
}
function drop(event: DragEvent) {
  dragging.value = false;
  void choose(event.dataTransfer?.files?.[0]);
}
async function focusRequired() {
  if (!file.value) {
    fileError.value ||= checking.value
      ? "请等待 Word 文件检查完成。"
      : "请先选择可读取的 Word 教案。";
    await nextTick();
    document.getElementById("optimize-file")?.focus();
    return true;
  }
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
  document.getElementById(`optimize-${invalid}`)?.focus();
  return true;
}
async function submit() {
  lessonFields.value?.commitPending();
  optimizationFocusInput.value?.commitPending();
  mustPreserveInput.value?.commitPending();
  error.value = "";
  if ((await focusRequired()) || !file.value) return;
  invalidField.value = null;
  submitting.value = true;
  key.value ||= makeIdempotencyKey();
  try {
    const accepted = await createOptimize(
      drafts.optimize,
      file.value,
      key.value,
    );
    submitted = true;
    drafts.clearOptimize();
    await router.push(`/jobs/${accepted.jobId}`);
  } catch (reason) {
    error.value =
      reason instanceof ApiProblem ? reason.message : "提交失败，请稍后重试。";
  } finally {
    submitting.value = false;
  }
}
</script>
<template>
  <div class="page-intro compact">
    <span class="eyebrow">CREATE · OPTIMIZE</span>
    <h1>让原教案变得更可教</h1>
    <p>
      可上传其他来源的 .docx
      教案，不要求使用本系统模板。原稿只读保存；导入后审查、改写，
      最终展示实际修改前后对比。若没有可交付的内容变化，页面会如实标明。
    </p>
  </div>
  <FormWayfinder
    :items="sections"
    :note="submitting ? '正在上传原稿并创建任务，请勿重复操作。' : draftNote"
  />
  <form
    class="lesson-form surface optimize-form"
    novalidate
    @submit.prevent="submit"
  >
    <section id="optimize-upload" class="upload-section" :aria-busy="checking">
      <div class="form-section-title">
        <span>00</span>
        <div>
          <h2>选择原教案</h2>
          <p>
            仅支持含可读取文字的 .docx，最大 20 MiB；扫描图片中的文字暂不识别。
          </p>
        </div>
      </div>
      <label
        class="drop-zone"
        :class="{ dragging, selected: file }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="drop"
      >
        <input
          id="optimize-file"
          type="file"
          :aria-invalid="fileError ? true : undefined"
          :aria-describedby="fileError ? 'optimize-file-error' : undefined"
          accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          @change="choose(($event.target as HTMLInputElement).files?.[0])"
        />
        <span class="upload-icon" aria-hidden="true">↥</span>
        <template v-if="checking"
          ><strong>正在检查 Word 文件…</strong>
          <p>计算文件摘要并检查基础格式，请稍候。</p></template
        >
        <template v-else-if="file"
          ><strong>{{ file.name }}</strong>
          <p>{{ size }} · SHA-256 已计算</p>
          <code
            >{{ digest.slice(0, 18) }}…{{ digest.slice(-8) }}</code
          ></template
        >
        <template v-else
          ><strong>拖放 Word 教案到这里</strong>
          <p>或点击选择本机文件</p></template
        >
      </label>
      <p
        v-if="fileError"
        id="optimize-file-error"
        class="field-error"
        role="alert"
      >
        {{ fileError }}
      </p>
      <div class="format-notice">
        <strong>关于排版</strong
        ><span
          >系统按段落与表格顺序提取原稿，再分段识别教学内容；请核对导入警告和改写对比。输出采用统一教案模板，不复刻原排版。</span
        >
      </div>
    </section>
    <LessonFields
      ref="lessonFields"
      v-model="drafts.optimize"
      id-prefix="optimize"
      :invalid-field="invalidField"
      compact
    />
    <section id="optimize-boundary" class="form-section">
      <div class="form-section-title">
        <span>05</span>
        <div>
          <h2>优化边界</h2>
          <p>明确最想改好的部分，以及不能被改写掉的内容。</p>
        </div>
      </div>
      <div class="field-grid two">
        <label
          ><span>优化重点</span
          ><ChipInput
            ref="optimizationFocusInput"
            v-model="drafts.optimize.optimizationFocus!"
            aria-label="优化重点"
            placeholder="如：增强课堂提问层次"
        /></label>
        <label
          ><span>必须保留</span
          ><ChipInput
            ref="mustPreserveInput"
            v-model="drafts.optimize.mustPreserveContent!"
            aria-label="必须保留"
            placeholder="如：保留原实验步骤与数据"
        /></label>
      </div>
    </section>
    <div v-if="error" id="optimize-form-error" class="form-error" role="alert">
      {{ error }}
    </div>
    <div class="submit-row">
      <p>
        <strong>原文件将只读保存</strong
        ><span>用户填写的科目、年级、课题和课时优先于模型推断。</span>
      </p>
      <button
        class="primary-button"
        type="submit"
        :disabled="submitting || checking"
      >
        <span v-if="submitting" class="button-spinner" />{{
          checking
            ? "正在检查文件…"
            : submitting
              ? "正在上传并创建…"
              : "开始优化教案"
        }}
      </button>
    </div>
  </form>
</template>
