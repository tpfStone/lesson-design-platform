<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import type { NavigationState } from "../features/navigation/api";
import { bridgeRequest, contentHash, type BindingContext, type WritebackResult } from "../features/navigation/bridge";
import { useWorkflowStore } from "../stores/workflow";

const props = defineProps<{ state: NavigationState; disabled?: boolean }>();
const workflow = useWorkflowStore();
const binding = ref<BindingContext | null>(null);
const saved = ref<WritebackResult | null>(null);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
let disposed = false;
let loadSequence = 0;

onBeforeUnmount(() => { disposed = true; loadSequence++; });
const linked = computed(() => Boolean(binding.value?.lessonId));
const unchanged = computed(() => linked.value && binding.value?.currentContent === props.state.lesson_plan.current_content);
const nextVersion = computed(() => (binding.value?.currentVersionNumber ?? 0) + 1);
const buttonText = computed(() => saving.value
  ? "正在保存……"
  : !linked.value
    ? "暂不可保存"
    : unchanged.value
      ? "确认保留当前版本"
      : `保存为 V${nextVersion.value}`);

async function loadBinding() {
  const sessionId = props.state.session.id;
  const sequence = ++loadSequence;
  loading.value = true;
  error.value = "";
  try {
    const result = await bridgeRequest<BindingContext>(`/sessions/${sessionId}/binding`);
    if (!disposed && sequence === loadSequence && props.state.session.id === sessionId) binding.value = result;
  } catch (reason) {
    if (!disposed && sequence === loadSequence) error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    if (!disposed && sequence === loadSequence) loading.value = false;
  }
}

watch(() => props.state.session.id, () => {
  saved.value = null;
  binding.value = null;
  void loadBinding();
}, { immediate: true });

async function save() {
  if (saving.value || loading.value || props.disabled || !binding.value) return;
  saving.value = true;
  error.value = "";
  const snapshot = props.state;
  try {
    const result = await bridgeRequest<WritebackResult>(`/sessions/${snapshot.session.id}/writeback`, {
      expectedVersionId: binding.value.currentVersionId,
      roundId: snapshot.round.id,
      expectedContentSha256: await contentHash(snapshot.lesson_plan.current_content),
    });
    if (!disposed && props.state.session.id === snapshot.session.id) {
      saved.value = result;
      if (workflow.activeRun?.lessonId === result.lessonId && workflow.currentStep?.id === "F4") {
        workflow.updateVersion(result.versionId, result.versionNumber);
        if (result.nativeStatus === "TERMINATED") workflow.completeStep("F4");
      }
      await loadBinding();
    }
  } catch (reason) {
    if (!disposed && props.state.session.id === snapshot.session.id) error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section class="transfer-panel v2-card" aria-label="保存协同共析结果">
    <div class="transfer-heading">
      <div>
        <span class="transfer-label">保存版本</span>
        <h2>把本次修订保存到“我的教案”</h2>
        <p v-if="loading">正在读取当前教案版本……</p>
        <p v-else-if="linked">《{{ binding?.title }}》 · 本次输入 V{{ binding?.sourceVersionNumber }} · 当前正式版本 V{{ binding?.currentVersionNumber }}</p>
        <p v-else>当前会话尚未找到平台教案关联，请先确认会话来源。</p>
      </div>
      <div class="transfer-actions">
        <button type="button" class="save-button" :disabled="loading || saving || disabled || !binding || !linked" @click="save">{{ buttonText }}</button>
        <button type="button" class="refresh-button" :disabled="loading || saving || disabled" @click="loadBinding">刷新版本</button>
      </div>
    </div>
    <p class="transfer-note">保存后不会覆盖旧版本；如果正文发生变化，将新增一个可追溯版本供后续任务继续使用。</p>
    <details v-if="linked" class="compare">
      <summary>查看保存前后的正文</summary>
      <div class="compare-grid">
        <div><h3>当前正式版本 V{{ binding?.currentVersionNumber }}</h3><pre>{{ binding?.currentContent }}</pre></div>
        <div><h3>本次共析修订</h3><pre>{{ state.lesson_plan.current_content }}</pre></div>
      </div>
    </details>
    <p v-if="saved" class="save-success" role="status">
      {{ saved.alreadySaved ? "这份修订已经保存过" : "保存成功" }}：当前教案为 V{{ saved.versionNumber }}。
      <RouterLink :to="{ path: '/lessons/' + saved.lessonId, query: { version: saved.versionId } }">查看该版本 →</RouterLink>
    </p>
    <p v-if="error" class="save-error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.transfer-panel{margin-top:26px;padding:22px 24px;border-color:var(--color-primary-border);background:#f7f9ff;color:var(--color-text)}
.transfer-heading{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:18px}.transfer-label{color:var(--color-primary);font-size:12px;font-weight:800}
h2{margin:6px 0 7px;font-size:20px}p{margin:4px 0;color:var(--color-text-secondary);font-size:13px;line-height:1.7}.transfer-actions{display:flex;flex-wrap:wrap;gap:10px}
button{min-height:40px;padding:0 15px;border-radius:var(--radius-md);font:inherit;font-size:13px;font-weight:700;cursor:pointer}.save-button{border:1px solid var(--color-primary);color:#fff;background:var(--color-primary)}.refresh-button{border:1px solid var(--color-primary-border);color:var(--color-primary);background:#fff}button:disabled{opacity:.52;cursor:not-allowed}
.transfer-note{margin-top:12px}.compare{margin-top:14px;color:var(--color-text-secondary);font-size:13px}.compare summary{cursor:pointer;font-weight:700}.compare-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:13px}.compare-grid>div{min-width:0;padding:15px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff}.compare-grid h3{margin:0 0 10px;font-size:13px;color:var(--color-text)}pre{max-height:280px;margin:0;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-family:inherit;font-size:13px;line-height:1.8;color:var(--color-text-secondary)}
.save-success{margin-top:14px;padding:11px 13px;border:1px solid var(--color-primary-border);border-radius:var(--radius-md);color:var(--color-primary);background:var(--color-primary-soft)}.save-success a{margin-left:8px;color:var(--color-primary);font-weight:700}.save-error{margin-top:12px;color:var(--color-danger)}
@media(max-width:680px){.compare-grid{grid-template-columns:1fr}.transfer-panel{padding:18px}.transfer-actions{width:100%}.transfer-actions button{flex:1}}
</style>
