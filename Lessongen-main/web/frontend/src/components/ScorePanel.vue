<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  defineComponent,
  h,
  onBeforeUnmount,
  onMounted,
  ref,
} from "vue";

const props = defineProps<{
  scores: Record<string, number>;
  overall?: number | null;
}>();
const labels: Record<string, string> = {
  curriculumAlignment: "课标对齐",
  knowledgeAccuracy: "知识准确",
  teachingLogic: "教学逻辑",
  classroomFeasibility: "课堂可行",
  differentiatedInstruction: "差异教学",
  studentEngagement: "学生参与",
  assessmentDesign: "评价设计",
  languageAndFormat: "语言格式",
};
type ScoreRow = { key: string; label: string; score: number | null };
type ScoredRow = { key: string; label: string; score: number };
const rows = computed(
  () =>
    Object.entries(labels).map(([key, label]) => {
      const value = props.scores?.[key];
      return {
        key,
        label,
        score:
          typeof value === "number" &&
          Number.isFinite(value) &&
          value >= 0 &&
          value <= 10
            ? value
            : null,
      };
    }) satisfies ScoreRow[],
);
const chartRows = computed(() =>
  rows.value.filter((row): row is ScoredRow => row.score !== null),
);
const hasCompleteScores = computed(
  () => chartRows.value.length === Object.keys(labels).length,
);
const validOverall = computed(() =>
  typeof props.overall === "number" &&
  Number.isFinite(props.overall) &&
  props.overall >= 0 &&
  props.overall <= 10
    ? props.overall
    : null,
);
const chartSlot = ref<HTMLDivElement>();
const showChart = ref(false);
let observer: globalThis.IntersectionObserver | undefined;
const ChartFallback = defineComponent({
  render: () =>
    h("p", { class: "chart-fallback" }, "图表暂不可用，数值表仍可查看。"),
});
const RadarChartCanvas = defineAsyncComponent({
  loader: () => import("./RadarChartCanvas.vue"),
  errorComponent: ChartFallback,
  delay: 150,
  timeout: 15_000,
});
onMounted(() => {
  if (!chartSlot.value || !("IntersectionObserver" in window)) {
    showChart.value = true;
    return;
  }
  observer = new window.IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        showChart.value = true;
        observer?.disconnect();
      }
    },
    { rootMargin: "120px" },
  );
  observer.observe(chartSlot.value);
});
onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <section class="score-panel v2-card">
    <div class="section-heading">
      <div>
        <span class="eyebrow">内部优化质量</span>
        <h2>八维内部质量</h2>
      </div>
      <div class="overall-score" :class="{ unavailable: validOverall == null }">
        <strong>{{
          validOverall == null ? "暂不可用" : validOverall.toFixed(1)
        }}</strong
        ><span v-if="validOverall != null">/ 10</span>
      </div>
    </div>
    <p class="score-notice">
      用于判断本次设计修改结果是否达到建议使用标准，不等同于“智能评价”的教案评价分数。
    </p>
    <div class="score-layout">
      <div
        ref="chartSlot"
        class="radar-slot"
        :class="{ unavailable: !hasCompleteScores }"
      >
        <p v-if="!hasCompleteScores" class="chart-fallback">
          部分维度暂无分数，暂不绘制雷达图；已提供的分数见数值表。
        </p>
        <RadarChartCanvas v-else-if="showChart" :rows="chartRows" />
        <p v-else class="chart-fallback">
          滚动到图表时加载；数值表可直接阅读。
        </p>
      </div>
      <dl class="score-list">
        <div v-for="row in rows" :key="row.key">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.score == null ? "暂不可用" : row.score.toFixed(1) }}</dd>
        </div>
      </dl>
    </div>
  </section>
</template>

<style scoped>
.score-panel{padding:22px;border-color:var(--color-border);background:#fff}
.score-panel .eyebrow{color:var(--color-primary);font-size:12px;font-weight:800;letter-spacing:0}
.score-panel h2{margin:5px 0 0;color:var(--color-text);font-size:20px}
.overall-score{color:var(--color-primary)}
.score-notice{color:var(--color-text-secondary)}
.score-list div{border-bottom-color:var(--color-border)}
.score-list dt{color:var(--color-text-secondary)}
.score-list dd{color:var(--color-text);font-family:inherit}
.score-panel :deep(.radar-grid polygon),.score-panel :deep(.radar-grid line){stroke:#d8e2f1}
.score-panel :deep(.radar-grid polygon:nth-child(even)){fill:rgba(234,241,255,.48)}
.score-panel :deep(.radar-value-shape){fill:rgba(37,99,217,.16);stroke:var(--color-primary)}
.score-panel :deep(.radar-value-dot){fill:var(--color-primary)}
.score-panel :deep(text){fill:var(--color-text-secondary)}
</style>
