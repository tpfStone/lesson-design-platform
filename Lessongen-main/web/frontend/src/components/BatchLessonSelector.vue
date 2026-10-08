<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import axios from "axios";
import VersionBadge from "./VersionBadge.vue";

export interface BatchSelection {
  lessonId: string;
  lessonTitle: string;
  subject: string;
  grade: string;
  versionId: string;
  versionNumber: number;
  sourceModule?: string;
}
interface LessonOption {
  id: string;
  title: string;
  currentVersionId: string;
  subject: string;
  grade: string;
}
interface VersionOption {
  id: string;
  versionNumber: number;
  sourceModule?: string;
}
interface LessonDetail { lesson: LessonOption; versions: VersionOption[] }
interface DocxPreview { originalFilename: string; sizeBytes: number; extractedContent: string; contentLength: number; warnings: string[] }
interface CreatedLesson { lesson: { id: string; title?: string; currentVersionId: string } }

const props = withDefaults(defineProps<{ modelValue: BatchSelection[]; disabled?: boolean; max?: number }>(), { disabled: false, max: 20 });
const emit = defineEmits<{ "update:modelValue": [value: BatchSelection[]] }>();

const lessons = ref<LessonOption[]>([]);
const versions = ref<VersionOption[]>([]);
const lessonId = ref("");
const versionId = ref("");
const loading = ref(false);
const loadingVersions = ref(false);
const error = ref("");
const notice = ref("");
const uploading = ref(false);
const batchFileInput = ref<HTMLInputElement | null>(null);
const batchUploading = ref(false);
const batchUploadLog = ref<string[]>([]);
const currentLesson = computed(() => lessons.value.find(item => item.id === lessonId.value) || null);
const currentVersion = computed(() => versions.value.find(item => item.id === versionId.value) || null);
const atLimit = computed(() => props.modelValue.length >= props.max);

async function loadLessons(preferred = "") {
  loading.value = true;
  error.value = "";
  try {
    lessons.value = (await axios.get<LessonOption[]>("/api/platform/lessons")).data;
    lessonId.value = lessons.value.some(item => item.id === preferred) ? preferred : lessons.value[0]?.id || "";
    await loadVersions(lessonId.value);
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? reason.message : "教案读取失败";
  } finally { loading.value = false; }
}
async function loadVersions(id: string, preferred = "") {
  versions.value = [];
  versionId.value = "";
  if (!id) return;
  loadingVersions.value = true;
  try {
    const data = (await axios.get<LessonDetail>(`/api/platform/lessons/${encodeURIComponent(id)}`)).data;
    versions.value = [...data.versions].sort((a, b) => b.versionNumber - a.versionNumber);
    versionId.value = versions.value.some(item => item.id === preferred)
      ? preferred
      : data.lesson.currentVersionId || versions.value[0]?.id || "";
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? reason.message : "版本读取失败";
  } finally { loadingVersions.value = false; }
}
function addCurrent() {
  notice.value = "";
  if (!currentLesson.value || !currentVersion.value || props.disabled) return;
  const duplicate = props.modelValue.some(item => item.lessonId === currentLesson.value!.id && item.versionId === currentVersion.value!.id);
  if (duplicate) { notice.value = "这份教案的当前版本已经加入批量列表。"; return; }
  if (atLimit.value) { notice.value = `一次最多选择 ${props.max} 份教案。`; return; }
  emit("update:modelValue", [...props.modelValue, {
    lessonId: currentLesson.value.id,
    lessonTitle: currentLesson.value.title,
    subject: currentLesson.value.subject,
    grade: currentLesson.value.grade,
    versionId: currentVersion.value.id,
    versionNumber: currentVersion.value.versionNumber,
    sourceModule: currentVersion.value.sourceModule,
  }]);
}
function remove(index: number) {
  if (props.disabled) return;
  emit("update:modelValue", props.modelValue.filter((_, itemIndex) => itemIndex !== index));
}
async function afterImported(created: { lesson: { id: string; currentVersionId: string } }) {
  try {
    const data = (await axios.get<LessonDetail>(`/api/platform/lessons/${encodeURIComponent(created.lesson.id)}`)).data;
    const version = data.versions.find(item => item.id === created.lesson.currentVersionId) || data.versions[0];
    if (!version) return;
    if (!props.modelValue.some(item => item.lessonId === data.lesson.id && item.versionId === version.id) && !atLimit.value) {
      emit("update:modelValue", [...props.modelValue, {
        lessonId: data.lesson.id,
        lessonTitle: data.lesson.title,
        subject: data.lesson.subject,
        grade: data.lesson.grade,
        versionId: version.id,
        versionNumber: version.versionNumber,
        sourceModule: version.sourceModule,
      }]);
    }
    await loadLessons(data.lesson.id);
    await loadVersions(data.lesson.id, version.id);
    notice.value = "新上传的教案已保存到“我的教案”，并加入当前批量列表。";
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? reason.message : "新教案读取失败";
  }
}
function chooseBatchFiles() {
  batchFileInput.value?.click();
}
async function uploadBatchFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  input.value = "";
  if (!files.length || batchUploading.value) return;
  const docxFiles = files.filter(file => file.name.toLowerCase().endsWith(".docx"));
  if (docxFiles.length !== files.length) {
    error.value = "当前仅支持批量上传 DOCX 文件，已忽略非 DOCX 文件。";
  } else {
    error.value = "";
  }
  if (!docxFiles.length) return;

  batchUploading.value = true;
  batchUploadLog.value = [];
  let added = 0;
  try {
    for (const file of docxFiles.slice(0, Math.max(0, props.max - props.modelValue.length))) {
      batchUploadLog.value = [`正在解析：${file.name}`, ...batchUploadLog.value.slice(0, 4)];
      const previewData = new FormData();
      previewData.append("file", file, file.name);
      const preview = (await axios.post<DocxPreview>("/api/platform/lessons/imports/docx/preview", previewData, { timeout: 60000 })).data;
      const name = preview.originalFilename.replace(/\.docx$/i, "").trim() || file.name.replace(/\.docx$/i, "");
      const saveData = new FormData();
      saveData.append("file", file, file.name);
      saveData.append("title", name);
      saveData.append("topic", name);
      saveData.append("durationMinutes", "45");
      const created = (await axios.post<CreatedLesson>("/api/platform/lessons/imports/docx", saveData, { timeout: 60000 })).data;
      await afterImported(created);
      added += 1;
      batchUploadLog.value = [`已导入：${file.name}`, ...batchUploadLog.value.slice(0, 4)];
      if (props.modelValue.length >= props.max) break;
    }
    notice.value = `已批量导入 ${added} 份教案，并加入当前批量列表。`;
    if (added > 0) uploading.value = false;
  } catch (reason) {
    error.value = axios.isAxiosError(reason)
      ? ((reason.response?.data as { detail?: string } | undefined)?.detail || reason.message)
      : "批量上传失败，请检查文件后重试。";
  } finally {
    batchUploading.value = false;
  }
}

onMounted(() => void loadLessons());
</script>

<template>
  <section class="batch-selector v2-card">
    <div class="selector-title">
      <div><span>选择教案</span><h2>添加已有教案与版本</h2><p>同一个教案版本不会重复加入；一次可选择 2～{{ max }} 份。</p></div>
      <button type="button" class="v2-button v2-button--secondary" :disabled="disabled || atLimit" @click="uploading = true">批量上传教案</button>
    </div>

    <div class="selector-row">
      <label><span>教案</span><select v-model="lessonId" :disabled="loading || disabled" @change="loadVersions(lessonId)"><option v-if="!lessons.length" value="">{{ loading ? "正在读取……" : "暂无教案" }}</option><option v-for="lesson in lessons" :key="lesson.id" :value="lesson.id">{{ lesson.title }}</option></select></label>
      <label><span>版本</span><select v-model="versionId" :disabled="loadingVersions || disabled || !versions.length"><option v-if="!versions.length" value="">{{ loadingVersions ? "正在读取……" : "暂无版本" }}</option><option v-for="version in versions" :key="version.id" :value="version.id">V{{ version.versionNumber }}<template v-if="version.id === currentLesson?.currentVersionId"> · 最新</template></option></select></label>
      <button type="button" class="v2-button v2-button--primary add-button" :disabled="disabled || !currentLesson || !currentVersion || atLimit" @click="addCurrent">添加</button>
    </div>

    <p v-if="notice" class="selector-notice">{{ notice }}</p>
    <p v-if="error" class="selector-error" role="alert">{{ error }}</p>

    <div class="selected-heading"><strong>已选择 {{ modelValue.length }} 份</strong><span v-if="modelValue.length < 2">至少选择 2 份后才能开始批量评审</span></div>
    <div v-if="modelValue.length" class="selected-list">
      <article v-for="(item, index) in modelValue" :key="`${item.lessonId}:${item.versionId}`">
        <div><strong>{{ item.lessonTitle }}</strong><small><template v-if="item.subject">{{ item.subject }}</template><template v-if="item.subject && item.grade"> · </template><template v-if="item.grade">{{ item.grade }}</template></small></div>
        <VersionBadge :version-number="item.versionNumber" :source="item.sourceModule" />
        <button type="button" :disabled="disabled" aria-label="移除教案" @click="remove(index)">×</button>
      </article>
    </div>

    <Teleport to="body"><div v-if="uploading" class="upload-backdrop" @click.self="uploading = false"><section class="upload-dialog" role="dialog" aria-modal="true" aria-label="批量上传教案">
      <header><div><small>批量上传教案</small><h2>一次导入多份 DOCX</h2><p>导入后会自动保存到“我的教案”，并加入当前批量评审列表。</p></div><button type="button" aria-label="关闭" @click="uploading = false">×</button></header>
      <input ref="batchFileInput" class="visually-hidden" type="file" multiple accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" @change="uploadBatchFiles">
      <button type="button" class="batch-upload-area" :disabled="batchUploading || atLimit" @click="chooseBatchFiles">
        <strong>{{ batchUploading ? "正在批量导入……" : "选择多份 DOCX 文件" }}</strong>
        <small>剩余可加入 {{ Math.max(0, max - modelValue.length) }} 份；最多 {{ max }} 份</small>
      </button>
      <div v-if="batchUploadLog.length" class="batch-upload-log">
        <p v-for="item in batchUploadLog" :key="item">{{ item }}</p>
      </div>
    </section></div></Teleport>
  </section>
</template>

<style scoped>
.batch-selector{padding:22px}.selector-title{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.selector-title span{color:var(--color-primary);font-size:12px;font-weight:800}.selector-title h2{margin:5px 0 6px;font-size:21px}.selector-title p{margin:0;color:var(--color-text-secondary);font-size:13px}.selector-row{display:flex;align-items:end;gap:12px;margin-top:20px;padding:15px;border:1px solid var(--color-primary-border);border-radius:var(--radius-md);background:#f6f9ff}.selector-row label{display:grid;flex:1 1 260px;gap:6px;color:var(--color-text-secondary);font-size:12px;font-weight:700}.selector-row select{width:100%;min-height:40px;padding:0 10px;border:1px solid #cbd8eb;border-radius:var(--radius-sm);color:var(--color-text);background:#fff}.add-button{min-width:88px}.selector-notice{margin:12px 0 0;color:var(--color-primary);font-size:13px}.selector-error{margin:12px 0 0;color:var(--color-danger);font-size:13px}.selected-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:22px}.selected-heading span{color:var(--color-text-muted);font-size:12px}.selected-list{display:grid;gap:9px;margin-top:11px}.selected-list article{display:grid;grid-template-columns:minmax(0,1fr) auto 34px;align-items:center;gap:14px;padding:12px 14px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff}.selected-list article>div{display:grid;gap:4px;min-width:0}.selected-list strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.selected-list small{color:var(--color-text-muted)}.selected-list article>button{width:30px;height:30px;border:0;border-radius:50%;color:var(--color-text-muted);background:var(--color-surface-soft);font-size:20px;cursor:pointer}.upload-backdrop{position:fixed;inset:0;z-index:320;display:grid;place-items:center;padding:20px;background:rgba(23,43,72,.44)}.upload-dialog{width:min(760px,100%);max-height:88vh;overflow:auto;padding:24px;border-radius:var(--radius-lg);background:#fff}.upload-dialog header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:18px}.upload-dialog header small{color:var(--color-primary);font-weight:800}.upload-dialog h2{margin:3px 0 5px}.upload-dialog header p{margin:0;color:var(--color-text-secondary);font-size:13px}.upload-dialog header button{width:36px;height:36px;border:0;border-radius:50%;font-size:24px;cursor:pointer}.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}.batch-upload-area{width:100%;min-height:150px;display:grid;place-items:center;padding:24px;border:1px dashed #9eb7e5;border-radius:var(--radius-md);color:var(--color-primary);background:#f6f9ff;cursor:pointer}.batch-upload-area strong,.batch-upload-area small{display:block}.batch-upload-area small{color:var(--color-text-muted);font-weight:400}.batch-upload-log{display:grid;gap:6px;margin-top:14px}.batch-upload-log p{margin:0;padding:9px 11px;border-radius:var(--radius-sm);color:var(--color-text-secondary);background:var(--color-surface-soft);font-size:12px}
@media(max-width:760px){.selector-title{flex-direction:column}.selector-row{align-items:stretch;flex-direction:column}.selector-row label{flex:auto}.add-button,.selector-title>.v2-button{width:100%}.selected-heading{align-items:flex-start;flex-direction:column}.selected-list article{grid-template-columns:minmax(0,1fr) auto}.selected-list article>button{grid-column:2;grid-row:1 / span 2}}
</style>
