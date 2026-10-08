<script setup lang="ts">
withDefaults(defineProps<{ open: boolean; title: string; description: string; confirmText?: string; cancelText?: string; busy?: boolean }>(), { confirmText: "确认", cancelText: "取消", busy: false });
defineEmits<{ confirm: []; cancel: [] }>();
</script>
<template>
  <Teleport to="body"><div v-if="open" class="dialog-backdrop" @click.self="$emit('cancel')">
    <section class="confirm-dialog" role="dialog" aria-modal="true" :aria-label="title">
      <h2>{{ title }}</h2><p>{{ description }}</p><div class="dialog-actions">
        <button type="button" class="v2-button v2-button--secondary" :disabled="busy" @click="$emit('cancel')">{{ cancelText }}</button>
        <button type="button" class="v2-button v2-button--primary" :disabled="busy" @click="$emit('confirm')">{{ busy ? "正在处理……" : confirmText }}</button>
      </div>
    </section>
  </div></Teleport>
</template>
<style scoped>
.dialog-backdrop { position:fixed; inset:0; z-index:300; display:grid; place-items:center; padding:20px; background:rgba(19,39,70,.42); }
.confirm-dialog { width:min(440px,100%); padding:26px; border-radius:var(--radius-lg); background:#fff; box-shadow:0 22px 70px rgba(20,39,70,.24); }
.confirm-dialog h2 { margin:0; color:var(--color-text); font-size:21px; }.confirm-dialog p { color:var(--color-text-secondary); line-height:1.7; }.dialog-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:22px; }
</style>
