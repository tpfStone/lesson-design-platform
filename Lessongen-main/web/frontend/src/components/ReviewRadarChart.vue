<script setup lang="ts">
import { computed } from "vue";

export interface RadarDimension {
  name: string;
  score: number;
  maximum: number;
  grade?: string;
}

const props = defineProps<{ dimensions: RadarDimension[] }>();
const center = 210;
const radius = 132;
const count = computed(() => Math.max(props.dimensions.length, 1));
const angle = (index: number) => -Math.PI / 2 + index * Math.PI * 2 / count.value;
const point = (index: number, distance: number) => ({
  x: center + Math.cos(angle(index)) * distance,
  y: center + Math.sin(angle(index)) * distance,
});
const polygon = (distance: number) => props.dimensions
  .map((_, index) => { const p = point(index, distance); return `${p.x},${p.y}`; })
  .join(" ");
const axes = computed(() => props.dimensions.map((dimension, index) => {
  const rate = dimension.maximum > 0 ? Math.max(0, Math.min(1, dimension.score / dimension.maximum)) : 0;
  return {
    ...dimension,
    number: index + 1,
    edge: point(index, radius),
    label: point(index, 164),
    value: point(index, rate * radius),
    rate: Math.round(rate * 100),
  };
}));
const shape = computed(() => axes.value.map(axis => `${axis.value.x},${axis.value.y}`).join(" "));
</script>

<template>
  <section class="review-radar v2-card" aria-label="十二维评分雷达图">
    <div class="chart-heading">
      <div><h3>十二维雷达图</h3><p>按各二级维度满分归一化展示，详细分数与等级见右侧。</p></div>
      <span>12 个二级维度</span>
    </div>
    <div class="chart-layout">
      <svg viewBox="0 0 420 420" role="img" aria-label="十二个二级维度评分雷达图，详细分数见右侧列表">
        <title>十二维评分雷达图</title>
        <g class="grid">
          <polygon v-for="rate in [0.25, 0.5, 0.75, 1]" :key="rate" :points="polygon(radius * rate)" />
          <line v-for="axis in axes" :key="axis.number" :x1="center" :y1="center" :x2="axis.edge.x" :y2="axis.edge.y" />
        </g>
        <polygon class="value-area" :points="shape" />
        <g v-for="axis in axes" :key="axis.number">
          <circle class="value-dot" :cx="axis.value.x" :cy="axis.value.y" r="4" />
          <text :x="axis.label.x" :y="axis.label.y" text-anchor="middle" dominant-baseline="middle">{{ axis.number }}</text>
        </g>
      </svg>
      <ol class="legend">
        <li v-for="axis in axes" :key="axis.number">
          <span class="number">{{ axis.number }}</span>
          <span class="name">{{ axis.name }}</span>
          <strong>{{ axis.score }} / {{ axis.maximum }}</strong>
          <span v-if="axis.grade" class="grade" :class="`grade--${axis.grade.toLowerCase()}`">{{ axis.grade }}</span>
          <small>{{ axis.rate }}%</small>
        </li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.review-radar{padding:24px}.chart-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:12px}.chart-heading h3{margin:0 0 5px;color:var(--color-text);font-size:20px}.chart-heading p{margin:0;color:var(--color-text-secondary);font-size:13px;line-height:1.6}.chart-heading>span{flex:none;padding:5px 9px;border-radius:999px;color:var(--color-primary);background:var(--color-primary-soft);font-size:12px;font-weight:700}.chart-layout{display:grid;grid-template-columns:minmax(310px,440px) minmax(0,1fr);gap:26px;align-items:center}svg{display:block;width:100%;max-width:430px;margin:auto}.grid polygon,.grid line{fill:none;stroke:#d7e2f3;stroke-width:1}.value-area{fill:rgba(37,99,217,.16);stroke:var(--color-primary);stroke-width:2.5}.value-dot{fill:var(--color-primary)}text{fill:#355d9d;font:700 13px "Microsoft YaHei",sans-serif}.legend{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 14px}.legend li{display:grid;grid-template-columns:26px minmax(0,1fr) auto 30px 40px;gap:7px;align-items:center;min-width:0;color:var(--color-text-secondary);font-size:12px}.number{display:grid;place-items:center;width:23px;height:23px;border-radius:50%;color:var(--color-primary);background:var(--color-primary-soft);font-weight:700}.name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.legend strong{white-space:nowrap;color:var(--color-text)}.legend small{text-align:right;color:var(--color-text-muted)}.grade{display:grid;place-items:center;width:27px;height:23px;border-radius:999px;font-size:11px;font-weight:800}.grade--a{color:var(--color-primary);background:var(--color-primary-soft)}.grade--b{color:var(--color-attention);background:var(--color-attention-soft)}.grade--c{color:var(--color-danger);background:var(--color-danger-soft)}
@media(max-width:900px){.chart-layout{grid-template-columns:1fr}.legend{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:620px){.review-radar{padding:17px}.chart-heading{flex-direction:column}.legend{grid-template-columns:1fr}.legend li{grid-template-columns:26px minmax(0,1fr) auto 30px 40px}}
</style>
