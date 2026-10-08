<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import axios from "axios";
import AppPageHeader from "../components/AppPageHeader.vue";
import BaseCard from "../components/BaseCard.vue";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import LessonSelectorBar, { type LessonOption, type VersionOption } from "../components/LessonSelectorBar.vue";
import { useWorkflowStore } from "../stores/workflow";

interface LessonDetail {
  lesson: {
    id: string;
    title: string;
    subject: string;
    grade: string;
    topic: string;
    durationMinutes: number | null;
    currentVersionId: string;
  };
  versions: Array<{ id: string; versionNumber: number; content: string; sourceModule?: string }>;
}
interface OptimizeHistory {
  jobId: string;
  lessonId: string;
  sourceVersionId: string;
  status: string;
  createdAt: string;
}
interface OptimizeDraft {
  subject: string;
  grade: string;
  topic: string;
  duration: number;
  courseInformation: string;
  textbookVersion: string;
  textbookContent: string;
  curriculumStandardsText: string;
  learningObjectivesText: string;
  studentProfile: string;
  classSize: number | null;
  availableResourcesText: string;
  additionalRequirements: string;
  lessonStyle: string;
  detailLevel: string;
  focusText: string;
  preserveText: string;
}

const route = useRoute();
const router = useRouter();
const workflow = useWorkflowStore();

const lessonId = computed(() => typeof route.query.lessonId === "string" ? route.query.lessonId : "");
const requestedVersionId = computed(() => typeof route.query.versionId === "string" ? route.query.versionId : "");
const isWorkflowStep = computed(() => Boolean(
  route.query.workflow === "1" && workflow.activeRun && !workflow.isFinished && workflow.currentStep?.id === "F2",
));
const lockedByWorkflow = computed(() => Boolean(
  isWorkflowStep.value && workflow.activeRun?.lessonId && workflow.activeRun?.versionId,
));
const isLaterWorkflowStep = computed(() => Boolean(
  isWorkflowStep.value && (workflow.activeRun?.currentIndex ?? 0) > 0,
));
const missingWorkflowLesson = computed(() => Boolean(
  isLaterWorkflowStep.value && !lockedByWorkflow.value,
));

const detail = ref<LessonDetail | null>(null);
const error = ref("");
const busy = ref(false);
const loading = ref(false);
const requestKey = ref(crypto.randomUUID());
const previous = ref<OptimizeHistory[]>([]);
const subject = ref("");
const grade = ref("");
const topic = ref("");
const duration = ref(45);
const courseInformation = ref("");
const textbookVersion = ref("");
const textbookContent = ref("");
const curriculumStandardsText = ref("");
const learningObjectivesText = ref("");
const studentProfile = ref("");
const classSize = ref<number | null>(null);
const availableResourcesText = ref("");
const additionalRequirements = ref("");
const lessonStyle = ref("choose_the_best_fit_for_this_topic");
const detailLevel = ref("showcase");
const focusText = ref("");
const preserveText = ref("");
const draftSavedAt = ref("");
const formTouched = ref(false);
const hydrating = ref(false);
const switchDialogOpen = ref(false);
const pendingSelection = ref<{ lesson: LessonOption; version: VersionOption } | null>(null);

const selected = computed(() => detail.value?.versions.find(v => v.id === requestedVersionId.value) || null);
const isCurrentVersion = computed(() => Boolean(selected.value && detail.value?.lesson.currentVersionId === selected.value.id));
const sourceVersionLabel = computed(() => selected.value ? `V${selected.value.versionNumber}` : "未选择");

function draftKey(id = lessonId.value, versionId = requestedVersionId.value) {
  return id && versionId ? `f2-optimize-settings-v2:${id}:${versionId}` : "";
}
function readDraft(key: string): OptimizeDraft | null {
  if (!key) return null;
  try { return JSON.parse(sessionStorage.getItem(key) || "") as OptimizeDraft; }
  catch { return null; }
}
function saveDraft() {
  if (hydrating.value || !detail.value || !draftKey()) return;
  const payload: OptimizeDraft = {
    subject: subject.value,
    grade: grade.value,
    topic: topic.value,
    duration: duration.value,
    courseInformation: courseInformation.value,
    textbookVersion: textbookVersion.value,
    textbookContent: textbookContent.value,
    curriculumStandardsText: curriculumStandardsText.value,
    learningObjectivesText: learningObjectivesText.value,
    studentProfile: studentProfile.value,
    classSize: classSize.value,
    availableResourcesText: availableResourcesText.value,
    additionalRequirements: additionalRequirements.value,
    lessonStyle: lessonStyle.value,
    detailLevel: detailLevel.value,
    focusText: focusText.value,
    preserveText: preserveText.value,
  };
  try {
    sessionStorage.setItem(draftKey(), JSON.stringify(payload));
    draftSavedAt.value = "设置已自动保存";
  } catch {
    draftSavedAt.value = "当前浏览器无法保存设置";
  }
  formTouched.value = true;
}
function parseLines(value: string) {
  return value.split(/\r?\n/).map(item => item.trim()).filter(Boolean);
}
function friendlyError(reason: unknown, fallback: string) {
  if (!axios.isAxiosError(reason)) return fallback;
  const detailText = (reason.response?.data as { detail?: string } | undefined)?.detail;
  return detailText || fallback;
}

async function loadDetail(id: string, versionId: string) {
  if (!id || !versionId) {
    detail.value = null;
    previous.value = [];
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const next = (await axios.get<LessonDetail>(`/api/platform/lessons/${encodeURIComponent(id)}`)).data;
    detail.value = next;
    const version = next.versions.find(item => item.id === versionId);
    if (!version) {
      error.value = "没有找到所选教案版本，请重新选择。";
      return;
    }

    hydrating.value = true;
    const saved = readDraft(draftKey(id, versionId));
    subject.value = saved?.subject ?? next.lesson.subject ?? "";
    grade.value = saved?.grade ?? next.lesson.grade ?? "";
    topic.value = saved?.topic ?? next.lesson.topic ?? next.lesson.title;
    duration.value = saved?.duration ?? next.lesson.durationMinutes ?? 45;
    courseInformation.value = saved?.courseInformation ?? "";
    textbookVersion.value = saved?.textbookVersion ?? "";
    textbookContent.value = saved?.textbookContent ?? "";
    curriculumStandardsText.value = saved?.curriculumStandardsText ?? "";
    learningObjectivesText.value = saved?.learningObjectivesText ?? "";
    studentProfile.value = saved?.studentProfile ?? "";
    classSize.value = saved?.classSize ?? null;
    availableResourcesText.value = saved?.availableResourcesText ?? "";
    additionalRequirements.value = saved?.additionalRequirements ?? "";
    lessonStyle.value = saved?.lessonStyle ?? "choose_the_best_fit_for_this_topic";
    detailLevel.value = saved?.detailLevel ?? "showcase";
    focusText.value = saved?.focusText ?? "";
    preserveText.value = saved?.preserveText ?? "";
    formTouched.value = false;
    draftSavedAt.value = saved ? "已恢复上次填写的设置" : "已自动填充教案基本信息";
    requestKey.value = crypto.randomUUID();
    hydrating.value = false;

    try {
      previous.value = (await axios.get<OptimizeHistory[]>("/api/platform/optimizations")).data
        .filter(item => item.lessonId === id && item.sourceVersionId === versionId);
    } catch {
      previous.value = [];
    }
  } catch (reason) {
    error.value = friendlyError(reason, "暂时无法读取教案，请稍后重试。");
  } finally {
    hydrating.value = false;
    loading.value = false;
  }
}

async function applySelection(lesson: LessonOption, version: VersionOption) {
  if (isWorkflowStep.value && !workflow.activeRun?.lessonId) {
    workflow.bindLesson({
      lessonId: lesson.id,
      lessonTitle: lesson.title,
      versionId: version.id,
      versionNumber: version.versionNumber,
    });
  }
  const query: Record<string, string> = { lessonId: lesson.id, versionId: version.id };
  if (isWorkflowStep.value) query.workflow = "1";
  await router.replace({ path: "/optimize-lesson", query });
}

function confirmLesson(lesson: LessonOption, version: VersionOption) {
  const changing = Boolean(
    lessonId.value && requestedVersionId.value &&
    (lesson.id !== lessonId.value || version.id !== requestedVersionId.value),
  );
  if (changing && formTouched.value) {
    pendingSelection.value = { lesson, version };
    switchDialogOpen.value = true;
    return;
  }
  void applySelection(lesson, version);
}

function cancelSwitch() {
  switchDialogOpen.value = false;
  pendingSelection.value = null;
}
function confirmSwitch() {
  const pending = pendingSelection.value;
  cancelSwitch();
  if (pending) void applySelection(pending.lesson, pending.version);
}

async function start() {
  if (!detail.value || !selected.value || busy.value) return;
  if (!isCurrentVersion.value) {
    error.value = "设计修改只能基于当前最新版本开始。历史版本仍可在“我的教案”中查看。";
    return;
  }
  if (!subject.value.trim() || !grade.value.trim() || !topic.value.trim() || duration.value < 5 || duration.value > 240) {
    error.value = "请补齐学科、年级、课题，并确认课时在 5–240 分钟之间。";
    return;
  }
  const normalizedClassSize = classSize.value === null || String(classSize.value) === "" ? null : Number(classSize.value);
  if (normalizedClassSize !== null && (!Number.isInteger(normalizedClassSize) || normalizedClassSize < 1 || normalizedClassSize > 200)) {
    error.value = "班级人数请填写 1–200 之间的整数，或留空。";
    return;
  }
  const lists = [
    { label: "课程标准", items: parseLines(curriculumStandardsText.value), max: 50, itemMax: 1000 },
    { label: "预设学习目标", items: parseLines(learningObjectivesText.value), max: 20, itemMax: 1000 },
    { label: "可用资源", items: parseLines(availableResourcesText.value), max: 50, itemMax: 500 },
    { label: "优化重点", items: parseLines(focusText.value), max: 20, itemMax: 1000 },
    { label: "必须保留", items: parseLines(preserveText.value), max: 20, itemMax: 2000 },
  ];
  const invalid = lists.find(group => group.items.length > group.max || group.items.some(item => item.length > group.itemMax));
  if (invalid) {
    error.value = `${invalid.label}最多 ${invalid.max} 项，每项不超过 ${invalid.itemMax} 字。`;
    return;
  }

  busy.value = true;
  error.value = "";
  try {
    const accepted = (await axios.post<{ jobId: string }>(
      `/api/platform/lessons/${encodeURIComponent(lessonId.value)}/optimizations`,
      {
        versionId: selected.value.id,
        requestKey: requestKey.value,
        subject: subject.value.trim(),
        grade: grade.value.trim(),
        topic: topic.value.trim(),
        durationMinutes: duration.value,
        courseInformation: courseInformation.value.trim(),
        textbookVersion: textbookVersion.value.trim(),
        textbookContent: textbookContent.value.trim(),
        curriculumStandards: parseLines(curriculumStandardsText.value),
        learningObjectives: parseLines(learningObjectivesText.value),
        studentProfile: studentProfile.value.trim(),
        classSize: normalizedClassSize,
        availableResources: parseLines(availableResourcesText.value),
        additionalRequirements: additionalRequirements.value.trim(),
        lessonStyle: lessonStyle.value,
        detailLevel: detailLevel.value,
        optimizationFocus: parseLines(focusText.value),
        mustPreserveContent: parseLines(preserveText.value),
      },
    )).data;

    const query: Record<string, string> = { lessonId: lessonId.value };
    if (isWorkflowStep.value) query.workflow = "1";
    const destination = `/jobs/${accepted.jobId}?lessonId=${encodeURIComponent(lessonId.value)}${isWorkflowStep.value ? "&workflow=1" : ""}`;
    if (isWorkflowStep.value) workflow.rememberPath("F2", destination);
    await router.push({ path: `/jobs/${accepted.jobId}`, query });
  } catch (reason) {
    error.value = friendlyError(reason, "暂时无法开始设计修改，请稍后重试。");
  } finally {
    busy.value = false;
  }
}

watch([lessonId, requestedVersionId], ([id, version]) => {
  void loadDetail(id, version);
}, { immediate: true });
watch([subject, grade, topic, duration, courseInformation, textbookVersion, textbookContent,
  curriculumStandardsText, learningObjectivesText, studentProfile, classSize,
  availableResourcesText, additionalRequirements, lessonStyle, detailLevel,
  focusText, preserveText], saveDraft);
</script>

<template>
  <main class="platform-optimize">
    <AppPageHeader
      title="设计修改"
      description="基于当前教案版本补充教学背景、明确优化重点和必须保留的内容，再开始本次修改。"
    >
      <template #actions>
        <span v-if="detail" class="autosave-note">✓ {{ draftSavedAt }}</span>
      </template>
    </AppPageHeader>

    <LessonSelectorBar
      v-if="!missingWorkflowLesson"
      :initial-lesson-id="lockedByWorkflow ? workflow.activeRun?.lessonId : lessonId"
      :initial-version-id="lockedByWorkflow ? workflow.activeRun?.versionId : requestedVersionId"
      :locked="lockedByWorkflow"
      :show-tools="false"
      action-label="确认使用此教案"
      @action="confirmLesson"
    />

    <p v-if="error" class="page-error" role="alert">{{ error }}</p>

    <BaseCard v-if="missingWorkflowLesson" class="intro-card workflow-binding-error">
      <h2>暂时无法继续当前工作流</h2>
      <p>这个设计修改步骤应当继承第一步已经确定的教案，但当前工作流没有找到可继承的教案版本。为避免后续步骤误用其他教案，这里不会重新开放教案选择。</p>
      <RouterLink class="v2-button v2-button--secondary" to="/workflows">返回工作流</RouterLink>
    </BaseCard>

    <BaseCard v-else-if="!detail && !loading" class="intro-card">
      <h2>先确定本次要修改的教案</h2>
      <p>从上方选择已有教案和版本，或点击“上传教案”导入 DOCX。确认后才会进入优化设置。</p>
    </BaseCard>

    <div v-else-if="loading" class="loading-card v2-card" role="status">正在读取当前教案与版本……</div>

    <template v-else-if="detail && selected">
      <BaseCard class="lesson-context">
        <div>
          <p class="section-kicker">当前修改对象</p>
          <h2>{{ detail.lesson.title }}</h2>
          <p>{{ sourceVersionLabel }} · {{ detail.lesson.subject || '未指定学科' }} · {{ detail.lesson.grade || '未指定年级' }}</p>
        </div>
        <span class="v2-status" :class="isCurrentVersion ? 'v2-status--complete' : 'v2-status--attention'">
          {{ isCurrentVersion ? '当前最新版本' : '历史版本' }}
        </span>
      </BaseCard>

      <BaseCard v-if="previous.length" class="prior-jobs">
        <div>
          <p class="section-kicker">已有任务</p>
          <h2>这个版本已有设计修改记录</h2>
          <p>打开已有任务不会再次调用模型；只有重新点击“开始设计修改”才会创建新任务。</p>
        </div>
        <div class="prior-links">
          <RouterLink
            v-for="item in previous.slice(0, 3)"
            :key="item.jobId"
            :to="{ path: `/jobs/${item.jobId}`, query: { lessonId, ...(isWorkflowStep ? { workflow: '1' } : {}) } }"
          >{{ new Date(item.createdAt).toLocaleString('zh-CN') }} · {{ item.status }} →</RouterLink>
        </div>
      </BaseCard>

      <section class="settings-stack" aria-label="优化设置">
        <BaseCard class="settings-card">
          <header class="settings-heading"><span>01</span><div><h2>基本信息</h2><p>已从当前教案自动填充，可按本次修改需要调整。</p></div></header>
          <div class="field-grid">
            <label><span>学科（必填）</span><input v-model="subject" maxlength="64" required /></label>
            <label><span>年级（必填）</span><input v-model="grade" maxlength="64" required /></label>
            <label><span>课题（必填）</span><input v-model="topic" maxlength="255" required /></label>
            <label><span>课时（分钟）</span><input v-model.number="duration" type="number" min="5" max="240" /></label>
            <label class="wide-field"><span>课程信息</span><textarea v-model="courseInformation" rows="2" maxlength="4000" /></label>
          </div>
        </BaseCard>

        <BaseCard class="settings-card">
          <header class="settings-heading"><span>02</span><div><h2>教学依据</h2></div></header>
          <div class="field-grid">
            <label><span>教材版本</span><input v-model="textbookVersion" maxlength="255" placeholder="如：人教版" /></label>
            <label class="wide-field"><span>课程标准（一行一项）</span><textarea v-model="curriculumStandardsText" rows="3" maxlength="50000" /></label>
            <label class="wide-field"><span>教材内容摘要</span><textarea v-model="textbookContent" rows="3" maxlength="30000" /></label>
          </div>
        </BaseCard>

        <BaseCard class="settings-card">
          <header class="settings-heading"><span>03</span><div><h2>学习设计</h2></div></header>
          <div class="field-grid">
            <label class="wide-field"><span>预设学习目标（一行一项）</span><textarea v-model="learningObjectivesText" rows="3" maxlength="20000" /></label>
            <label class="wide-field"><span>学情描述</span><textarea v-model="studentProfile" rows="3" maxlength="8000" /></label>
            <label><span>班级人数</span><input v-model.number="classSize" type="number" min="1" max="200" placeholder="可留空" /></label>
            <label class="wide-field"><span>可用资源（一行一项）</span><textarea v-model="availableResourcesText" rows="3" maxlength="25000" /></label>
          </div>
        </BaseCard>

        <BaseCard class="settings-card">
          <header class="settings-heading"><span>04</span><div><h2>风格与高级要求</h2></div></header>
          <div class="field-grid">
            <label><span>教学设计取向</span><select v-model="lessonStyle">
              <option value="choose_the_best_fit_for_this_topic">根据课题自动选择</option>
              <option value="inquiry_through_cognitive_conflict">认知冲突探究</option>
              <option value="authentic_problem_driven">真实问题驱动</option>
              <option value="dialogue_and_discussion">对话与讨论</option>
              <option value="project_or_task_based">项目或任务驱动</option>
              <option value="close_reading_and_evidence">细读与证据推理</option>
            </select></label>
            <label><span>详细程度</span><select v-model="detailLevel">
              <option value="showcase">展示版</option><option value="standard">标准版</option>
            </select></label>
            <label class="wide-field"><span>其他要求</span><textarea v-model="additionalRequirements" rows="3" maxlength="8000" /></label>
          </div>
        </BaseCard>

        <BaseCard class="settings-card">
          <header class="settings-heading"><span>05</span><div><h2>优化关注点</h2><p>系统会参考当前版本已有的评价、推演与共析结果（如有）；你也可以补充这次特别希望加强的内容。</p></div></header>
          <label class="wide-field"><span>你还希望重点优化</span><textarea v-model="focusText" rows="5" maxlength="3000" placeholder="例如：增强课堂提问层次&#10;增加学生自主探究&#10;完善过程性评价（建议一行一项）" /></label>
        </BaseCard>

        <BaseCard class="settings-card">
          <header class="settings-heading"><span>06</span><div><h2>优化边界</h2><p>明确本次修改中必须保留的内容，避免重要设计被覆盖。</p></div></header>
          <label class="wide-field"><span>必须保留</span><textarea v-model="preserveText" rows="5" maxlength="4000" placeholder="例如：保留原实验步骤&#10;保留已有作业数据（建议一行一项）" /></label>
        </BaseCard>
      </section>

      <BaseCard class="start-card">
        <div>
          <p class="section-kicker">准备开始</p>
          <h2>基于 {{ sourceVersionLabel }} 进行设计修改</h2>
          <p v-if="!isCurrentVersion">当前选择的是历史版本。为避免覆盖最新修改，请切换到当前最新版本后再开始。</p>
          <p v-else>任务开始后会自动保存运行状态，你可以离开页面，稍后从“任务记录”继续查看。</p>
        </div>
        <button
          type="button"
          class="v2-button v2-button--primary"
          :disabled="busy || !isCurrentVersion"
          @click="start"
        >{{ busy ? '正在启动…' : '开始设计修改' }}</button>
      </BaseCard>
    </template>

    <ConfirmDialog
      :open="switchDialogOpen"
      title="切换教案或版本？"
      description="切换后，当前填写的教学背景和优化要求可能不再适用于新的版本。已填写内容仍会保存在当前浏览器中。"
      confirm-text="继续切换"
      @cancel="cancelSwitch"
      @confirm="confirmSwitch"
    />
  </main>
</template>

<style scoped>
.platform-optimize{display:grid;gap:var(--space-6);color:var(--color-text)}
.autosave-note{display:inline-flex;align-items:center;min-height:34px;padding:0 11px;border-radius:999px;color:var(--color-primary);background:var(--color-primary-soft);font-size:12px;font-weight:700}
.page-error{margin:0;padding:13px 15px;border:1px solid #f0c8cb;border-radius:var(--radius-md);color:var(--color-danger);background:var(--color-danger-soft);line-height:1.65}
.intro-card,.loading-card{padding:24px}.intro-card h2{margin:0 0 8px;font-size:20px}.intro-card p{margin:0;color:var(--color-text-secondary);line-height:1.75}.loading-card{color:var(--color-text-secondary)}
.lesson-context{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:22px}.lesson-context h2{margin:4px 0 8px;font-size:22px}.lesson-context p{margin:0;color:var(--color-text-secondary)}.section-kicker{margin:0!important;color:var(--color-primary)!important;font-size:12px!important;font-weight:700!important}
.prior-jobs{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;padding:22px}.prior-jobs h2{margin:5px 0 7px;font-size:19px}.prior-jobs p{margin:0;color:var(--color-text-secondary);line-height:1.65}.prior-links{display:grid;flex:none;gap:7px}.prior-links a{color:var(--color-primary);font-size:13px;font-weight:700}
.settings-stack{display:grid;gap:var(--space-4)}.settings-card{padding:24px}.settings-heading{display:flex;gap:14px;margin-bottom:20px}.settings-heading>span{width:34px;height:34px;display:grid;place-items:center;flex:none;border-radius:var(--radius-md);color:#fff;background:var(--color-primary);font-size:12px;font-weight:800}.settings-heading h2{margin:0;font-size:20px}.settings-heading p{margin:6px 0 0;color:var(--color-text-secondary);line-height:1.65;font-size:13px}
.field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.field-grid label,.wide-field{display:grid;gap:7px}.field-grid .wide-field{grid-column:1/-1}.field-grid label>span,.wide-field>span{color:var(--color-text-secondary);font-size:13px;font-weight:700}input,textarea,select{width:100%;padding:11px 12px;border:1px solid #cbd8eb;border-radius:var(--radius-md);color:var(--color-text);background:#fff;outline:none}input:focus,textarea:focus,select:focus{border-color:var(--color-primary);box-shadow:0 0 0 3px var(--color-primary-soft)}textarea{line-height:1.7;resize:vertical}
.start-card{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:24px}.start-card h2{margin:5px 0 8px;font-size:21px}.start-card p{margin:0;color:var(--color-text-secondary);line-height:1.65}.start-card .v2-button{flex:none;min-width:136px}
@media(max-width:760px){.lesson-context,.prior-jobs,.start-card{align-items:stretch;flex-direction:column}.prior-links{width:100%}.field-grid{grid-template-columns:1fr}.start-card .v2-button{width:100%}}
.workflow-binding-error{display:grid;justify-items:start;gap:10px}.workflow-binding-error h2,.workflow-binding-error p{margin:0}
</style>
