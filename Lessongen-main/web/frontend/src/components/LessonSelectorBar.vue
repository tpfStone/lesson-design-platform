<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import axios from "axios";
import { RouterLink } from "vue-router";
import LessonImportPanel from "./LessonImportPanel.vue";
import ReviewDocumentPreview from "./ReviewDocumentPreview.vue";

export interface LessonOption {
  id: string;
  title: string;
  currentVersionId: string;
  subject: string;
  grade: string;
  topic: string;
  durationMinutes?: number | null;
}
export interface VersionOption {
  id: string;
  versionNumber: number;
  sourceModule: string;
  content: string;
}
const props = withDefaults(defineProps<{
  initialLessonId?: string;
  initialVersionId?: string;
  showTools?: boolean;
  locked?: boolean;
  actionLabel?: string;
  actionDisabled?: boolean;
  actionBusy?: boolean;
}>(), {
  initialLessonId: "", initialVersionId: "", showTools: true, locked: false,
  actionLabel: "", actionDisabled: false, actionBusy: false,
});
const emit = defineEmits<{
  selection: [lesson: LessonOption | null, version: VersionOption | null];
  action: [lesson: LessonOption, version: VersionOption];
}>();
const lessons = ref<LessonOption[]>([]);
const versions = ref<VersionOption[]>([]);
const lessonId = ref(props.initialLessonId);
const versionId = ref(props.initialVersionId);
const loading = ref(true), loadingVersions = ref(false), error = ref("");
const comparing = ref(false), leftId = ref(""), rightId = ref("");
const uploading = ref(false);
const selectedLesson = computed(() => lessons.value.find(item => item.id === lessonId.value) || null);
const selectedVersion = computed(() => versions.value.find(item => item.id === versionId.value) || null);
const left = computed(() => versions.value.find(item => item.id === leftId.value));
const right = computed(() => versions.value.find(item => item.id === rightId.value));
const exportUrl = computed(() => selectedLesson.value && selectedVersion.value
  ? `/api/platform/lessons/${encodeURIComponent(lessonId.value)}/versions/${encodeURIComponent(versionId.value)}/export/docx`
  : "");
const sourceNames: Record<string, string> = {
  IMPORT_DOCX: "导入原稿", IMPORT_TEXT: "文本创建", MANUAL: "手动修改",
  F1_ANNOTATION: "智能评价后", F2_OPTIMIZATION: "设计修改后", F2_OPTIMIZE: "设计修改后",
  F3_SIMULATION: "课堂推演后", F4_NAVIGATION: "协同共析后",
};
function versionLabel(version: VersionOption) {
  const source = sourceNames[version.sourceModule] || version.sourceModule.replaceAll("_", " ");
  return `V${version.versionNumber} · ${source}${version.id === selectedLesson.value?.currentVersionId ? "（最新）" : ""}`;
}
function publish() { emit("selection", selectedLesson.value, selectedVersion.value); }
async function loadVersions(id: string, preferred = "") {
  versions.value = []; versionId.value = ""; error.value = ""; publish();
  if (!id) return;
  loadingVersions.value = true;
  try {
    const data = (await axios.get<{ versions: VersionOption[] }>(`/api/platform/lessons/${encodeURIComponent(id)}`)).data;
    if (lessonId.value !== id) return;
    versions.value = [...data.versions].sort((a, b) => b.versionNumber - a.versionNumber);
    versionId.value = versions.value.some(item => item.id === preferred)
      ? preferred : selectedLesson.value?.currentVersionId || versions.value[0]?.id || "";
    publish();
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? reason.message : "版本读取失败";
  } finally { loadingVersions.value = false; }
}
function openCompare() {
  rightId.value = versionId.value;
  leftId.value = versions.value.find(item => item.id !== rightId.value)?.id || rightId.value;
  comparing.value = true;
}
function runAction() {
  if (selectedLesson.value && selectedVersion.value) emit("action", selectedLesson.value, selectedVersion.value);
}
async function loadLessons(preferredLessonId = props.initialLessonId, preferredVersionId = props.initialVersionId) {
  loading.value = true;
  try {
    lessons.value = (await axios.get<LessonOption[]>("/api/platform/lessons")).data;
    lessonId.value = lessons.value.some(item => item.id === preferredLessonId)
      ? preferredLessonId : lessons.value[0]?.id || "";
    await loadVersions(lessonId.value, preferredVersionId);
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? reason.message : "教案读取失败";
  } finally { loading.value = false; }
}
async function afterImported(created: { lesson: { id: string; currentVersionId: string } }) {
  uploading.value = false;
  await loadLessons(created.lesson.id, created.lesson.currentVersionId);
}
onMounted(async () => {
  await loadLessons();
});
watch(() => [props.initialLessonId, props.initialVersionId] as const, ([id, version]) => {
  if (id && lessons.value.some(item => item.id === id) && id !== lessonId.value) {
    lessonId.value = id; void loadVersions(id, version);
  } else if (version && versions.value.some(item => item.id === version)) {
    versionId.value = version; publish();
  }
});
</script>

<template>
  <section class="lesson-selector" :class="{ 'lesson-selector--locked': locked }" aria-label="当前教案">
    <div class="selector-heading"><strong>当前教案</strong><span v-if="locked">由当前工作流指定</span></div>
    <div v-if="locked" class="locked-selection">
      <div><strong>{{ selectedLesson?.title || "正在读取教案……" }}</strong><small v-if="selectedVersion">V{{ selectedVersion.versionNumber }}<template v-if="selectedLesson?.subject"> · {{ selectedLesson.subject }}</template><template v-if="selectedLesson?.grade"> · {{ selectedLesson.grade }}</template></small></div>
      <span>锁定</span>
    </div>
    <div v-else class="selector-row">
      <label><span>教案</span><select v-model="lessonId" :disabled="loading" @change="loadVersions(lessonId)"><option v-if="!lessons.length" value="">{{ loading ? "正在读取……" : "暂无教案" }}</option><option v-for="lesson in lessons" :key="lesson.id" :value="lesson.id">{{ lesson.title }}</option></select></label>
      <label><span>版本</span><select v-model="versionId" :disabled="loadingVersions || !versions.length" @change="publish"><option v-if="!versions.length" value="">{{ loadingVersions ? "正在读取……" : "暂无版本" }}</option><option v-for="version in versions" :key="version.id" :value="version.id">{{ versionLabel(version) }}</option></select></label>
      <div v-if="showTools" class="selector-tools"><button type="button" :disabled="!selectedVersion" @click="openCompare">版本对比</button><a v-if="exportUrl" :href="exportUrl" download>导出DOCX</a></div>
      <button type="button" class="upload-button" @click="uploading = true">上传教案</button>
      <button v-if="actionLabel" type="button" class="selector-action" :disabled="actionDisabled || actionBusy || !selectedLesson || !selectedVersion" @click="runAction">{{ actionBusy ? "正在处理……" : actionLabel }}</button>
    </div>
    <p v-if="error" class="selector-error" role="alert">暂时无法读取教案，请稍后重试。<small>{{ error }}</small></p>
    <RouterLink v-if="!loading && !lessons.length" to="/">返回首页上传或生成教案</RouterLink>
    <Teleport to="body"><div v-if="comparing" class="compare-backdrop" @click.self="comparing = false"><section class="compare-dialog" role="dialog" aria-modal="true" aria-label="教案版本对比">
      <header><div><small>版本历史</small><h2>教案版本对比</h2></div><button type="button" aria-label="关闭" @click="comparing = false">×</button></header>
      <div class="compare-grid"><div><label>原版本<select v-model="leftId"><option v-for="version in versions" :key="version.id" :value="version.id">{{ versionLabel(version) }}</option></select></label><ReviewDocumentPreview v-if="left" :content="left.content" /></div><div><label>对比版本<select v-model="rightId"><option v-for="version in versions" :key="version.id" :value="version.id">{{ versionLabel(version) }}</option></select></label><ReviewDocumentPreview v-if="right" :content="right.content" /></div></div>
    </section></div></Teleport>
    <Teleport to="body"><div v-if="uploading" class="compare-backdrop" @click.self="uploading = false"><section class="upload-dialog" role="dialog" aria-modal="true" aria-label="上传教案">
      <header><div><small>上传教案</small><h2>导入 DOCX 到我的教案</h2></div><button type="button" aria-label="关闭" @click="uploading = false">×</button></header>
      <LessonImportPanel :redirect-on-save="false" @imported="afterImported" />
    </section></div></Teleport>
  </section>
</template>

<style scoped>
.lesson-selector{margin:20px 0 26px;padding:16px 18px;border:1px solid var(--color-primary-border);border-radius:var(--radius-md);background:#f5f8ff}.selector-heading{display:flex;justify-content:space-between;gap:12px;margin-bottom:12px}.selector-heading strong{color:var(--color-text);font-size:14px}.selector-heading span{color:var(--color-text-muted);font-size:12px}.selector-row{display:flex;align-items:end;gap:12px}.selector-row label{display:grid;flex:1 1 220px;gap:6px;color:var(--color-text-secondary);font-size:12px;font-weight:700}.selector-row select,.compare-grid select{width:100%;min-height:40px;padding:0 11px;border:1px solid #cbd8eb;border-radius:var(--radius-sm);color:var(--color-text);background:#fff}.selector-tools{display:flex;align-items:center;gap:12px;min-height:40px}.selector-tools button,.selector-tools a{border:0;color:var(--color-primary);background:transparent;font-size:13px;cursor:pointer;white-space:nowrap}.upload-button{min-height:40px;padding:0 14px;border:1px solid var(--color-primary-border);border-radius:var(--radius-md);color:var(--color-primary);background:#fff;font-weight:700;cursor:pointer;white-space:nowrap}.selector-action{min-height:40px;padding:0 17px;border:0;border-radius:var(--radius-md);color:#fff;background:var(--color-primary);font-weight:700;cursor:pointer;white-space:nowrap}.selector-action:disabled{opacity:.55;cursor:not-allowed}.locked-selection{display:flex;align-items:center;justify-content:space-between;gap:16px}.locked-selection strong,.locked-selection small{display:block}.locked-selection small{margin-top:6px;color:var(--color-text-secondary)}.locked-selection>span{color:var(--color-primary);font-size:12px;font-weight:700}.selector-error{color:var(--color-danger)}.selector-error small{display:block;margin-top:5px;color:var(--color-text-muted)}.lesson-selector>a{color:var(--color-primary);font-weight:700}.compare-backdrop{position:fixed;inset:0;z-index:320;display:grid;place-items:center;padding:20px;background:rgba(23,43,72,.44)}.compare-dialog,.upload-dialog{width:min(1080px,100%);max-height:88vh;overflow:auto;padding:24px;border-radius:var(--radius-lg);background:#fff}.upload-dialog{width:min(760px,100%)}.compare-dialog header,.upload-dialog header{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}.compare-dialog header small,.upload-dialog header small{color:var(--color-primary)}.compare-dialog h2,.upload-dialog h2{margin:3px 0 0}.compare-dialog header button,.upload-dialog header button{width:36px;height:36px;border:0;border-radius:50%;font-size:24px;cursor:pointer}.upload-dialog :deep(.import-panel){padding:0;border:0}.compare-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.compare-grid label{display:grid;gap:6px;margin-bottom:10px;color:var(--color-text-secondary);font-size:13px}@media(max-width:760px){.selector-row{align-items:stretch;flex-direction:column}.selector-row label{flex:auto}.selector-tools{justify-content:space-between}.selector-action,.upload-button{width:100%}.compare-grid{grid-template-columns:1fr}}
</style>
