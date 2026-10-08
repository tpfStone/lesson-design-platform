<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import axios from "axios";
import AppPageHeader from "../components/AppPageHeader.vue";
import EmptyState from "../components/EmptyState.vue";
import LoadingState from "../components/LoadingState.vue";
import ResultDownloadPanel, { type DownloadFile } from "../components/ResultDownloadPanel.vue";
import ReviewRadarChart, { type RadarDimension } from "../components/ReviewRadarChart.vue";
import VersionBadge from "../components/VersionBadge.vue";
import { useWorkflowStore } from "../stores/workflow";

interface Version {
  id: string;
  versionNumber: number;
  sourceModule?: string;
  content: string;
}
interface Detail {
  lesson: {
    id: string;
    title: string;
    subject: string;
    grade: string;
    currentVersionId: string;
  };
  versions: Version[];
}
interface RunState {
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  error?: string;
}
interface Run {
  id: string;
  lessonId: string;
  versionId: string;
  versionNumber: number;
  createdAt: string;
  state: RunState | null;
}
interface Comment {
  "位置"?: string;
  "原文引用"?: string;
  "评价"?: string;
  "具体分析"?: string;
  "建议"?: string;
  "细化建议"?: string;
  "依据来源"?: string;
  "理论依据"?: string;
  "档位参照"?: string;
}
interface Item {
  "维度名称": string;
  "得分": number;
  "满分": number;
  "等级"?: string;
  "得分理由"?: string;
  "批注列表"?: Comment[];
}
interface Group {
  name: string;
  score: number;
  maximum: number;
  items: Item[];
}
interface Dimension extends RadarDimension {
  grade: string;
}
interface ResultFile { kind: string; name?: string; url?: string }
interface Result {
  summary?: string;
  rubric: {
    standard?: string;
    score: number;
    maximum: number;
    groups: Group[];
    dimensions?: Dimension[];
    gradingScale?: Record<string, string>;
  };
  artifacts?: Record<string, string>;
  files?: ResultFile[] | string[];
}

const route = useRoute();
const workflow = useWorkflowStore();
const id = computed(() => String(route.params.lessonId || ""));
const api = axios.create({ baseURL: "/api/platform/lessons", timeout: 20000 });

const detail = ref<Detail | null>(null);
const versionId = ref("");
const history = ref<Run[]>([]);
const active = ref<Run | null>(null);
const result = ref<Result | null>(null);
const busy = ref(false);
const error = ref("");
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;

const base = computed(() => `/${encodeURIComponent(id.value)}/annotations`);
const selectedVersion = computed(() => detail.value?.versions.find(version => version.id === versionId.value) || null);
const workflowMode = computed(() => route.query.workflow === "1" && Boolean(workflow.activeRun));
const evaluating = computed(() => active.value?.state?.status === "QUEUED" || active.value?.state?.status === "RUNNING");
const dimensions = computed<Dimension[]>(() => {
  if (result.value?.rubric.dimensions?.length) return result.value.rubric.dimensions;
  const fallback = result.value?.rubric.groups.flatMap(group => group.items.map(item => ({
    name: item["维度名称"], score: item["得分"], maximum: item["满分"], grade: item["等级"] || "",
  }))) || [];
  return fallback;
});
const detailByName = computed(() => {
  const map = new Map<string, Item>();
  for (const group of result.value?.rubric.groups || []) {
    for (const item of group.items || []) map.set(item["维度名称"], item);
  }
  return map;
});
const annotatedItems = computed(() => (result.value?.rubric.groups || []).flatMap(group => group.items || []).filter(item => (item["批注列表"] || []).length > 0));
const downloadFiles = computed<DownloadFile[]>(() => {
  if (!result.value || !active.value) return [];
  const available = new Set<string>();
  if (result.value.artifacts) Object.keys(result.value.artifacts).forEach(kind => available.add(kind));
  if (Array.isArray(result.value.files)) {
    for (const file of result.value.files) {
      if (typeof file === "string") available.add(file);
      else if (file?.kind) available.add(file.kind);
    }
  }
  const labels: Record<string, string> = {
    docx: "智能评价报告 Word",
    docx_annotated: "原教案批注 Word",
    pdf: "原教案批注 PDF",
  };
  return [...available]
    .filter(kind => Boolean(labels[kind]))
    .map(kind => ({ key: kind, label: labels[kind]!, href: fileUrl(kind) }));
});

function activeKey() { return `f1-active-annotation:${id.value}`; }
function describe(reason: unknown): string {
  if (axios.isAxiosError(reason)) {
    const status = reason.response?.status || 0;
    const body = reason.response?.data as { detail?: string } | undefined;
    if (status >= 500) return "智能评价服务暂时不可用，请稍后重试。";
    return body?.detail || "请求未完成，请检查当前教案后重试。";
  }
  return reason instanceof Error ? reason.message : "请求失败";
}
function clearTimer() { if (timer) clearTimeout(timer); timer = undefined; }
function statusText(status?: RunState["status"]) {
  if (status === "QUEUED" || status === "RUNNING") return "正在评价";
  if (status === "COMPLETED") return "已完成";
  if (status === "FAILED") return "运行失败";
  return "查看结果";
}
function statusTone(status?: RunState["status"]) {
  if (status === "COMPLETED") return "complete";
  if (status === "FAILED") return "error";
  if (status === "QUEUED" || status === "RUNNING") return "active";
  return "neutral";
}

async function load() {
  clearTimer();
  error.value = "";
  active.value = null;
  result.value = null;
  try {
    detail.value = (await api.get<Detail>(`/${encodeURIComponent(id.value)}`)).data;
    const requested = String(route.query.version || "");
    const workflowVersion = workflowMode.value && workflow.activeRun?.lessonId === id.value ? workflow.activeRun.versionId : "";
    const preferred = workflowVersion || requested;
    versionId.value = detail.value.versions.some(version => version.id === preferred)
      ? preferred
      : detail.value.lesson.currentVersionId;
    history.value = (await api.get<Run[]>(base.value)).data;

    const queryRun = typeof route.query.annotation === "string" ? route.query.annotation : "";
    const savedRun = window.localStorage.getItem(activeKey()) || "";
    const resume = history.value.find(run => run.id === queryRun) || history.value.find(run => run.id === savedRun);
    if (resume) await inspect(resume);
  } catch (reason) {
    error.value = describe(reason);
  }
}

async function inspect(run: Run) {
  clearTimer();
  active.value = run;
  result.value = null;
  error.value = "";
  try {
    const latest = (await api.get<Run>(`${base.value}/${encodeURIComponent(run.id)}`)).data;
    if (active.value?.id !== run.id) return;
    active.value = latest;
    window.localStorage.setItem(activeKey(), latest.id);

    if (latest.state?.status === "COMPLETED") {
      result.value = (await api.get<Result>(`${base.value}/${encodeURIComponent(run.id)}/result`)).data;
      if (workflow.activeRun?.lessonId === id.value && workflow.activeRun.versionId === latest.versionId && workflow.currentStep?.id === "F1") {
        workflow.rememberPath("F1", `/lessons/${id.value}/annotate?version=${encodeURIComponent(latest.versionId)}&annotation=${encodeURIComponent(latest.id)}&workflow=1`);
        workflow.completeStep("F1");
      }
    } else if (latest.state?.status === "QUEUED" || latest.state?.status === "RUNNING") {
      if (!disposed) timer = setTimeout(() => void inspect(latest), 2500);
    }
  } catch (reason) {
    error.value = describe(reason);
  }
}

async function start() {
  if (busy.value || evaluating.value || !versionId.value) return;
  busy.value = true;
  error.value = "";
  result.value = null;
  try {
    const run = (await api.post<Run>(base.value, { versionId: versionId.value, suggest: true })).data;
    history.value = [run, ...history.value.filter(item => item.id !== run.id)];
    window.localStorage.setItem(activeKey(), run.id);
    await inspect(run);
  } catch (reason) {
    error.value = describe(reason);
  } finally {
    busy.value = false;
  }
}

function fileUrl(kind: string) {
  return `/api/platform/lessons/${encodeURIComponent(id.value)}/annotations/${encodeURIComponent(active.value?.id || "")}/artifacts/${encodeURIComponent(kind)}`;
}
function percent(score: number, maximum: number) {
  if (!maximum) return 0;
  return Math.max(0, Math.min(100, (score / maximum) * 100));
}

onMounted(() => void load());
watch(id, () => void load());
watch(() => route.query.version, () => {
  if (!detail.value || workflowMode.value) return;
  const requested = typeof route.query.version === "string" ? route.query.version : "";
  versionId.value = detail.value.versions.some(version => version.id === requested)
    ? requested : detail.value.lesson.currentVersionId;
});
onUnmounted(() => { disposed = true; clearTimer(); });
</script>

<template>
  <main class="annotation-page">
    <AppPageHeader title="智能评价" description="对教案进行多维评价、问题诊断与详细批注。">
      <template #actions>
        <RouterLink class="v2-button v2-button--secondary" to="/review/batch">批量与对比</RouterLink>
      </template>
    </AppPageHeader>

    <p v-if="error" class="page-alert" role="alert">{{ error }}</p>

    <section v-if="detail" class="current-lesson v2-card">
      <div class="lesson-copy">
        <span>{{ workflowMode ? "当前工作流教案" : "当前教案" }}</span>
        <strong>{{ detail.lesson.title }}</strong>
        <VersionBadge
          v-if="selectedVersion"
          :version-number="selectedVersion.versionNumber"
          :source="selectedVersion.sourceModule"
          :latest="selectedVersion.id === detail.lesson.currentVersionId"
        />
        <small>
          <template v-if="detail.lesson.subject">{{ detail.lesson.subject }}</template>
          <template v-if="detail.lesson.subject && detail.lesson.grade"> · </template>
          <template v-if="detail.lesson.grade">{{ detail.lesson.grade }}</template>
          <template v-if="workflowMode"> · 工作流已锁定</template>
        </small>
      </div>
      <div class="lesson-actions">
        <RouterLink v-if="!workflowMode" class="v2-button v2-button--secondary" to="/review">更换教案</RouterLink>
        <button type="button" class="v2-button v2-button--primary" :disabled="busy || evaluating || !versionId" @click="start">
          {{ busy || evaluating ? "正在评价……" : "开始评价" }}
        </button>
      </div>
    </section>

    <section v-if="active && evaluating" class="run-state v2-card" aria-live="polite">
      <LoadingState message="正在分析教案内容并生成评价结果，请稍候……" />
      <div class="run-state-copy"><h2>正在进行智能评价</h2><p>当前任务会自动更新状态，刷新页面后也会继续查询同一任务。</p></div>
    </section>

    <section v-else-if="active?.state?.status === 'FAILED'" class="run-state run-state--error v2-card" aria-live="polite">
      <div><h2>智能评价未完成</h2><p>本次评价未完成，请稍后重新发起。</p></div>
    </section>

    <template v-if="result">
      <section class="result-heading v2-card">
        <div><span>智能评价结果</span><h2>综合得分</h2><p v-if="result.summary">{{ result.summary }}</p></div>
        <strong>{{ result.rubric.score }}<small> / {{ result.rubric.maximum }}</small></strong>
      </section>

      <ReviewRadarChart v-if="dimensions.length === 12" :dimensions="dimensions" />
      <section v-else class="v2-card"><EmptyState title="暂无有效的十二维评分数据" description="当前结果没有返回完整的 12 个二级维度，因此不绘制错误的雷达图。" /></section>

      <section class="result-section">
        <div class="section-heading"><div><span>维度摘要</span><h2>六个一级维度</h2></div><p>一级维度只做总览，A/B/C 仅用于下方二级维度。</p></div>
        <div class="group-grid">
          <article v-for="group in result.rubric.groups" :key="group.name" class="group-card v2-card">
            <header><h3>{{ group.name }}</h3><strong>{{ group.score }} / {{ group.maximum }}</strong></header>
            <div class="track"><span :style="{ width: `${percent(group.score, group.maximum)}%` }" /></div>
          </article>
        </div>
      </section>

      <section class="result-section">
        <div class="section-heading"><div><span>详细评分</span><h2>十二个二级维度详细评价</h2></div><p>展开维度可查看评分理由与对应批注。</p></div>
        <div class="dimension-list">
          <details v-for="dimension in dimensions" :key="dimension.name" class="dimension-card v2-card">
            <summary>
              <span class="dimension-name">{{ dimension.name }}</span>
              <strong>{{ dimension.score }} / {{ dimension.maximum }}</strong>
              <span class="grade" :class="`grade--${dimension.grade.toLowerCase()}`">{{ dimension.grade }}</span>
              <span class="expand-text">查看详情</span>
            </summary>
            <div class="dimension-body">
              <p class="reason">{{ detailByName.get(dimension.name)?.["得分理由"] || "暂无详细评分理由。" }}</p>
            </div>
          </details>
        </div>
      </section>


      <section v-if="annotatedItems.length" class="result-section">
        <div class="section-heading"><div><span>详细批注</span><h2>问题诊断与改进建议</h2></div><p>按二级维度展开查看原文证据、具体分析和建议。</p></div>
        <div class="annotation-list">
          <details v-for="item in annotatedItems" :key="item['维度名称']" class="annotation-group v2-card">
            <summary><strong>{{ item["维度名称"] }}</strong><span>{{ item["批注列表"]?.length || 0 }} 条批注</span></summary>
            <div class="comment-list">
              <article v-for="(comment, index) in item['批注列表']" :key="index" class="comment-card">
                <div class="comment-head"><strong>{{ comment["位置"] || `批注 ${index + 1}` }}</strong><span>{{ comment["评价"] || item["等级"] || "" }}</span></div>
                <blockquote v-if="comment['原文引用']">{{ comment["原文引用"] }}</blockquote>
                <p v-if="comment['具体分析']"><b>分析：</b>{{ comment["具体分析"] }}</p>
                <p v-if="comment['建议']"><b>问题诊断：</b>{{ comment["建议"] }}</p>
                <p v-if="comment['细化建议']" class="suggestion"><b>改进建议：</b>{{ comment["细化建议"] }}</p>
                <details v-if="comment['依据来源'] || comment['理论依据'] || comment['档位参照']" class="evidence-box">
                  <summary>查看评价依据</summary>
                  <p v-if="comment['依据来源']"><b>依据来源：</b>{{ comment["依据来源"] }}</p>
                  <p v-if="comment['理论依据']"><b>理论依据：</b>{{ comment["理论依据"] }}</p>
                  <pre v-if="comment['档位参照']">{{ comment["档位参照"] }}</pre>
                </details>
              </article>
            </div>
          </details>
        </div>
      </section>

      <ResultDownloadPanel v-if="downloadFiles.length" :files="downloadFiles" description="本次智能评价结果已保存，可按需下载教师使用的结果文件。" />
    </template>

    <section v-if="history.length" class="history-card v2-card">
      <div class="section-heading"><div><span>历史记录</span><h2>本教案评价记录</h2></div><p>点击已保存任务可恢复状态或查看对应结果。</p></div>
      <div class="run-list">
        <button v-for="run in history" :key="run.id" :class="{ chosen: active?.id === run.id }" @click="inspect(run)">
          <div><strong>V{{ run.versionNumber }}</strong><small>{{ new Date(run.createdAt).toLocaleString() }}</small></div>
          <span class="v2-status" :class="`v2-status--${statusTone(active?.id === run.id ? active.state?.status : run.state?.status)}`">{{ statusText(active?.id === run.id ? active.state?.status : run.state?.status) }}</span>
        </button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.annotation-page{display:grid;gap:24px}.page-alert{margin:0;padding:13px 16px;border:1px solid #efc6c7;border-radius:var(--radius-md);color:var(--color-danger);background:var(--color-danger-soft)}.current-lesson{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:20px}.lesson-copy{display:grid;gap:5px;min-width:0}.lesson-copy>span,.section-heading span,.result-heading span{color:var(--color-primary);font-size:12px;font-weight:800}.lesson-copy>strong{overflow:hidden;text-overflow:ellipsis;color:var(--color-text);font-size:19px}.lesson-copy>small{color:var(--color-text-secondary)}.lesson-actions{display:flex;align-items:center;gap:10px;flex:none}.run-state{display:grid;grid-template-columns:220px minmax(0,1fr);align-items:center;padding:8px 24px}.run-state :deep(.state-box){min-height:120px}.run-state-copy h2,.run-state--error h2{margin:0 0 8px;font-size:20px}.run-state-copy p,.run-state--error p{margin:0;color:var(--color-text-secondary);line-height:1.7}.run-state--error{display:block;padding:24px;border-color:#efc6c7;background:var(--color-danger-soft)}.result-heading{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:26px}.result-heading h2{margin:6px 0 7px;font-size:22px}.result-heading p{max-width:780px;margin:0;color:var(--color-text-secondary);line-height:1.7}.result-heading>strong{flex:none;color:var(--color-primary);font-size:46px;letter-spacing:-.04em}.result-heading>strong small{font-size:17px;color:var(--color-text-muted);letter-spacing:0}.result-section{display:grid;gap:16px}.section-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:18px}.section-heading h2{margin:5px 0 0;font-size:22px}.section-heading p{margin:0;color:var(--color-text-secondary);font-size:13px}.group-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.group-card{padding:18px}.group-card header{display:flex;align-items:center;justify-content:space-between;gap:14px}.group-card h3{margin:0;font-size:16px}.group-card strong{color:var(--color-primary);font-size:16px}.track{height:6px;margin-top:16px;overflow:hidden;border-radius:999px;background:#e8eef8}.track span{display:block;height:100%;border-radius:inherit;background:var(--color-primary)}.dimension-list{display:grid;gap:10px}.dimension-card{overflow:hidden}.dimension-card summary{display:grid;grid-template-columns:minmax(0,1fr) auto 34px 70px;align-items:center;gap:14px;padding:17px 18px;cursor:pointer;list-style:none}.dimension-card summary::-webkit-details-marker{display:none}.dimension-name{font-weight:750}.dimension-card summary>strong{color:var(--color-text)}.expand-text{color:var(--color-primary);font-size:12px;font-weight:700;text-align:right}.grade{display:grid;place-items:center;width:30px;height:25px;border-radius:999px;font-size:12px;font-weight:800}.grade--a{color:var(--color-primary);background:var(--color-primary-soft)}.grade--b{color:var(--color-attention);background:var(--color-attention-soft)}.grade--c{color:var(--color-danger);background:var(--color-danger-soft)}.dimension-body{padding:0 18px 18px;border-top:1px solid #edf1f7}.reason{margin:16px 0;color:var(--color-text-secondary);line-height:1.75}.annotation-list{display:grid;gap:10px}.annotation-group{overflow:hidden}.annotation-group>summary{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 18px;cursor:pointer;list-style:none}.annotation-group>summary::-webkit-details-marker{display:none}.annotation-group>summary span{color:var(--color-primary);font-size:12px;font-weight:700}.annotation-group>.comment-list{padding:0 18px 18px;border-top:1px solid #edf1f7}.comment-list{display:grid;gap:12px}.comment-card{padding:16px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:var(--color-surface-soft)}.comment-head{display:flex;align-items:center;justify-content:space-between;gap:14px}.comment-head span{color:var(--color-primary);font-size:12px;font-weight:800}.comment-card blockquote{margin:12px 0;padding:10px 13px;border-left:3px solid var(--color-primary-border);color:var(--color-text-secondary);background:#fff;line-height:1.7}.comment-card p{margin:9px 0;color:var(--color-text-secondary);line-height:1.7}.comment-card b{color:var(--color-text)}.comment-card .suggestion{color:#31547f}.evidence-box{margin-top:10px;padding-top:10px;border-top:1px dashed #cbd8eb}.evidence-box summary{display:block;padding:0;color:var(--color-primary);font-size:12px;font-weight:700}.evidence-box pre{overflow:auto;white-space:pre-wrap;color:var(--color-text-secondary)}.history-card{padding:22px}.run-list{display:grid;gap:9px;margin-top:16px}.run-list button{display:flex;align-items:center;justify-content:space-between;gap:16px;width:100%;padding:12px 14px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff;text-align:left;cursor:pointer}.run-list button:hover,.run-list button.chosen{border-color:var(--color-primary-border);background:#f7f9ff}.run-list button div{display:grid;gap:3px}.run-list button small{color:var(--color-text-muted)}
@media(max-width:900px){.group-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.run-state{grid-template-columns:1fr}.run-state :deep(.state-box){min-height:90px}.section-heading{align-items:flex-start;flex-direction:column}}
@media(max-width:650px){.current-lesson,.result-heading{align-items:stretch;flex-direction:column}.lesson-actions{align-items:stretch;flex-direction:column}.lesson-actions>*{width:100%}.result-heading>strong{font-size:38px}.group-grid{grid-template-columns:1fr}.dimension-card summary{grid-template-columns:minmax(0,1fr) auto 32px}.expand-text{display:none}}
</style>
