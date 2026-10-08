<script setup lang="ts">
import { computed } from "vue";
import type { JobStatus } from "../types/api";
const props = defineProps<{ status: JobStatus }>();
const label = computed(
  () =>
    ({
      QUEUED: "排队中",
      DISPATCHING: "准备中",
      PREPROCESSING: "解析原稿",
      RUNNING: "生成中",
      EXPORTING: "整理文件",
      COMPLETED: "已完成",
      NEEDS_HUMAN: "待教师复核",
      FAILED: "未完成",
    })[props.status],
);
</script>
<template>
  <span class="status-pill" :class="`status-${status.toLowerCase()}`"
    ><i />{{ label }}</span
  >
</template>
