<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import axios from "axios";

interface DocxPreview { originalFilename: string; sizeBytes: number; extractedContent: string; contentLength: number; warnings: string[] }
interface CreatedLesson { lesson: { id: string; title?: string; currentVersionId: string } }
const props = withDefaults(defineProps<{ redirectOnSave?: boolean }>(), { redirectOnSave: true });
const emit = defineEmits<{ imported: [created: CreatedLesson] }>();
const router = useRouter();
const fileInput = ref<HTMLInputElement | null>(null);
const file = ref<File | null>(null), preview = ref<DocxPreview | null>(null);
const previewing = ref(false), saving = ref(false), error = ref("");
const form = ref({ title: "", subject: "", grade: "", topic: "", durationMinutes: 45, content: "" });
function chooseFile() { fileInput.value?.click(); }
async function selected(event: Event) {
  const input = event.target as HTMLInputElement;
  const selectedFile = input.files?.[0] || null;
  file.value = null; preview.value = null; error.value = "";
  if (!selectedFile) return;
  if (!selectedFile.name.toLowerCase().endsWith(".docx")) { error.value = "当前仅支持DOCX文件，PDF功能即将支持。"; input.value = ""; return; }
  previewing.value = true;
  try {
    const data = new FormData(); data.append("file", selectedFile, selectedFile.name);
    preview.value = (await axios.post<DocxPreview>("/api/platform/lessons/imports/docx/preview", data, { timeout: 60000 })).data;
    file.value = selectedFile; form.value.content = preview.value.extractedContent;
    const name = preview.value.originalFilename.replace(/\.docx$/i, "").trim();
    form.value.title = name; form.value.topic = name;
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? (reason.response?.data as { detail?: string })?.detail || reason.message : "DOCX解析失败";
  } finally { previewing.value = false; }
}
async function save() {
  if (!file.value || !preview.value || saving.value || !form.value.title.trim()) return;
  saving.value = true; error.value = "";
  try {
    const data = new FormData(); data.append("file", file.value, file.value.name);
    data.append("title", form.value.title.trim());
    // Preserve the parsed DOCX structure unless the user really changed the preview text.
    if (form.value.content !== preview.value.extractedContent) {
      data.append("content", form.value.content);
    }
    if (form.value.subject.trim()) data.append("subject", form.value.subject.trim());
    if (form.value.grade.trim()) data.append("grade", form.value.grade.trim());
    if (form.value.topic.trim()) data.append("topic", form.value.topic.trim());
    data.append("durationMinutes", String(form.value.durationMinutes));
    const created = (await axios.post<CreatedLesson>("/api/platform/lessons/imports/docx", data, { timeout: 60000 })).data;
    emit("imported", created);
    if (props.redirectOnSave) await router.push({ path: `/lessons/${created.lesson.id}`, query: { version: created.lesson.currentVersionId } });
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? (reason.response?.data as { detail?: string })?.detail || reason.message : "教案保存失败";
  } finally { saving.value = false; }
}
</script>

<template>
  <section class="import-panel">
    <div class="import-copy"><span>上传教案</span><h2>{{ preview ? "确认教案信息" : "拖拽或点击上传DOCX" }}</h2><p>DOCX已支持，PDF识别即将支持。</p></div>
    <input ref="fileInput" class="visually-hidden" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" @change="selected">
    <button v-if="!preview" type="button" class="upload-area" :disabled="previewing" @click="chooseFile"><strong>{{ previewing ? "正在解析教案……" : "选择DOCX文件" }}</strong><small>文件会保存到“我的教案”，供四个功能共同使用</small></button>
    <div v-else class="import-form">
      <label class="wide">教案名称<input v-model="form.title" maxlength="200"></label>
      <label>学科<input v-model="form.subject" placeholder="例如：数学"></label>
      <label>年级<input v-model="form.grade" placeholder="例如：四年级"></label>
      <label class="wide">课题<input v-model="form.topic" maxlength="200"></label>
      <div class="import-actions"><button type="button" class="change-file" @click="chooseFile">重新选择</button><button type="button" class="save-file" :disabled="saving || !form.title.trim()" @click="save">{{ saving ? "正在保存……" : "保存到我的教案" }}</button></div>
    </div>
    <p v-if="error" class="import-error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.import-panel{height:100%;padding:26px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff}.import-copy>span{color:var(--color-primary);font-size:12px;font-weight:800}.import-copy h2{margin:7px 0 5px;font-size:21px}.import-copy p{margin:0 0 18px;color:var(--color-text-secondary);font-size:13px}.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}.upload-area{width:100%;min-height:126px;display:grid;place-items:center;padding:22px;border:1px dashed #9eb7e5;border-radius:var(--radius-md);color:var(--color-primary);background:#f6f9ff;cursor:pointer}.upload-area strong,.upload-area small{display:block}.upload-area small{margin-top:-28px;color:var(--color-text-muted);font-weight:400}.import-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.import-form label{display:grid;gap:5px;color:var(--color-text-secondary);font-size:12px;font-weight:700}.import-form label.wide,.import-actions{grid-column:1/-1}.import-form input{min-height:39px;padding:0 10px;border:1px solid #cdd9e9;border-radius:var(--radius-sm)}.import-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:4px}.import-actions button{min-height:39px;padding:0 14px;border-radius:var(--radius-md);font-weight:700;cursor:pointer}.change-file{border:1px solid var(--color-primary-border);color:var(--color-primary);background:#fff}.save-file{border:0;color:#fff;background:var(--color-primary)}.save-file:disabled{opacity:.55}.import-error{margin:12px 0 0;color:var(--color-danger);font-size:13px}@media(max-width:540px){.import-form{grid-template-columns:1fr}.upload-area small{margin-top:0}}
</style>
