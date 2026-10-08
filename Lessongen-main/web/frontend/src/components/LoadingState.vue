<script setup lang="ts">withDefaults(defineProps<{ message?: string }>(), { message: "正在加载，请稍候……" });</script>
<template><div class="state-box" role="status"><span class="state-spinner" aria-hidden="true" />{{ message }}</div></template>
<style scoped>
.state-box { display:flex; align-items:center; justify-content:center; gap:10px; min-height:150px; color:var(--color-text-secondary); }
.state-spinner { width:19px; height:19px; border:2px solid var(--color-primary-border); border-top-color:var(--color-primary); border-radius:50%; animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
</style>
