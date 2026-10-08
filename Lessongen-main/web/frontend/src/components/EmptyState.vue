<script setup lang="ts">withDefaults(defineProps<{ title?: string; description?: string }>(), { title: "暂无内容", description: "完成相关任务后，结果会显示在这里。" });</script>
<template><div class="empty-state"><span aria-hidden="true">＋</span><strong>{{ title }}</strong><p>{{ description }}</p><slot /></div></template>
<style scoped>
.empty-state { display:grid; justify-items:center; min-height:180px; padding:32px; text-align:center; color:var(--color-text-secondary); }
.empty-state span { display:grid; place-items:center; width:38px; height:38px; border-radius:50%; color:var(--color-primary); background:var(--color-primary-soft); font-size:22px; }
.empty-state strong { margin-top:14px; color:var(--color-text); font-size:17px; }.empty-state p { margin:7px 0 18px; }
</style>
