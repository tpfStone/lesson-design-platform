<script setup lang="ts">
import { computed } from "vue";

export interface BatchResultRow {
  key: string;
  lessonId: string;
  lessonTitle: string;
  versionId: string;
  versionNumber: number;
  annotationId?: string;
  score?: number | null;
  status: string;
}
const props = defineProps<{ rows: BatchResultRow[]; modelValue: string[]; disabled?: boolean; maxCompare?: number }>();
const emit = defineEmits<{ "update:modelValue": [value: string[]] }>();
const max = computed(() => props.maxCompare ?? 5);
function canCompare(row: BatchResultRow) { return row.status === "COMPLETED" && Boolean(row.annotationId); }
function checked(row: BatchResultRow) { return row.annotationId ? props.modelValue.includes(row.annotationId) : false; }
function toggle(row: BatchResultRow) {
  if (!row.annotationId || !canCompare(row) || props.disabled) return;
  if (checked(row)) emit("update:modelValue", props.modelValue.filter(id => id !== row.annotationId));
  else if (props.modelValue.length < max.value) emit("update:modelValue", [...props.modelValue, row.annotationId]);
}
function statusText(status: string) { return status === "COMPLETED" ? "已完成" : status === "FAILED" ? "失败" : status === "RUNNING" ? "评价中" : "等待"; }
function statusTone(status: string) { return status === "COMPLETED" ? "complete" : status === "FAILED" ? "error" : status === "RUNNING" || status === "QUEUED" ? "active" : "neutral"; }
</script>

<template>
  <section class="batch-table v2-card">
    <div class="table-heading"><div><span>批量结果</span><h2>各教案评价结果</h2></div><p>成功结果可进入单份评价页，也可选择 2～{{ max }} 份进行横向对比。</p></div>
    <div class="table-scroll">
      <table>
        <thead><tr><th class="select-col">选择</th><th>教案</th><th>版本</th><th>总分</th><th>状态</th><th aria-label="操作" /></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="row.key">
            <td class="select-col"><input v-if="canCompare(row)" type="checkbox" :checked="checked(row)" :disabled="disabled || (!checked(row) && modelValue.length >= max)" :aria-label="`选择 ${row.lessonTitle} V${row.versionNumber} 进行对比`" @change="toggle(row)"><span v-else>—</span></td>
            <td><strong>{{ row.lessonTitle }}</strong></td>
            <td>V{{ row.versionNumber }}</td>
            <td>{{ typeof row.score === "number" ? row.score : "—" }}</td>
            <td><span class="v2-status" :class="`v2-status--${statusTone(row.status)}`">{{ statusText(row.status) }}</span></td>
            <td class="action-col"><RouterLink v-if="row.status === 'COMPLETED' && row.annotationId" :to="{ path: `/lessons/${row.lessonId}/annotate`, query: { version: row.versionId, annotation: row.annotationId } }">查看结果 →</RouterLink></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.batch-table{overflow:hidden}.table-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;padding:22px 22px 16px}.table-heading span{color:var(--color-primary);font-size:12px;font-weight:800}.table-heading h2{margin:5px 0 0;font-size:21px}.table-heading p{max-width:520px;margin:0;color:var(--color-text-secondary);font-size:13px;line-height:1.6}.table-scroll{overflow:auto;border-top:1px solid var(--color-border)}table{width:100%;border-collapse:collapse;min-width:760px}th,td{padding:14px 16px;border-bottom:1px solid #edf1f7;text-align:left;font-size:13px}th{color:var(--color-text-secondary);background:#f8faff;font-size:12px}td strong{font-size:14px}.select-col{width:68px;text-align:center}.select-col input{width:16px;height:16px;accent-color:var(--color-primary)}.action-col{text-align:right}.action-col a{color:var(--color-primary);font-weight:700;white-space:nowrap}tbody tr:last-child td{border-bottom:0}@media(max-width:700px){.table-heading{align-items:flex-start;flex-direction:column}}
</style>
