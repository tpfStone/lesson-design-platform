<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import axios from "axios";
import AppPageHeader from "../components/AppPageHeader.vue";
import BatchLessonSelector, { type BatchSelection } from "../components/BatchLessonSelector.vue";
import BatchProgressPanel, { type BatchProgressItem, type BatchProgressState } from "../components/BatchProgressPanel.vue";
import BatchResultTable, { type BatchResultRow } from "../components/BatchResultTable.vue";
import LessonComparisonChart, { type ComparisonDimension, type ComparisonSeries } from "../components/LessonComparisonChart.vue";
import LoadingState from "../components/LoadingState.vue";

interface BatchPayload extends BatchProgressState {
  batchId: string;
  items?: BatchProgressItem[];
  qualitySummary?: unknown;
  strengths?: unknown;
  commonIssues?: unknown;
  artifacts?: Record<string, string>;
}
interface PersistedState {
  batchId: string;
  comparisonId: string;
  selections: BatchSelection[];
  compareIds: string[];
}
type JsonObject = Record<string, unknown>;

const STORAGE_KEY = "f1-batch-review-v2";
const selections = ref<BatchSelection[]>([]);
const batchId = ref("");
const batchState = ref<BatchPayload | null>(null);
const batchResult = ref<BatchPayload | null>(null);
const starting = ref(false);
const error = ref("");
const compareIds = ref<string[]>([]);
const comparisonId = ref("");
const comparisonResult = ref<unknown>(null);
const comparing = ref(false);
const showReport = ref(false);
let batchTimer: ReturnType<typeof setTimeout> | undefined;
let comparisonTimer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;

const batchRunning = computed(() => batchState.value?.status === "QUEUED" || batchState.value?.status === "RUNNING");
const batchTerminal = computed(() => ["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"].includes(batchState.value?.status || ""));
const rows = computed<BatchResultRow[]>(() => {
  const sourceItems = batchResult.value?.items || batchState.value?.items || [];
  return selections.value.map(selection => {
    const item = sourceItems.find(candidate => candidate.lessonId === selection.lessonId && candidate.versionId === selection.versionId);
    return {
      key: `${selection.lessonId}:${selection.versionId}`,
      lessonId: selection.lessonId,
      lessonTitle: selection.lessonTitle,
      versionId: selection.versionId,
      versionNumber: selection.versionNumber,
      annotationId: item?.annotationId,
      score: typeof item?.score === "number" ? item.score : null,
      status: item?.status || (batchTerminal.value ? "FAILED" : "QUEUED"),
    };
  });
});
const selectedCompareRows = computed(() => rows.value.filter(row => row.annotationId && compareIds.value.includes(row.annotationId)));
const quality = computed(() => asObject(batchResult.value?.qualitySummary));
const successScores = computed(() => rows.value.map(row => row.score).filter((score): score is number => typeof score === "number"));
const qualityAverage = computed(() => {
  const provided = numberFrom(quality.value, ["averageScore", "average_score", "average", "avgScore", "avg_score", "meanScore", "平均分"]);
  if (provided !== null) return provided;
  return successScores.value.length ? Math.round(successScores.value.reduce((sum, score) => sum + score, 0) / successScores.value.length * 10) / 10 : null;
});
const qualityHighest = computed(() => numberFrom(quality.value, ["highestScore", "highest_score", "highest", "maxScore", "max_score", "最高分"]) ?? (successScores.value.length ? Math.max(...successScores.value) : null));
const qualityLowest = computed(() => numberFrom(quality.value, ["lowestScore", "lowest_score", "lowest", "minScore", "min_score", "最低分"]) ?? (successScores.value.length ? Math.min(...successScores.value) : null));
interface StrengthSummary {
  dimension: string;
  averageRate: number | null;
  averageScore: number | null;
  maximum: number | null;
  gradeDistribution: Record<string, number>;
}
interface CommonIssueSummary {
  dimension: string;
  averageRate: number | null;
  cCount: number | null;
  annotationCount: number | null;
  problemExamples: string[];
  recommendationExamples: string[];
}

const successfulLessonCount = computed(() =>
  numberFrom(quality.value, ["lessonCount", "lesson_count", "count", "评审教案"]) ?? batchState.value?.succeeded ?? successScores.value.length,
);
const strengths = computed<StrengthSummary[]>(() => {
  const direct = normalizeStrengths(batchResult.value?.strengths);
  return direct.length ? direct : normalizeStrengths(quality.value?.strengths);
});
const commonIssues = computed<CommonIssueSummary[]>(() => {
  const direct = normalizeCommonIssues(batchResult.value?.commonIssues);
  return direct.length ? direct : normalizeCommonIssues(quality.value?.commonIssues ?? quality.value?.common_issues);
});
const comparisonSeries = computed<ComparisonSeries[]>(() => normalizeComparison(comparisonResult.value, selectedCompareRows.value));

function asObject(value: unknown): JsonObject | null { return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : null; }
function asArray(value: unknown): unknown[] { return Array.isArray(value) ? value : []; }
function numberFrom(object: JsonObject | null, keys: string[]): number | null {
  if (!object) return null;
  for (const key of keys) { const value = object[key]; if (typeof value === "number" && Number.isFinite(value)) return value; }
  return null;
}
function stringFrom(object: JsonObject | null, keys: string[]): string {
  if (!object) return "";
  for (const key of keys) { const value = object[key]; if (typeof value === "string" && value.trim()) return value.trim(); }
  return "";
}
function textArray(value: unknown): string[] {
  return asArray(value).filter((item): item is string => typeof item === "string").map(item => item.trim()).filter(Boolean);
}
function normalizeStrengths(value: unknown): StrengthSummary[] {
  return asArray(value).map(item => {
    if (typeof item === "string" && item.trim()) {
      return { dimension: item.trim(), averageRate: null, averageScore: null, maximum: null, gradeDistribution: {} };
    }
    const object = asObject(item);
    if (!object) return null;
    const dimension = stringFrom(object, ["dimension", "name", "title", "维度"]);
    if (!dimension) return null;
    const distributionObject = asObject(object.gradeDistribution ?? object.grade_distribution);
    const gradeDistribution: Record<string, number> = {};
    if (distributionObject) {
      for (const grade of ["A", "B", "C"]) {
        const count = distributionObject[grade];
        if (typeof count === "number" && Number.isFinite(count)) gradeDistribution[grade] = count;
      }
    }
    return {
      dimension,
      averageRate: numberFrom(object, ["averageRate", "average_rate", "rate", "平均得分率"]),
      averageScore: numberFrom(object, ["averageScore", "average_score", "score", "平均得分"]),
      maximum: numberFrom(object, ["maximum", "max", "满分"]),
      gradeDistribution,
    };
  }).filter((item): item is StrengthSummary => Boolean(item));
}
function normalizeCommonIssues(value: unknown): CommonIssueSummary[] {
  return asArray(value).map(item => {
    if (typeof item === "string" && item.trim()) {
      return { dimension: item.trim(), averageRate: null, cCount: null, annotationCount: null, problemExamples: [], recommendationExamples: [] };
    }
    const object = asObject(item);
    if (!object) return null;
    const dimension = stringFrom(object, ["dimension", "name", "title", "维度"]);
    if (!dimension) return null;
    return {
      dimension,
      averageRate: numberFrom(object, ["averageRate", "average_rate", "rate", "平均得分率"]),
      cCount: numberFrom(object, ["cCount", "c_count", "C", "C数量"]),
      annotationCount: numberFrom(object, ["annotationCount", "annotation_count", "批注数"]),
      problemExamples: textArray(object.problemExamples ?? object.problem_examples ?? object.problems),
      recommendationExamples: textArray(object.recommendationExamples ?? object.recommendation_examples ?? object.recommendations),
    };
  }).filter((item): item is CommonIssueSummary => Boolean(item));
}
function gradeDistributionText(distribution: Record<string, number>): string {
  return ["A", "B", "C"].filter(grade => typeof distribution[grade] === "number").map(grade => `${grade} ${distribution[grade]}份`).join(" · ");
}
function describe(reason: unknown) {
  if (axios.isAxiosError(reason)) {
    const status = reason.response?.status || 0;
    const body = reason.response?.data as { detail?: string } | undefined;
    if (status >= 500) return "智能评价服务暂时不可用，请稍后重试。";
    return body?.detail || "请求未完成，请检查当前选择后重试。";
  }
  return reason instanceof Error ? reason.message : "请求失败";
}
function persist() {
  const value: PersistedState = { batchId: batchId.value, comparisonId: comparisonId.value, selections: selections.value, compareIds: compareIds.value };
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value)); } catch { /* Keep the current page state in memory. */ }
}
function clearTimers() { if (batchTimer) clearTimeout(batchTimer); if (comparisonTimer) clearTimeout(comparisonTimer); batchTimer = undefined; comparisonTimer = undefined; }
function resetBatch() {
  clearTimers(); batchId.value = ""; batchState.value = null; batchResult.value = null; comparisonId.value = ""; comparisonResult.value = null; compareIds.value = []; showReport.value = false; error.value = ""; persist();
}

async function startBatch() {
  if (starting.value || selections.value.length < 2 || selections.value.length > 20) return;
  starting.value = true; error.value = ""; resetBatch();
  try {
    const response = (await axios.post<BatchPayload>("/api/platform/annotations/batches", {
      items: selections.value.map(item => ({ lessonId: item.lessonId, versionId: item.versionId })),
      suggest: true,
    })).data;
    batchId.value = response.batchId;
    batchState.value = response;
    persist();
    await pollBatch();
  } catch (reason) { error.value = describe(reason); }
  finally { starting.value = false; }
}

async function pollBatch() {
  if (!batchId.value) return;
  try {
    batchState.value = (await axios.get<BatchPayload>(`/api/platform/annotations/batches/${encodeURIComponent(batchId.value)}`)).data;
    persist();
    if (["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"].includes(batchState.value.status)) {
      if (batchState.value.succeeded > 0) {
        batchResult.value = (await axios.get<BatchPayload>(`/api/platform/annotations/batches/${encodeURIComponent(batchId.value)}/result`)).data;
      }
      return;
    }
    if (!disposed) batchTimer = setTimeout(() => void pollBatch(), 2500);
  } catch (reason) { error.value = describe(reason); }
}

function batchArtifact(kind: string) { return `/api/platform/annotations/batches/${encodeURIComponent(batchId.value)}/artifacts/${encodeURIComponent(kind)}`; }

async function startComparison() {
  if (comparing.value || compareIds.value.length < 2 || compareIds.value.length > 5) return;
  comparing.value = true; error.value = ""; comparisonResult.value = null;
  try {
    const response = (await axios.post<JsonObject>("/api/platform/annotations/comparisons", { annotationIds: compareIds.value })).data;
    comparisonId.value = stringFrom(response, ["comparisonId"]);
    if (!comparisonId.value) throw new Error("暂时无法创建横向对比，请稍后重试。");
    persist();
    await pollComparison();
  } catch (reason) { error.value = describe(reason); }
  finally { comparing.value = false; }
}

async function pollComparison() {
  if (!comparisonId.value) return;
  try {
    const state = (await axios.get<JsonObject>(`/api/platform/annotations/comparisons/${encodeURIComponent(comparisonId.value)}`)).data;
    const status = stringFrom(state, ["status"]);
    if (status === "QUEUED" || status === "RUNNING") {
      if (!disposed) comparisonTimer = setTimeout(() => void pollComparison(), 1200);
      return;
    }
    comparisonResult.value = (await axios.get<unknown>(`/api/platform/annotations/comparisons/${encodeURIComponent(comparisonId.value)}/result`)).data;
    persist();
  } catch (reason) { error.value = describe(reason); }
}

function dimensionFrom(value: unknown): ComparisonDimension | null {
  const object = asObject(value); if (!object) return null;
  const name = stringFrom(object, ["name", "dimension", "dimensionName", "维度名称"]);
  const score = numberFrom(object, ["score", "得分"]);
  const maximum = numberFrom(object, ["maximum", "max", "满分"]);
  const grade = stringFrom(object, ["grade", "等级"]);
  if (!name || score === null || maximum === null) return null;
  return { name, score, maximum, grade: grade || undefined };
}
function normalizeComparison(raw: unknown, fallbackRows: BatchResultRow[]): ComparisonSeries[] {
  const root = asObject(raw); if (!root || !fallbackRows.length) return [];
  const seriesOriented = ["items", "runs", "series", "results"].flatMap(key => asArray(root[key])).filter(item => asObject(item));
  const withDimensions = seriesOriented.filter(item => asArray(asObject(item)?.dimensions).length >= 1);
  if (withDimensions.length >= 2) {
    return withDimensions.slice(0, fallbackRows.length).map((value, index) => {
      const object = asObject(value)!;
      const row = fallbackRows[index];
      const parsed = asArray(object.dimensions).map(dimensionFrom).filter((item): item is ComparisonDimension => Boolean(item));
      return { id: row?.annotationId || String(index), label: row ? `${row.lessonTitle} V${row.versionNumber}` : `教案 ${index + 1}`, total: numberFrom(object, ["score", "totalScore", "total"]), dimensions: parsed };
    }).filter(item => item.dimensions.length === 12);
  }

  const dimensionRows = asArray(root.dimensions).map(asObject).filter((item): item is JsonObject => Boolean(item));
  if (!dimensionRows.length) return [];
  const output = fallbackRows.map((row, index) => ({ id: row.annotationId || row.key, label: `${row.lessonTitle} V${row.versionNumber}`, total: row.score, dimensions: [] as ComparisonDimension[] }));
  for (const dimensionObject of dimensionRows) {
    const name = stringFrom(dimensionObject, ["name", "dimension", "dimensionName", "维度名称"]);
    if (!name) continue;
    const values = ["values", "items", "runs", "results", "scores"].flatMap(key => asArray(dimensionObject[key]));
    values.slice(0, output.length).forEach((value, index) => {
      if (typeof value === "number") {
        const maximum = numberFrom(dimensionObject, ["maximum", "max", "满分"]);
        if (maximum !== null) output[index]!.dimensions.push({ name, score: value, maximum });
        return;
      }
      const object = asObject(value); if (!object) return;
      const score = numberFrom(object, ["score", "得分"]);
      const maximum = numberFrom(object, ["maximum", "max", "满分"]) ?? numberFrom(dimensionObject, ["maximum", "max", "满分"]);
      const grade = stringFrom(object, ["grade", "等级"]);
      if (score !== null && maximum !== null) output[index]!.dimensions.push({ name, score, maximum, grade: grade || undefined });
    });
  }
  return output.filter(item => item.dimensions.length === 12);
}

function loadPersisted() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null") as PersistedState | null;
    if (!saved) return;
    selections.value = Array.isArray(saved.selections) ? saved.selections.slice(0, 20) : [];
    batchId.value = saved.batchId || "";
    comparisonId.value = saved.comparisonId || "";
    compareIds.value = Array.isArray(saved.compareIds) ? saved.compareIds.slice(0, 5) : [];
  } catch { /* Ignore malformed local state. */ }
}

watch(selections, () => persist(), { deep: true });
watch(compareIds, () => persist(), { deep: true });

onMounted(async () => {
  loadPersisted();
  if (batchId.value) await pollBatch();
  if (comparisonId.value) await pollComparison();
});
onUnmounted(() => { disposed = true; clearTimers(); });
</script>

<template>
  <main class="batch-review-page">
    <AppPageHeader title="批量与对比" description="同时评价多份教案，并查看整体质量与横向差异。">
      <template #actions><RouterLink class="v2-button v2-button--secondary" to="/review">返回智能评价</RouterLink></template>
    </AppPageHeader>

    <p v-if="error" class="page-alert" role="alert">{{ error }}</p>

    <BatchLessonSelector v-model="selections" :disabled="batchRunning || starting" :max="20" />

    <div class="start-row">
      <p>至少选择 2 份教案后开始批量评审；当前批次会保留在本浏览器中，返回页面后可继续查看。</p>
      <div class="start-actions">
        <button v-if="batchId && batchTerminal" type="button" class="v2-button v2-button--secondary" @click="resetBatch">新建批次</button>
        <button type="button" class="v2-button v2-button--primary" :disabled="starting || batchRunning || selections.length < 2 || selections.length > 20" @click="startBatch">{{ starting ? "正在启动……" : batchRunning ? "评价进行中" : "开始批量评审" }}</button>
      </div>
    </div>

    <BatchProgressPanel v-if="batchState && (batchRunning || batchState.completed > 0)" :selections="selections" :state="batchState" />

    <section v-if="batchState?.status === 'COMPLETED_WITH_ERRORS'" class="partial-warning v2-card">
      <strong>{{ batchState.succeeded }} / {{ batchState.total }} 份评价成功</strong>
      <p>{{ batchState.failed }} 份教案评价未成功。其他成功结果和综合报告仍可正常查看。</p>
    </section>
    <section v-else-if="batchState?.status === 'FAILED'" class="partial-warning partial-warning--error v2-card">
      <strong>本次批量评价未产生可用结果</strong><p>可以检查服务状态后重新建立一个批次；当前页面不会自动重复提交。</p>
    </section>

    <template v-if="batchResult">
      <BatchResultTable v-model="compareIds" :rows="rows" :disabled="comparing" :max-compare="5" />

      <section class="quality-report v2-card">
        <div class="quality-heading"><div><span>综合质量报告</span><h2>批次整体质量</h2></div><div class="report-actions"><button type="button" class="v2-button v2-button--secondary" @click="showReport = !showReport">{{ showReport ? "收起综合报告" : "查看综合报告" }}</button><a class="v2-button v2-button--secondary" :href="batchArtifact('quality_docx')" download>下载 Word</a></div></div>
        <div class="quality-stats">
          <article><span>成功评审</span><strong>{{ successfulLessonCount }}</strong></article>
          <article><span>平均得分</span><strong>{{ qualityAverage ?? "—" }}</strong></article>
          <article><span>最高得分</span><strong>{{ qualityHighest ?? "—" }}</strong></article>
          <article><span>最低得分</span><strong>{{ qualityLowest ?? "—" }}</strong></article>
        </div>
        <div class="quality-brief">
          <article>
            <h3>整体优势</h3>
            <div v-if="strengths.length" class="quality-summary-list">
              <div v-for="item in strengths.slice(0,3)" :key="item.dimension" class="quality-summary-item">
                <div class="quality-summary-head"><strong>{{ item.dimension }}</strong><span v-if="item.averageRate !== null">{{ item.averageRate }}%</span></div>
                <p>
                  <template v-if="item.averageScore !== null && item.maximum !== null">平均 {{ item.averageScore }} / {{ item.maximum }}</template>
                  <template v-if="gradeDistributionText(item.gradeDistribution)"><span v-if="item.averageScore !== null && item.maximum !== null"> · </span>{{ gradeDistributionText(item.gradeDistribution) }}</template>
                </p>
              </div>
            </div>
            <p v-else>当前结果未返回可展示的整体优势摘要。</p>
          </article>
          <article>
            <h3>共性问题</h3>
            <div v-if="commonIssues.length" class="quality-summary-list">
              <div v-for="item in commonIssues.slice(0,3)" :key="item.dimension" class="quality-summary-item">
                <div class="quality-summary-head"><strong>{{ item.dimension }}</strong><span v-if="item.averageRate !== null">{{ item.averageRate }}%</span></div>
                <p v-if="item.cCount !== null || item.annotationCount !== null" class="quality-summary-meta">
                  <template v-if="item.cCount !== null">C 等级 {{ item.cCount }} 份</template>
                  <template v-if="item.annotationCount !== null"><span v-if="item.cCount !== null"> · </span>{{ item.annotationCount }} 条批注</template>
                </p>
                <p v-if="item.problemExamples[0]" class="quality-summary-example">{{ item.problemExamples[0] }}</p>
              </div>
            </div>
            <p v-else>当前结果未返回可展示的共性问题摘要。</p>
          </article>
        </div>
        <div v-if="showReport" class="report-detail">
          <div v-if="commonIssues.length" class="report-detail-section">
            <strong>共性问题与改进建议</strong>
            <article v-for="item in commonIssues" :key="`issue-detail-${item.dimension}`" class="report-issue">
              <h4>{{ item.dimension }}</h4>
              <div v-if="item.problemExamples.length"><span>典型诊断</span><ul><li v-for="(example, index) in item.problemExamples" :key="`${item.dimension}-problem-${index}`">{{ example }}</li></ul></div>
              <div v-if="item.recommendationExamples.length"><span>改进建议</span><ul><li v-for="(example, index) in item.recommendationExamples" :key="`${item.dimension}-recommendation-${index}`">{{ example }}</li></ul></div>
            </article>
          </div>
          <p>以上内容来自本次批量评审的真实聚合结果；完整综合质量报告可下载 Word 查看。</p>
        </div>
      </section>

      <section class="compare-launch v2-card">
        <div><span>横向对比</span><h2>选择成功结果进行比较</h2><p>至少选择 2 份，前端最多同时展示 5 份，保证图表可读性。</p></div>
        <div class="compare-action"><strong>已选择 {{ compareIds.length }} 份</strong><button type="button" class="v2-button v2-button--primary" :disabled="comparing || compareIds.length < 2 || compareIds.length > 5" @click="startComparison">{{ comparing ? "正在生成对比……" : "横向对比" }}</button></div>
      </section>

      <section v-if="comparing && !comparisonResult" class="v2-card"><LoadingState message="正在读取横向对比结果……" /></section>

      <template v-if="comparisonResult">
        <section class="comparison-heading v2-card"><div><span>教案横向对比</span><h2>总分</h2></div><div class="total-scores"><article v-for="item in comparisonSeries" :key="item.id"><span>{{ item.label }}</span><strong>{{ typeof item.total === 'number' ? item.total : '—' }}</strong></article></div></section>
        <LessonComparisonChart v-if="comparisonSeries.length >= 2" :series="comparisonSeries" />
        <section v-else class="comparison-unavailable v2-card"><h2>对比结果已返回</h2><p>当前对比结果暂时无法完整展示十二维图表。页面不会使用不完整数据绘制可能误导的结果。</p></section>

        <section v-if="comparisonSeries.length >= 2" class="comparison-table v2-card">
          <div class="comparison-table-heading"><span>十二维对比表</span><h2>二级维度评分与等级</h2></div>
          <div class="table-scroll"><table><thead><tr><th>维度</th><th v-for="item in comparisonSeries" :key="item.id">{{ item.label }}</th></tr></thead><tbody><tr v-for="dimension in comparisonSeries[0]?.dimensions || []" :key="dimension.name"><th>{{ dimension.name }}</th><td v-for="item in comparisonSeries" :key="item.id"><template v-if="item.dimensions.find(value => value.name === dimension.name)">{{ item.dimensions.find(value => value.name === dimension.name)?.score }} / {{ item.dimensions.find(value => value.name === dimension.name)?.maximum }}<span v-if="item.dimensions.find(value => value.name === dimension.name)?.grade" class="mini-grade">{{ item.dimensions.find(value => value.name === dimension.name)?.grade }}</span></template><template v-else>—</template></td></tr></tbody></table></div>
        </section>
      </template>
    </template>
  </main>
</template>

<style scoped>
.batch-review-page{display:grid;gap:24px}.page-alert{margin:0;padding:13px 16px;border:1px solid #efc6c7;border-radius:var(--radius-md);color:var(--color-danger);background:var(--color-danger-soft)}.start-row{display:flex;align-items:center;justify-content:space-between;gap:18px}.start-row p{margin:0;color:var(--color-text-secondary);font-size:13px}.start-actions{display:flex;gap:10px;flex:none}.partial-warning{padding:18px 20px;border-color:#ead49e;background:var(--color-attention-soft)}.partial-warning strong{color:var(--color-attention)}.partial-warning p{margin:5px 0 0;color:var(--color-text-secondary)}.partial-warning--error{border-color:#efc6c7;background:var(--color-danger-soft)}.partial-warning--error strong{color:var(--color-danger)}.quality-report{padding:22px}.quality-heading,.compare-launch,.comparison-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.quality-heading span,.compare-launch>div>span,.comparison-heading>div>span,.comparison-table-heading span{color:var(--color-primary);font-size:12px;font-weight:800}.quality-heading h2,.compare-launch h2,.comparison-heading h2,.comparison-table-heading h2{margin:5px 0 0;font-size:21px}.report-actions{display:flex;gap:9px}.quality-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:20px}.quality-stats article{padding:15px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:var(--color-surface-soft)}.quality-stats span{display:block;color:var(--color-text-secondary);font-size:12px}.quality-stats strong{display:block;margin-top:5px;color:var(--color-text);font-size:24px}.quality-brief{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:14px}.quality-brief article{padding:17px;border:1px solid var(--color-border);border-radius:var(--radius-md)}.quality-brief h3{margin:0 0 8px;font-size:16px}.quality-summary-list{display:grid;gap:10px}.quality-summary-item{padding:12px 13px;border:1px solid #edf1f7;border-radius:var(--radius-sm);background:var(--color-surface-soft)}.quality-summary-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.quality-summary-head strong{font-size:14px}.quality-summary-head span{color:var(--color-primary);font-size:13px;font-weight:800}.quality-brief p,.report-detail p{margin:0;color:var(--color-text-secondary);line-height:1.7}.quality-summary-item>p{margin-top:5px;font-size:12px}.quality-summary-meta{color:var(--color-text-secondary)}.quality-summary-example{display:-webkit-box;overflow:hidden;-webkit-box-orient:vertical;-webkit-line-clamp:3}.report-detail{display:grid;gap:14px;margin-top:14px;padding:14px;border-radius:var(--radius-md);background:var(--color-surface-soft)}.report-detail strong{display:block;margin-bottom:7px}.report-detail ul{margin:5px 0 0;padding-left:20px;color:var(--color-text-secondary);line-height:1.8}.report-detail-section{display:grid;gap:10px}.report-issue{padding:13px;border:1px solid var(--color-border);border-radius:var(--radius-sm);background:var(--color-surface)}.report-issue h4{margin:0 0 8px}.report-issue>div+div{margin-top:10px}.report-issue span{font-size:12px;font-weight:800;color:var(--color-text)}.compare-launch{padding:22px}.compare-launch p{margin:6px 0 0;color:var(--color-text-secondary);font-size:13px}.compare-action{display:flex;align-items:center;gap:14px;flex:none}.compare-action>strong{color:var(--color-text-secondary);font-size:13px}.comparison-heading{padding:22px}.total-scores{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:10px}.total-scores article{min-width:130px;padding:10px 13px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:var(--color-surface-soft)}.total-scores span{display:block;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--color-text-secondary);font-size:11px}.total-scores strong{display:block;margin-top:4px;color:var(--color-primary);font-size:22px}.comparison-unavailable{padding:22px}.comparison-unavailable h2{margin:0 0 7px;font-size:20px}.comparison-unavailable p{margin:0;color:var(--color-text-secondary);line-height:1.7}.comparison-table{overflow:hidden}.comparison-table-heading{padding:22px 22px 15px}.table-scroll{overflow:auto;border-top:1px solid var(--color-border)}table{width:100%;min-width:760px;border-collapse:collapse}th,td{padding:13px 15px;border-bottom:1px solid #edf1f7;text-align:left;font-size:12px}thead th{color:var(--color-text-secondary);background:#f8faff}tbody th{font-size:13px}.mini-grade{display:inline-grid;place-items:center;min-width:24px;height:22px;margin-left:6px;padding:0 6px;border-radius:999px;color:var(--color-primary);background:var(--color-primary-soft);font-weight:800}
@media(max-width:800px){.start-row,.quality-heading,.compare-launch,.comparison-heading{align-items:stretch;flex-direction:column}.start-actions,.report-actions{align-items:stretch;flex-direction:column}.start-actions>*,.report-actions>*{width:100%}.quality-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.quality-brief{grid-template-columns:1fr}.compare-action{justify-content:space-between}.total-scores{justify-content:flex-start}}
@media(max-width:520px){.quality-stats{grid-template-columns:1fr}.compare-action{align-items:stretch;flex-direction:column}.compare-action button{width:100%}}
</style>
