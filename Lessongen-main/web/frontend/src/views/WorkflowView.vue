<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import axios from "axios";
import AppPageHeader from "../components/AppPageHeader.vue";
import { type LessonOption, type VersionOption } from "../components/LessonSelectorBar.vue";
import { type FeatureId, type WorkflowStep, useWorkflowStore } from "../stores/workflow";

const workflow = useWorkflowStore(), route = useRoute(), router = useRouter();
const selectedLesson = ref<LessonOption | null>(null), selectedVersion = ref<VersionOption | null>(null);
const showEditor = ref(false), error = ref("");
const editId = ref(""), editName = ref(""), editSteps = ref<FeatureId[]>(["F1", "F2", "F3", "F4"]);
const initialLessonId = computed(() => typeof route.query.lessonId === "string" ? route.query.lessonId : "");
const initialVersionId = computed(() => typeof route.query.versionId === "string" ? route.query.versionId : "");
const featureNames: Record<FeatureId, string> = { F1: "智能评价", F2: "设计修改", F3: "课堂推演", F4: "协同共析" };
const featureReasons: Record<FeatureId, string> = { F1: "识别教案问题", F2: "生成或优化设计", F3: "推演课堂表现", F4: "逐节判断并修订" };
function remember(lesson: LessonOption | null, version: VersionOption | null) { selectedLesson.value = lesson; selectedVersion.value = version; }
function choose(id: string) { workflow.selectTemplate(id); }
function openCreate() { editId.value = ""; editName.value = ""; editSteps.value = ["F1", "F2", "F3", "F4"]; error.value = ""; showEditor.value = true; }
function openEdit(id: string) { const item = workflow.templates.find(value => value.id === id); if (!item || item.builtin) return; editId.value = id; editName.value = item.name; editSteps.value = item.steps.map(step => step.id); error.value = ""; showEditor.value = true; }
function saveCustom() {
  const steps: WorkflowStep[] = editSteps.value.map(id => ({ id, name: featureNames[id], reason: featureReasons[id] }));
  if (!editName.value.trim()) { error.value = "请填写工作流名称。"; return; }
  if (!workflow.saveCustom({ id: editId.value || undefined, name: editName.value, steps })) { error.value = "自定义工作流必须包含四个不同功能，且课堂推演后不能紧接智能评价。"; return; }
  showEditor.value = false;
}
async function start() {
  if (workflow.activeRun && !workflow.isFinished && !window.confirm("当前还有未完成的工作流，是否以本次选择替换？")) return;
  workflow.startRun(selectedLesson.value && selectedVersion.value ? { lessonId: selectedLesson.value.id, lessonTitle: selectedLesson.value.title, versionId: selectedVersion.value.id, versionNumber: selectedVersion.value.versionNumber } : undefined, workflow.selectedTemplate);
  if (workflow.currentDestination) await router.push(workflow.currentDestination);
}
async function hydrateQuerySelection() {
  if (!initialLessonId.value || !initialVersionId.value) return;
  try {
    const data = (await axios.get<{ lesson: LessonOption; versions: VersionOption[] }>(`/api/platform/lessons/${encodeURIComponent(initialLessonId.value)}`)).data;
    const version = data.versions.find(item => item.id === initialVersionId.value);
    if (version) remember(data.lesson, version);
  } catch { /* LessonSelectorBar will show the same selection and its own error state. */ }
}
onMounted(() => { void hydrateQuerySelection(); });
</script>

<template>
  <main class="workflow-page">
    <AppPageHeader title="工作流" description="选择推荐流程或自定义流程。工作流开始后，在第一个具体任务中确定本次使用的教案。"><template #actions><button class="v2-button v2-button--secondary" type="button" @click="openCreate">新建自定义工作流</button></template></AppPageHeader>
    <section class="template-grid">
      <article v-for="template in workflow.templates" :key="template.id" class="template-card v2-card" :class="{ selected: workflow.selectedTemplateId === template.id }" @click="choose(template.id)">
        <div class="template-head"><span>{{ template.builtin ? "固定流程" : "自定义" }}</span><div v-if="!template.builtin"><button type="button" @click.stop="openEdit(template.id)">编辑</button><button type="button" @click.stop="workflow.deleteCustom(template.id)">删除</button></div></div>
        <h2>{{ template.name }}</h2><p>{{ template.description }}</p>
        <ol><li v-for="(step, index) in template.steps" :key="`${step.id}-${index}`"><b>{{ index + 1 }}</b><span>{{ step.name }}</span></li></ol>
        <button class="select-template" type="button">{{ workflow.selectedTemplateId === template.id ? "已选择" : "选择此流程" }}</button>
      </article>
    </section>
    <section class="start-panel v2-card"><div><small>当前选择</small><h2>{{ workflow.selectedTemplate.name }}</h2><p v-if="selectedLesson">{{ selectedLesson.title }} · V{{ selectedVersion?.versionNumber }}</p><p v-else>点击开始后进入第一个智能体任务，在那里选择、上传或生成教案。</p></div><button class="v2-button v2-button--primary" type="button" @click="start">开始工作流</button></section>

    <Teleport to="body"><div v-if="showEditor" class="modal-backdrop" @click.self="showEditor=false"><section class="modal-card editor"><header><div><small>自定义工作流</small><h2>{{ editId ? "编辑工作流" : "新建工作流" }}</h2></div><button type="button" @click="showEditor=false">×</button></header><label>工作流名称<input v-model="editName" maxlength="40" placeholder="例如：完整备课检查"></label><div class="step-editor"><label v-for="(_, index) in editSteps" :key="index">第 {{ index + 1 }} 步<select v-model="editSteps[index]"><option v-for="(name,id) in featureNames" :key="id" :value="id">{{ name }}</option></select></label></div><p class="rule">必须设置四个不同功能；课堂推演后不能紧接智能评价。</p><p v-if="error" class="error">{{ error }}</p><button class="v2-button v2-button--primary" type="button" @click="saveCustom">保存工作流</button></section></div></Teleport>
  </main>
</template>

<style scoped>
.workflow-page{display:grid;gap:25px}.template-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.template-card{display:flex;flex-direction:column;padding:22px;cursor:pointer}.template-card.selected{border:2px solid var(--color-primary);padding:21px;background:var(--color-primary-soft)}.template-head{display:flex;justify-content:space-between;color:var(--color-primary);font-size:12px;font-weight:800}.template-head button{border:0;color:var(--color-text-secondary);background:transparent;cursor:pointer}.template-card h2{margin:12px 0 7px;font-size:20px}.template-card>p{min-height:46px;margin:0;color:var(--color-text-secondary);font-size:13px;line-height:1.6}.template-card ol{display:grid;gap:9px;margin:18px 0;padding:0;list-style:none}.template-card li{display:flex;align-items:center;gap:9px}.template-card li b{width:25px;height:25px;display:grid;place-items:center;border-radius:50%;color:var(--color-primary);background:#fff;font-size:12px}.select-template{margin-top:auto;min-height:38px;border:1px solid var(--color-primary-border);border-radius:var(--radius-md);color:var(--color-primary);background:#fff;font-weight:700;cursor:pointer}.start-panel{display:flex;align-items:center;justify-content:space-between;gap:22px;padding:24px}.start-panel small{color:var(--color-primary);font-weight:800}.start-panel h2{margin:6px 0}.start-panel p{margin:0;color:var(--color-text-secondary)}.modal-backdrop{position:fixed;inset:0;z-index:350;display:grid;place-items:center;padding:20px;background:rgba(20,39,70,.45)}.modal-card{width:min(760px,100%);max-height:90vh;overflow:auto;padding:25px;border-radius:var(--radius-lg);background:#fff}.modal-card header{display:flex;align-items:center;justify-content:space-between}.modal-card header small{color:var(--color-primary)}.modal-card header h2{margin:4px 0 0}.modal-card header button{width:36px;height:36px;border:0;border-radius:50%;font-size:24px;cursor:pointer}.editor>label,.step-editor label{display:grid;gap:7px;color:var(--color-text-secondary);font-size:13px;font-weight:700}.editor>label{margin-top:22px}.editor input,.editor select{min-height:42px;padding:0 11px;border:1px solid var(--color-border);border-radius:var(--radius-sm)}.step-editor{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px;margin:17px 0}.rule{color:var(--color-text-muted);font-size:13px}.error{color:var(--color-danger)}@media(max-width:900px){.template-grid{grid-template-columns:1fr}.template-card>p{min-height:0}}@media(max-width:620px){.start-panel{align-items:flex-start;flex-direction:column}.step-editor{grid-template-columns:1fr}}
</style>
