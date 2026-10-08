<script setup lang="ts">
import { computed, ref } from "vue";

export interface ComparisonDimension { name: string; score: number; maximum: number; grade?: string }
export interface ComparisonSeries { id: string; label: string; total?: number | null; dimensions: ComparisonDimension[] }
const props = defineProps<{ series: ComparisonSeries[] }>();
const mode = ref<"radar" | "bar">("radar");
const center = 220;
const radius = 136;
const dimensionNames = computed(() => props.series[0]?.dimensions.map(item => item.name) || []);
const count = computed(() => Math.max(dimensionNames.value.length, 1));
const colors = ["#2563d9", "#5b82df", "#7b6fd6", "#2d7fc6", "#5b6d9b"];
const dashes = ["0", "7 4", "3 3", "10 4 2 4", "2 5"];
const angle = (index: number) => -Math.PI / 2 + index * Math.PI * 2 / count.value;
const point = (index: number, distance: number) => ({ x: center + Math.cos(angle(index)) * distance, y: center + Math.sin(angle(index)) * distance });
const polygon = (distance: number) => dimensionNames.value.map((_, index) => { const p = point(index, distance); return `${p.x},${p.y}`; }).join(" ");
const axes = computed(() => dimensionNames.value.map((name, index) => ({ name, number: index + 1, edge: point(index, radius), label: point(index, 171) })));
function shape(series: ComparisonSeries) {
  return dimensionNames.value.map((name, index) => {
    const item = series.dimensions.find(dimension => dimension.name === name);
    const rate = item && item.maximum > 0 ? Math.max(0, Math.min(1, item.score / item.maximum)) : 0;
    const p = point(index, rate * radius);
    return `${p.x},${p.y}`;
  }).join(" ");
}
function rate(series: ComparisonSeries, name: string) {
  const item = series.dimensions.find(dimension => dimension.name === name);
  return item && item.maximum > 0 ? Math.max(0, Math.min(100, item.score / item.maximum * 100)) : 0;
}
function dimension(series: ComparisonSeries, name: string) { return series.dimensions.find(item => item.name === name); }
</script>

<template>
  <section class="comparison-chart v2-card">
    <div class="chart-toolbar">
      <div><span>横向对比</span><h2>十二维表现对比</h2><p>雷达图用于观察整体轮廓，柱状图用于精确比较各维得分率。</p></div>
      <div class="chart-tabs" role="tablist" aria-label="对比图表类型">
        <button type="button" :class="{ active: mode === 'radar' }" @click="mode = 'radar'">雷达图</button>
        <button type="button" :class="{ active: mode === 'bar' }" @click="mode = 'bar'">柱状图</button>
      </div>
    </div>

    <div class="series-legend">
      <span v-for="(item, index) in series" :key="item.id"><i :style="{ background: colors[index % colors.length] }" />{{ item.label }}<strong v-if="typeof item.total === 'number'">{{ item.total }}</strong></span>
    </div>

    <div v-if="mode === 'radar'" class="radar-layout">
      <svg viewBox="0 0 440 440" role="img" aria-label="多份教案十二维雷达图">
        <title>多份教案十二维雷达图</title>
        <g class="grid"><polygon v-for="gridRate in [0.25,0.5,0.75,1]" :key="gridRate" :points="polygon(radius * gridRate)" /><line v-for="axis in axes" :key="axis.number" :x1="center" :y1="center" :x2="axis.edge.x" :y2="axis.edge.y" /></g>
        <polygon v-for="(item,index) in series" :key="item.id" class="series-shape" :points="shape(item)" :style="{ stroke: colors[index % colors.length], strokeDasharray: dashes[index % dashes.length] }" />
        <g v-for="axis in axes" :key="axis.number"><text :x="axis.label.x" :y="axis.label.y" text-anchor="middle" dominant-baseline="middle">{{ axis.number }}</text></g>
      </svg>
      <ol class="dimension-legend"><li v-for="axis in axes" :key="axis.number"><span>{{ axis.number }}</span>{{ axis.name }}</li></ol>
    </div>

    <div v-else class="bar-chart">
      <article v-for="name in dimensionNames" :key="name" class="bar-group">
        <strong>{{ name }}</strong>
        <div class="bars">
          <div v-for="(item,index) in series" :key="item.id" class="bar-row">
            <span>{{ item.label }}</span><div class="bar-track"><i :style="{ width: `${rate(item,name)}%`, background: colors[index % colors.length] }" /></div><small><template v-if="dimension(item,name)">{{ dimension(item,name)?.score }} / {{ dimension(item,name)?.maximum }}</template><template v-else>—</template></small>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.comparison-chart{padding:22px}.chart-toolbar{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.chart-toolbar span{color:var(--color-primary);font-size:12px;font-weight:800}.chart-toolbar h2{margin:5px 0 5px;font-size:21px}.chart-toolbar p{margin:0;color:var(--color-text-secondary);font-size:13px}.chart-tabs{display:flex;flex:none;padding:3px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:var(--color-surface-soft)}.chart-tabs button{min-height:34px;padding:0 13px;border:0;border-radius:6px;color:var(--color-text-secondary);background:transparent;font-weight:700;cursor:pointer}.chart-tabs button.active{color:var(--color-primary);background:#fff;box-shadow:0 2px 8px rgba(35,64,112,.08)}.series-legend{display:flex;flex-wrap:wrap;gap:10px 18px;margin:18px 0}.series-legend>span{display:inline-flex;align-items:center;gap:7px;color:var(--color-text-secondary);font-size:12px}.series-legend i{width:18px;height:3px;border-radius:99px}.series-legend strong{color:var(--color-text)}.radar-layout{display:grid;grid-template-columns:minmax(320px,500px) minmax(0,1fr);gap:28px;align-items:center}svg{display:block;width:100%;max-width:480px;margin:auto}.grid polygon,.grid line{fill:none;stroke:#d7e2f3;stroke-width:1}.series-shape{fill:none;stroke-width:2.6;stroke-linejoin:round}text{fill:#355d9d;font:700 13px "Microsoft YaHei",sans-serif}.dimension-legend{list-style:none;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 16px;margin:0;padding:0}.dimension-legend li{display:flex;align-items:center;gap:8px;color:var(--color-text-secondary);font-size:13px}.dimension-legend span{display:grid;place-items:center;width:23px;height:23px;border-radius:50%;color:var(--color-primary);background:var(--color-primary-soft);font-size:11px;font-weight:800}.bar-chart{display:grid;gap:16px}.bar-group{display:grid;grid-template-columns:120px minmax(0,1fr);gap:18px;padding-top:14px;border-top:1px solid #edf1f7}.bar-group>strong{font-size:13px}.bars{display:grid;gap:7px}.bar-row{display:grid;grid-template-columns:minmax(110px,180px) minmax(120px,1fr) 70px;align-items:center;gap:10px;color:var(--color-text-secondary);font-size:12px}.bar-row>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.bar-track{height:8px;overflow:hidden;border-radius:999px;background:#e8eef8}.bar-track i{display:block;height:100%;border-radius:inherit}.bar-row small{text-align:right;color:var(--color-text)}
@media(max-width:820px){.chart-toolbar{flex-direction:column}.radar-layout{grid-template-columns:1fr}.dimension-legend{grid-template-columns:repeat(2,minmax(0,1fr))}.bar-group{grid-template-columns:1fr}.bar-row{grid-template-columns:110px minmax(100px,1fr) 65px}}
@media(max-width:560px){.dimension-legend{grid-template-columns:1fr}.bar-row{grid-template-columns:1fr}.bar-row small{text-align:left}}
</style>
