<script setup lang="ts">
import { computed } from "vue";
import type { BatchSelection } from "./BatchLessonSelector.vue";

export interface BatchProgressItem {
  lessonId: string;
  versionId: string;
  status: string;
  score?: number | null;
  annotationId?: string;
}
export interface BatchProgressState {
  status: string;
  total: number;
  completed: number;
  succeeded: number;
  failed: number;
  items?: BatchProgressItem[];
}
const props = defineProps<{ selections: BatchSelection[]; state: BatchProgressState }>();
const progress = computed(() => props.state.total > 0 ? Math.min(100, Math.round(props.state.completed / props.state.total * 100)) : 0);
function itemState(selection: BatchSelection) {
  return props.state.items?.find(item => item.lessonId === selection.lessonId && item.versionId === selection.versionId);
}
function label(status?: string) {
  if (status === "COMPLETED") return "已完成";
  if (status === "FAILED") return "失败";
  if (status === "RUNNING") return "评价中";
  if (status === "QUEUED") return "等待";
  return "等待";
}
function symbol(status?: string) {
  if (status === "COMPLETED") return "✓";
  if (status === "FAILED") return "×";
  if (status === "RUNNING") return "●";
  return "○";
}
function tone(status?: string) {
  if (status === "COMPLETED") return "complete";
  if (status === "FAILED") return "error";
  if (status === "RUNNING" || status === "QUEUED") return "active";
  return "neutral";
}
</script>

<template>
  <section class="batch-progress v2-card" aria-live="polite">
    <div class="progress-heading">
      <div><span>评价进度</span><h2>批量评价进行中</h2><p>{{ state.completed }} / {{ state.total }} 已完成</p></div>
      <strong>{{ progress }}%</strong>
    </div>
    <div class="progress-track"><span :style="{ width: `${progress}%` }" /></div>
    <div class="progress-list">
      <article v-for="selection in selections" :key="`${selection.lessonId}:${selection.versionId}`">
        <span class="progress-symbol" :class="`progress-symbol--${tone(itemState(selection)?.status)}`">{{ symbol(itemState(selection)?.status) }}</span>
        <div><strong>{{ selection.lessonTitle }}</strong><small>V{{ selection.versionNumber }}</small></div>
        <span class="v2-status" :class="`v2-status--${tone(itemState(selection)?.status)}`">{{ label(itemState(selection)?.status) }}</span>
      </article>
    </div>
  </section>
</template>

<style scoped>
.batch-progress{padding:22px}.progress-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:18px}.progress-heading span{color:var(--color-primary);font-size:12px;font-weight:800}.progress-heading h2{margin:5px 0 4px;font-size:21px}.progress-heading p{margin:0;color:var(--color-text-secondary)}.progress-heading>strong{color:var(--color-primary);font-size:26px}.progress-track{height:8px;margin:18px 0 16px;overflow:hidden;border-radius:999px;background:#e7eef9}.progress-track span{display:block;height:100%;border-radius:inherit;background:var(--color-primary);transition:width .25s ease}.progress-list{display:grid;gap:8px}.progress-list article{display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:11px;padding:10px 12px;border-top:1px solid #edf1f7}.progress-list article:first-child{border-top:0}.progress-list article>div{display:flex;align-items:center;gap:9px;min-width:0}.progress-list strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}.progress-list small{flex:none;color:var(--color-text-muted)}.progress-symbol{display:grid;place-items:center;width:27px;height:27px;border-radius:50%;font-size:13px;font-weight:800}.progress-symbol--complete{color:var(--color-primary);background:var(--color-primary-soft)}.progress-symbol--active{color:var(--color-primary);background:#eef4ff}.progress-symbol--error{color:var(--color-danger);background:var(--color-danger-soft)}.progress-symbol--neutral{color:var(--color-text-muted);background:var(--color-surface-soft)}
@media(max-width:620px){.progress-heading{align-items:flex-start}.progress-list article{grid-template-columns:30px minmax(0,1fr)}.progress-list article>.v2-status{grid-column:2;justify-self:start}.progress-list article>div{align-items:flex-start;flex-direction:column;gap:2px}}
</style>
