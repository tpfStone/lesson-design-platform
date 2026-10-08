<script setup lang="ts">
withDefaults(defineProps<{ as?: string; padded?: boolean }>(), { as: "section", padded: true });
</script>

<template>
  <component :is="as" class="v2-card" :class="{ 'base-card--padded': padded }"><slot /></component>
</template>

<style scoped>.base-card--padded { padding: clamp(18px, 2.5vw, 28px); }</style>
