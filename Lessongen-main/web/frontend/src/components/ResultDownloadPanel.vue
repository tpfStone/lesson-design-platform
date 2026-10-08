<script setup lang="ts">
export interface DownloadFile { key: string; label: string; href: string; filename?: string }
defineProps<{ files: DownloadFile[]; title?: string; description?: string }>();
</script>
<template>
  <section v-if="files.length" class="result-downloads" aria-label="结果文件">
    <div class="download-heading"><div><h2>{{ title || "结果文件" }}</h2><p>{{ description || "本次任务结果已保存，可按需下载。" }}</p></div></div>
    <ul><li v-for="file in files" :key="file.key"><span>{{ file.label }}</span><a class="v2-button v2-button--secondary" :href="file.href" :download="file.filename || ''">下载</a></li></ul>
  </section>
</template>
<style scoped>
.result-downloads { margin-top:32px; padding-top:24px; border-top:1px solid var(--color-border); }.download-heading h2 { margin:0; font-size:20px; }.download-heading p { margin:7px 0 0; color:var(--color-text-secondary); }
.result-downloads ul { margin:18px 0 0; padding:0; list-style:none; }.result-downloads li { display:flex; align-items:center; justify-content:space-between; gap:16px; min-height:58px; border-top:1px solid #edf1f7; }
</style>
