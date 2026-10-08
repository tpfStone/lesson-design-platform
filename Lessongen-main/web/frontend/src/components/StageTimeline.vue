<script setup lang="ts">
import { computed } from "vue";
import type { JobDetail, JobEvent } from "../types/api";
const props = defineProps<{ job: JobDetail; events: JobEvent[] }>();
const generateStages = [
  ["queued", "任务入队"],
  ["design_architect", "设计路线"],
  ["writer", "形成初稿"],
  ["judge", "内部初评"],
  ["critics", "三类批评"],
  ["validator", "意见校验"],
  ["rewriter", "定向改写"],
  ["verifier", "落实核验"],
  ["finalize", "整理产物"],
];
const optimizeStages = [
  ["queued", "任务入队"],
  ["docx_security_check", "Word 安全解析"],
  ["docx_normalize", "识别原稿内容"],
  ["judge", "原稿内部评估"],
  ["critics", "三类批评"],
  ["validator", "意见校验"],
  ["rewriter", "定向改写"],
  ["verifier", "落实核验"],
  ["optimization_pairwise_compare", "原稿与修改稿对照"],
  ["finalize", "整理产物"],
];
const aliases: Record<string, string> = {
  dispatching: "queued",
  preprocessing: "docx_security_check",
  run: "queued",
  bootstrap: "queued",
  evaluation_router: "judge",
  critique_aggregator: "critics",
  validation_router: "validator",
  exporting: "finalize",
};
const canonical = (stage: string) => aliases[stage] || stage;
const stages = computed(() =>
  props.job.mode === "OPTIMIZE" ? optimizeStages : generateStages,
);
const current = computed(() => canonical(props.job.currentStage));
const currentIndex = computed(() =>
  stages.value.findIndex((stage) => stage[0] === current.value),
);
const observed = computed(
  () => new Set(props.events.map((item) => canonical(item.stage))),
);
const state = (stage: string, index: number) => {
  if (stage === current.value) return "active";
  if (observed.value.has(stage)) return "seen";
  if (currentIndex.value >= 0 && index < currentIndex.value) return "passed";
  return "waiting";
};
</script>
<template>
  <ol class="stage-timeline" aria-label="教案任务进度">
    <li
      v-for="(stage, index) in stages"
      :key="stage[0]"
      :class="state(stage[0], index)"
    >
      <span class="stage-dot" aria-hidden="true">{{
        state(stage[0], index) === "seen" ? "✓" : index + 1
      }}</span>
      <div>
        <strong>{{ stage[1] }}</strong
        ><small v-if="state(stage[0], index) === 'active'">当前阶段</small>
        <small v-else-if="state(stage[0], index) === 'seen'">本次已运行</small>
        <small v-else-if="state(stage[0], index) === 'passed'"
          >已越过，未保存逐步记录</small
        >
      </div>
    </li>
  </ol>
</template>
