<script setup lang="ts">
import { onMounted, watch } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const titles: Record<string, string> = {
  "platform-dashboard": "工作台",
  "lesson-space": "我的教案",
  "lesson-detail": "教案详情",
  workflows: "工作流",
  review: "智能评审",
  design: "教案生成与优化",
  "lesson-annotate": "智能评审",
  generate: "教案生成",
  optimize: "教案优化",
  simulate: "课堂模拟",
  "navigation-entry": "协同共析",
  "f4-navigation-workbench": "协同共析",
  job: "任务详情",
};
function updateTitle() {
  document.title = `${titles[String(route.name)] || "工作台"} · AI 教学设计平台`;
}
onMounted(updateTitle);
watch(() => route.name, updateTitle);
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <RouterView />
</template>
