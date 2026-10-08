<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  rows: Array<{ key: string; label: string; score: number }>;
}>();
const center = 180;
const radius = 112;
const labelRadius = 148;
const angle = (index: number) => -Math.PI / 2 + (index * Math.PI * 2) / 8;
const point = (index: number, distance: number) => ({
  x: center + Math.cos(angle(index)) * distance,
  y: center + Math.sin(angle(index)) * distance,
});
const pointString = (distance: number) =>
  props.rows
    .map((_, index) => {
      const value = point(index, distance);
      return `${value.x},${value.y}`;
    })
    .join(" ");
const rings = [2, 4, 6, 8, 10].map((value) => ({
  value,
  points: pointString((value / 10) * radius),
}));
const axes = computed(() =>
  props.rows.map((row, index) => ({
    ...row,
    edge: point(index, radius),
    labelPoint: point(index, labelRadius),
    value: point(index, (Math.min(10, Math.max(0, row.score)) / 10) * radius),
  })),
);
const shape = computed(() =>
  axes.value.map((row) => `${row.value.x},${row.value.y}`).join(" "),
);
</script>

<template>
  <svg
    class="radar-svg"
    viewBox="0 0 360 360"
    role="img"
    aria-label="八维内部质量示意图；具体分数见页面数值表"
  >
    <title>八维内部质量示意图</title>
    <g class="radar-grid">
      <polygon v-for="ring in rings" :key="ring.value" :points="ring.points" />
      <line
        v-for="row in axes"
        :key="row.key"
        :x1="center"
        :y1="center"
        :x2="row.edge.x"
        :y2="row.edge.y"
      />
    </g>
    <polygon class="radar-value-shape" :points="shape" />
    <g v-for="row in axes" :key="row.key">
      <circle
        class="radar-value-dot"
        :cx="row.value.x"
        :cy="row.value.y"
        r="3.5"
      >
        <title>{{ row.label }} {{ row.score.toFixed(1) }} / 10</title>
      </circle>
      <text
        :x="row.labelPoint.x"
        :y="row.labelPoint.y"
        text-anchor="middle"
        dominant-baseline="middle"
      >
        {{ row.label }}
      </text>
    </g>
  </svg>
</template>

<style scoped>
.radar-svg {
  display: block;
  width: 100%;
  height: 285px;
  overflow: visible;
}
.radar-grid polygon,
.radar-grid line {
  fill: none;
  stroke: #d9dfdc;
  stroke-width: 1;
}
.radar-grid polygon:nth-child(even) {
  fill: rgba(244, 241, 232, 0.42);
}
.radar-value-shape {
  fill: rgba(29, 148, 141, 0.19);
  stroke: #147d78;
  stroke-width: 2.5;
  transform-origin: 50% 50%;
  animation: reveal-shape 360ms cubic-bezier(0.22, 1, 0.36, 1) both;
}
.radar-value-dot {
  fill: #147d78;
}
text {
  fill: #334b59;
  font-size: 12px;
  font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif;
}
@keyframes reveal-shape {
  from {
    opacity: 0;
    transform: scale(0.92);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
@media (prefers-reduced-motion: reduce) {
  .radar-value-shape {
    animation: none;
  }
}
</style>
