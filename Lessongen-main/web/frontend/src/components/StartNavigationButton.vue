<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { bridgeRequest } from "../features/navigation/bridge";
const props = defineProps<{ lessonId: string; versionId: string; disabled?: boolean; nativeReference?: string | null;
  subject?: string | null; grade?: string | null; topic?: string | null; title?: string | null }>();
const router = useRouter();
const busy = ref(false), error = ref("");
const formOpen = ref(false);
const subject = ref(props.subject || "");
const grade = ref(props.grade || "");
const topic = ref(props.topic || props.title || "");
const keyName = computed(() => `platform.f4.start.${props.lessonId}.${props.versionId}`);
const requestKey = ref("");
const originSession = computed(() => /^f4:([0-9a-f-]{36}):round:/i.exec(props.nativeReference || "")?.[1]);
watch(keyName, key => { requestKey.value = localStorage.getItem(key) || crypto.randomUUID(); error.value = ""; }, { immediate: true });
function start() {
  if (busy.value || props.disabled || !props.versionId) return;
  if (!subject.value.trim() || !grade.value.trim() || !topic.value.trim()) {
    formOpen.value = true;
    return;
  }
  void submit();
}
async function submit() {
  if (busy.value || props.disabled || !props.versionId) return;
  if (!subject.value.trim() || !grade.value.trim() || !topic.value.trim() || topic.value.trim().length > 200) {
    error.value = "请填写学科、年级和不超过 200 字的课题。";
    return;
  }
  busy.value = true; error.value = "";
  const storedKey = keyName.value;
  try {
    localStorage.setItem(storedKey, requestKey.value);
    const result = await bridgeRequest<{ sessionId: string }>(`/lessons/${encodeURIComponent(props.lessonId)}/sessions`, {
      versionId: props.versionId, requestKey: requestKey.value,
      subject: subject.value.trim(), grade: grade.value.trim(), topic: topic.value.trim(),
    });
    formOpen.value = false;
    await router.push({ path: "/platform/navigation", query: { session: result.sessionId } });
    localStorage.removeItem(storedKey);
    requestKey.value = crypto.randomUUID();
  } catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); formOpen.value = true; }
  finally { busy.value = false; }
}
</script>

<template>
  <span class="navigation-start">
    <button type="button" :disabled="busy || disabled || !versionId" @click="start">{{ busy ? "正在创建导航会话…" : "导航修订这个版本 →" }}</button>
    <RouterLink v-if="originSession && !busy" :to="{ path: '/platform/navigation', query: { session: originSession } }">继续来源会话</RouterLink>
    <Teleport to="body"><div v-if="formOpen" class="f4-metadata-backdrop" @click.self="formOpen = false">
      <form class="f4-metadata-dialog" role="dialog" aria-modal="true" aria-label="补全引导修订信息" @submit.prevent="submit">
        <h2>补全教案信息</h2><p>F4 创建会话需要这三项；只用于本次修订，不会修改原教案。</p>
        <label>学科<input v-model="subject" maxlength="100" required placeholder="例如：数学" /></label>
        <label>年级<input v-model="grade" maxlength="100" required placeholder="例如：三年级" /></label>
        <label>课题<input v-model="topic" maxlength="200" required placeholder="例如：小数的加法和减法" /></label>
        <p v-if="error" class="start-error" role="alert">{{ error }}</p>
        <div class="f4-dialog-actions"><button type="button" class="cancel" @click="formOpen = false">取消</button><button type="submit" :disabled="busy">{{ busy ? "正在创建…" : "开始引导修订" }}</button></div>
      </form>
    </div></Teleport>
  </span>
</template>

<style scoped>
.navigation-start { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:flex-end; margin:0; min-width:0; }
button { border:1px solid #3569df; color:#3569df; background:#eff4ff; border-radius:10px; padding:12px 18px; font:inherit; font-weight:650; cursor:pointer; }
button:disabled { opacity:.5; cursor:wait; }
a { color:#456182; font-size:14px; }
.start-error { color:#b23b45; font-size:14px; width:100%; }
.f4-metadata-backdrop { position:fixed; inset:0; z-index:1000; display:grid; place-items:center; padding:20px; background:rgba(18,37,68,.45); }
.f4-metadata-dialog { width:min(440px,100%); display:grid; gap:13px; padding:26px; border:1px solid #dce5f2; border-radius:16px; background:white; box-shadow:0 20px 60px rgba(18,37,68,.2); }
.f4-metadata-dialog h2 { margin:0; color:#172b48; font-size:22px; }
.f4-metadata-dialog p { margin:0; color:#5c6e86; line-height:1.5; }
.f4-metadata-dialog label { display:grid; gap:6px; color:#274164; font-weight:650; }
.f4-metadata-dialog input { width:100%; box-sizing:border-box; border:1px solid #cbd8ea; border-radius:9px; padding:10px 12px; font:inherit; }
.f4-dialog-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:8px; }
.f4-dialog-actions .cancel { color:#405572; background:#f4f7fb; border-color:#cbd8ea; }
</style>
