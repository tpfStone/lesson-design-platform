<script setup lang="ts">
withDefaults(defineProps<{ title: string; subtitle?: string; status?: string; tone?: "complete" | "attention" | "error" | "neutral" }>(), { subtitle: "", status: "", tone: "neutral" });
</script>
<template><header class="result-header"><div><small>任务结果</small><h2>{{ title }}</h2><p v-if="subtitle">{{ subtitle }}</p></div><span v-if="status" class="v2-status" :class="`v2-status--${tone}`">{{ status }}</span></header></template>
<style scoped>.result-header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.result-header small{color:var(--color-primary);font-weight:700}.result-header h2{margin:5px 0 0}.result-header p{margin:7px 0 0;color:var(--color-text-secondary)}</style>
