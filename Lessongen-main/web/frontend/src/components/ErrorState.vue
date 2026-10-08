<script setup lang="ts">
defineProps<{ title?: string; message: string; technicalDetail?: string }>();
defineEmits<{ retry: [] }>();
</script>
<template>
  <section class="error-state" role="alert">
    <strong>{{ title || "暂时无法完成操作" }}</strong><p>{{ message }}</p>
    <button v-if="$attrs.onRetry" type="button" class="v2-button v2-button--secondary" @click="$emit('retry')">重新尝试</button>
    <details v-if="technicalDetail"><summary>查看技术详情</summary><pre>{{ technicalDetail }}</pre></details>
  </section>
</template>
<style scoped>
.error-state { padding:18px; border:1px solid #efc8ca; border-radius:var(--radius-md); background:var(--color-danger-soft); color:var(--color-danger); }
.error-state p { margin:7px 0 13px; }.error-state details { margin-top:14px; font-size:12px; }.error-state pre { overflow:auto; white-space:pre-wrap; }
</style>
