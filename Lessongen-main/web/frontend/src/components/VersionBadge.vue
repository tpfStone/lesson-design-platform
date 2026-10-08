<script setup lang="ts">
defineProps<{ versionNumber: number; source?: string; latest?: boolean }>();
const sourceNames: Record<string, string> = {
  IMPORT_DOCX: "导入原稿", IMPORT_TEXT: "文本创建", MANUAL: "手动修改",
  F1_ANNOTATION: "智能评价后", F2_OPTIMIZATION: "设计修改后", F2_OPTIMIZE: "设计修改后",
  F3_SIMULATION: "课堂推演后", F4_NAVIGATION: "协同共析后",
};
</script>

<template>
  <span class="version-badge">V{{ versionNumber }}<template v-if="source"> · {{ sourceNames[source] || source }}</template><strong v-if="latest">最新</strong></span>
</template>

<style scoped>
.version-badge { display:inline-flex; align-items:center; gap:7px; color:var(--color-text-secondary); font-size:13px; }
.version-badge strong { padding:2px 7px; border-radius:999px; color:var(--color-primary); background:var(--color-primary-soft); font-size:11px; }
</style>
