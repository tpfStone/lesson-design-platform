import { defineStore } from "pinia";

export type FeatureId = "F1" | "F2" | "F3" | "F4";
export interface WorkflowStep { id: FeatureId; name: string; reason: string }
export interface WorkflowTemplate {
  id: string; name: string; description: string; steps: WorkflowStep[]; builtin: boolean;
}
export interface WorkflowRun {
  templateId: string; templateName: string; steps: WorkflowStep[];
  lessonId: string; lessonTitle: string; versionId: string; versionNumber: number | null;
  currentIndex: number; completedIndexes: number[]; startedAt: string; updatedAt: string;
  finishedAt?: string; paths?: Record<string, string>;
}

const step = (id: FeatureId, name: string, reason: string): WorkflowStep => ({ id, name, reason });
export const builtinWorkflows: WorkflowTemplate[] = [
  {
    id: "micro-teaching", name: "虚拟微格教学", builtin: true,
    description: "先完善教案设计，再进入课堂推演观察教学风险。",
    steps: [step("F2", "设计修改", "优化或生成本次课堂使用的教案"), step("F3", "课堂推演", "观察真实模型驱动的动态课堂")],
  },
  {
    id: "lesson-polish", name: "教案研磨设计", builtin: true,
    description: "先评价定位问题，再修改设计，最后用课堂推演检验效果。",
    steps: [
      step("F1", "智能评价", "定位教案优势和主要问题"),
      step("F2", "设计修改", "围绕评价结果完成系统优化"),
      step("F3", "课堂推演", "检验教学过程中的潜在风险"),
    ],
  },
  {
    id: "teaching-review", name: "教案评审教研", builtin: true,
    description: "先完成智能评价，再进入协同共析形成可讨论的修订意见。",
    steps: [step("F1", "智能评价", "快速定位关键问题"), step("F4", "协同共析", "逐节判断并保存修订")],
  },
];

const RUN_KEY = "platform-active-workflow-v2";
const CUSTOM_KEY = "platform-custom-workflows-v2";
const SELECTED_KEY = "platform-selected-workflow-v2";
function readJson<T>(key: string, fallback: T): T {
  try { return JSON.parse(window.localStorage.getItem(key) || "") as T; } catch { return fallback; }
}
function loadCustom(): WorkflowTemplate[] {
  return readJson<WorkflowTemplate[]>(CUSTOM_KEY, []).filter(item => item.id && item.name && item.steps?.length === 4)
    .map(item => ({ ...item, builtin: false }));
}
function loadRun(): WorkflowRun | null {
  const value = readJson<WorkflowRun | null>(RUN_KEY, null);
  if (!value?.steps?.length) return null;
  return { ...value, completedIndexes: Array.isArray(value.completedIndexes) ? value.completedIndexes : [] };
}
function destination(feature: FeatureId, run: WorkflowRun, stepIndex = run.currentIndex) {
  if (run.paths?.[String(stepIndex)]) return run.paths[String(stepIndex)];
  const query = run.lessonId && run.versionId ? { lessonId: run.lessonId, versionId: run.versionId, workflow: "1" } : { workflow: "1" };
  if (feature === "F1" && !run.lessonId) return { path: "/review", query };
  if (feature === "F1") return { path: `/lessons/${run.lessonId}/annotate`, query: { version: run.versionId, workflow: "1" } };
  if (feature === "F2") return run.lessonId ? { path: "/optimize-lesson", query } : { path: "/design", query };
  if (feature === "F4") return { path: "/navigation", query: { ...query, autostart: "1" } };
  return { path: "/simulate", query };
}

export const useWorkflowStore = defineStore("workflow", {
  state: () => ({
    customTemplates: loadCustom(),
    selectedTemplateId: window.localStorage.getItem(SELECTED_KEY) || builtinWorkflows[0]!.id,
    activeRun: loadRun() as WorkflowRun | null,
  }),
  getters: {
    templates: state => [...builtinWorkflows, ...state.customTemplates],
    selectedTemplate(): WorkflowTemplate {
      return this.templates.find(item => item.id === this.selectedTemplateId) || builtinWorkflows[0]!;
    },
    activePlan: state => state.activeRun ? {
      id: state.activeRun.templateId, name: state.activeRun.templateName,
      description: "", steps: state.activeRun.steps, builtin: true,
    } as WorkflowTemplate : null,
    currentStep(): WorkflowStep | null {
      return this.activeRun?.steps[this.activeRun.currentIndex] || null;
    },
    isFinished: state => Boolean(state.activeRun?.finishedAt),
    currentDestination(): ReturnType<typeof destination> | null {
      return this.activeRun && this.currentStep ? destination(this.currentStep.id, this.activeRun) : null;
    },
  },
  actions: {
    persistRun() {
      try {
        if (this.activeRun) window.localStorage.setItem(RUN_KEY, JSON.stringify(this.activeRun));
        else window.localStorage.removeItem(RUN_KEY);
      } catch { /* Keep the in-memory state when storage is unavailable. */ }
    },
    persistTemplates() {
      try { window.localStorage.setItem(CUSTOM_KEY, JSON.stringify(this.customTemplates)); } catch { /* Keep in memory. */ }
    },
    selectTemplate(id: string) {
      if (!this.templates.some(item => item.id === id)) return;
      this.selectedTemplateId = id;
      try { window.localStorage.setItem(SELECTED_KEY, id); } catch { /* Keep in memory. */ }
    },
    saveCustom(input: { id?: string; name: string; steps: WorkflowStep[] }) {
      if (input.steps.length !== 4 || new Set(input.steps.map(item => item.id)).size !== 4) return false;
      if (input.steps.some((item, index) => item.id === "F3" && input.steps[index + 1]?.id === "F1")) return false;
      const id = input.id || `custom-${crypto.randomUUID()}`;
      const template: WorkflowTemplate = {
        id, name: input.name.trim(), builtin: false,
        description: "按你设定的四个步骤依次完成教学设计任务。", steps: input.steps,
      };
      const index = this.customTemplates.findIndex(item => item.id === id);
      if (index >= 0) this.customTemplates[index] = template; else this.customTemplates.push(template);
      this.persistTemplates(); this.selectTemplate(id); return true;
    },
    deleteCustom(id: string) {
      this.customTemplates = this.customTemplates.filter(item => item.id !== id);
      if (this.selectedTemplateId === id) this.selectTemplate(builtinWorkflows[0]!.id);
      this.persistTemplates();
    },
    startRun(input?: { lessonId: string; lessonTitle: string; versionId: string; versionNumber: number }, requestedTemplate?: WorkflowTemplate) {
      const template: WorkflowTemplate = requestedTemplate || this.selectedTemplate;
      const now = new Date().toISOString();
      this.activeRun = {
        templateId: template.id, templateName: template.name, steps: template.steps.map(item => ({ ...item })),
        lessonId: input?.lessonId || "", lessonTitle: input?.lessonTitle || "", versionId: input?.versionId || "", versionNumber: input?.versionNumber ?? null,
        currentIndex: 0, completedIndexes: [], paths: {}, startedAt: now, updatedAt: now,
      };
      this.persistRun();
    },
    bindLesson(input: { lessonId: string; lessonTitle: string; versionId: string; versionNumber: number }) {
      if (!this.activeRun) return;
      this.activeRun.lessonId = input.lessonId;
      this.activeRun.lessonTitle = input.lessonTitle;
      this.activeRun.versionId = input.versionId;
      this.activeRun.versionNumber = input.versionNumber;
      this.activeRun.updatedAt = new Date().toISOString();
      this.persistRun();
    },
    completeStep(feature: FeatureId) {
      if (!this.activeRun || this.currentStep?.id !== feature) return;
      if (!this.activeRun.completedIndexes.includes(this.activeRun.currentIndex)) this.activeRun.completedIndexes.push(this.activeRun.currentIndex);
      this.activeRun.currentIndex += 1;
      this.activeRun.updatedAt = new Date().toISOString();
      if (this.activeRun.currentIndex >= this.activeRun.steps.length) this.activeRun.finishedAt = this.activeRun.updatedAt;
      this.persistRun();
    },
    updateVersion(versionId: string, versionNumber?: number) {
      if (!this.activeRun || !versionId) return;
      this.activeRun.versionId = versionId;
      if (typeof versionNumber === "number") this.activeRun.versionNumber = versionNumber;
      this.activeRun.updatedAt = new Date().toISOString(); this.persistRun();
    },
    stepDestination(feature: FeatureId, index?: number) {
      return this.activeRun ? destination(feature, this.activeRun, index ?? this.activeRun.currentIndex) : null;
    },
    rememberPath(feature: FeatureId, path: string) {
      if (!this.activeRun || !path || this.currentStep?.id !== feature) return;
      this.activeRun.paths ||= {}; this.activeRun.paths[String(this.activeRun.currentIndex)] = path;
      this.activeRun.updatedAt = new Date().toISOString(); this.persistRun();
    },
    clearRun() { this.activeRun = null; this.persistRun(); },
  },
});
