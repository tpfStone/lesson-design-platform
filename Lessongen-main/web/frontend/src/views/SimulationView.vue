<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import axios from "axios";
import { useWorkflowStore } from "../stores/workflow";
import LessonSelectorBar, { type LessonOption, type VersionOption } from "../components/LessonSelectorBar.vue";
import AppPageHeader from "../components/AppPageHeader.vue";
import BaseCard from "../components/BaseCard.vue";
import ResultDownloadPanel from "../components/ResultDownloadPanel.vue";
import ConfirmDialog from "../components/ConfirmDialog.vue";

interface Lesson { id: string; title: string; currentVersionId: string }
interface LessonDetail { versions: Array<{ id: string; versionNumber: number; sourceModule?: string }> }
interface SimulationSummary {
  simulationRunId: string; versionId: string; versionNumber: number; status: string;
  completedRounds: number; createdAt: string; f3ModelContent: string;
}
interface ClassroomEvent {
  eventId?: string; sequence?: number; occurredAt?: string; speaker?: string;
  roleLabel?: string; content?: string; status?: string;
  trigger?: { type?: string; content?: string };
  material?: { materialId?: string; title?: string };
}
interface ClassroomIssue {
  nativeIssueId?: string; title?: string; problem?: string; suggestedAction?: string;
  targetLessonSection?: string;
  evidence?: Array<{ eventId?: string; sequence?: number; speaker?: string; contentQuote?: string }>;
}
interface ClassroomAction { actionId?: string; sourceIssueId?: string; action?: string }
interface ClassroomRecord {
  status?: string; modelMode?: string;
  session?: { status?: string; modelMode?: string; activeRoles?: string[] };
  events?: ClassroomEvent[];
  materials?: Array<{ materialId?: string; title?: string }>;
  statistics?: { materialCoverage?: Array<{ materialId?: string; title?: string; covered?: boolean }> };
  summary?: { title?: string; materialsCovered?: string[]; rolesObserved?: string[] };
  issues?: ClassroomIssue[]; actionItems?: ClassroomAction[];
  executionBoundary?: { httpChain?: string; f3ModelContent?: string };
}
interface SimulationDetail extends SimulationSummary {
  materialCount?: number; historyCount?: number;
  startedAt?: string; finishedAt?: string; finalClassroomStatus?: string;
  f3SessionId?: string; f4SessionId?: string;
  summaryMarkdown: string;
  sessionRecord?: ClassroomRecord;
}

const route = useRoute(), router = useRouter();
const workflow = useWorkflowStore();
const lessons = ref<Lesson[]>([]);
const lessonId = ref(typeof route.query.lessonId === "string" ? route.query.lessonId : "");
const chosenLessonId = ref("");
const entered = ref(!!lessonId.value);
interface Launch {
  launchId: string; state: string; simulationRunId: string | null; f3SessionId?: string | null;
  message: string; activeRoles?: string[] | null; timeoutSeconds?: number;
}
const launch = ref<Launch | null>(null);
const starting = ref(false);
const studentRoles = [
  { id: "inquisitive_mind", label: "好奇提问型", description: "喜欢追问原因，表达疑惑" },
  { id: "deep_thinker", label: "深度思考型", description: "深入分析，提出思考性问题" },
  { id: "class_clown", label: "活跃互动型", description: "活跃发言，带来意外互动" },
  { id: "note_taker", label: "认真记录型", description: "关注重点并整理学习内容" },
  { id: "assistant", label: "协作支持型", description: "配合课堂推进，补充回应" },
];
const selectedStudents = ref(["inquisitive_mind", "deep_thinker"]);
const timeoutSeconds = ref(30);
const classroom = ref<{ status?: string; activeRoles?: string[]; limits?: { timeoutSeconds?: number } } | null>(null);
const liveEvents = ref<ClassroomEvent[]>([]);
const pendingMessages = ref<string[]>([]);
const messageDraft = ref("");
const sending = ref(false);
const controlling = ref(false);
const liveError = ref("");
const endDialogOpen = ref(false);
const chatList = ref<HTMLElement | null>(null);
const hasNewEvents = ref(false);
let timer: ReturnType<typeof window.setInterval> | undefined;
let polling = false;
const selectedLesson = computed(() => lessons.value.find(item => item.id === chosenLessonId.value));
const versions = ref<LessonDetail["versions"]>([]);
const versionId = ref(typeof route.query.versionId === "string" ? route.query.versionId : "");
const runs = ref<SimulationSummary[]>([]);
const detail = ref<SimulationDetail | null>(null);
const loading = ref(false);
const error = ref("");
const artifactBase = (runId: string) => `/api/platform/lessons/${encodeURIComponent(lessonId.value)}/simulations/${encodeURIComponent(runId)}/artifacts`;
const visibleRuns = computed(() => versionId.value ? runs.value.filter(run => run.versionId === versionId.value) : runs.value);
const modeLabel = (mode?: string) => mode === "MOCK" ? "模拟回复" : mode === "REAL" ? "真实模型" : "历史记录";
const statusLabel = (status?: string) => ({ COMPLETED: "已完成", FAILED: "运行失败", INTERRUPTED: "已中止", RUNNING: "进行中", PAUSED: "已暂停", QUEUED: "准备中" }[status || ""] || "状态未知");
const roleLabel = (role?: string) => ({ teacher: "教师", assistant: "协作支持型", class_clown: "活跃互动型", deep_thinker: "深度思考型", note_taker: "认真记录型", inquisitive_mind: "好奇提问型", student: "学生" }[role || ""] || "课堂参与者");
const events = computed(() => [...(detail.value?.sessionRecord?.events || [])].sort((a, b) => (a.sequence || 0) - (b.sequence || 0)));
const issues = computed(() => detail.value?.sessionRecord?.issues || []);
const actions = computed(() => detail.value?.sessionRecord?.actionItems || []);
const coverage = computed(() => detail.value?.sessionRecord?.statistics?.materialCoverage || []);
const materialTitle = (id?: string) => coverage.value.find(item => item.materialId === id)?.title
  || detail.value?.sessionRecord?.materials?.find(item => item.materialId === id)?.title || "对应教学环节";

// 问题卡里的 targetLessonSection 可能是 materialId，也可能直接是环节文本。
// 统一先解析成标题，再复用短标签规则，避免“对应环节”再次显示整段正文。
function issueSectionDisplayTitle(target?: string) {
  if (!target) return "教学环节";
  const resolved = coverage.value.find(item => item.materialId === target)?.title
    || detail.value?.sessionRecord?.materials?.find(item => item.materialId === target)?.title
    || target;
  return materialDisplayTitle(resolved);
}

// 课堂界面只展示“教学环节标题 + 时长”，避免把完整 material 正文塞进灰色标签。
// 这里只处理显示文本，不修改 F3 实际收到的 material / teachingScript 数据。
function materialDisplayTitle(raw?: string) {
  if (!raw) return "教学环节";

  const text = raw.replace(/\s+/g, " ").trim();

  // 例如：1. 情境导入（4分钟） 教师活动：……
  //      1. Warm-up（5 分钟）教师活动……
  const bracketMatch = text.match(/^\s*(?:\d+\s*[.、．]\s*)?(.{1,40}?)[（(]\s*(\d+)\s*分钟\s*[）)]/);
  if (bracketMatch) {
    return `${bracketMatch[1].trim()}（${bracketMatch[2]}分钟）`;
  }

  // 兼容：情境导入 4分钟 教师活动……
  const durationMatch = text.match(/^\s*(?:\d+\s*[.、．]\s*)?(.{1,40}?)\s+(\d+)\s*分钟(?:\s|$)/);
  if (durationMatch) {
    return `${durationMatch[1].trim()}（${durationMatch[2]}分钟）`;
  }

  // 没有规范时长格式时，至少在正文标签前截断。
  const marker = /教师活动|学生任务|学生学习任务|学习产出|成功标准|评价证据|评价重点|评价与证据|观察重点|误概念预判|使用资源|使用材料|问题\s*\d*\s*[:：]|预期回答|追问/;
  const markerIndex = text.search(marker);
  const shortTitle = (markerIndex > 0 ? text.slice(0, markerIndex) : text)
    .replace(/^\s*\d+\s*[.、．]\s*/, "")
    .trim();

  // 最后一层纯展示兜底，避免旧数据再次撑爆界面。
  return shortTitle.length > 32 ? `${shortTitle.slice(0, 32)}…` : (shortTitle || "教学环节");
}

// 结果页问题卡片的纯展示兜底：
// 某些 F3 issue 可能把完整 material 正文误拼到 title/problem 前面。
// 这里仅去掉两者共同的超长 material 前缀，不修改后端保存的数据。
function issueSharedMaterialPrefix(issue: ClassroomIssue) {
  const title = (issue.title || "").replace(/\s+/g, " " ).trim();
  const problem = (issue.problem || "").replace(/\s+/g, " " ).trim();
  if (!title || !problem) return "";

  const max = Math.min(title.length, problem.length);
  let index = 0;
  while (index < max && title[index] === problem[index]) index += 1;

  const prefix = title.slice(0, index).trim();
  const looksLikeMaterial = /教师活动|学生任务|学生学习任务|评价证据|评价重点|观察重点|误概念预判|使用资源|使用材料|调控[:：]|问题\s*\d*\s*[:：]/.test(prefix);
  return prefix.length >= 120 && looksLikeMaterial ? prefix : "";
}

function issueDisplayTitle(issue: ClassroomIssue) {
  const raw = (issue.title || "课堂问题").replace(/\s+/g, " " ).trim();
  const prefix = issueSharedMaterialPrefix(issue);
  const cleaned = prefix ? raw.slice(prefix.length).trim() : raw;

  // 若仍然异常超长且明显夹带 material 正文，优先保留末尾的短问题标题。
  if (cleaned.length > 100 && /教师活动|学生任务|评价证据|调控[:：]/.test(cleaned)) {
    const tailAfterParen = cleaned.slice(cleaned.lastIndexOf("）") + 1).trim();
    if (tailAfterParen && tailAfterParen.length <= 80) return tailAfterParen;
  }

  return cleaned.length > 100 ? `${cleaned.slice(0, 100)}…` : cleaned;
}

function issueDisplayProblem(issue: ClassroomIssue) {
  const raw = (issue.problem || "").replace(/\s+/g, " " ).trim();
  const prefix = issueSharedMaterialPrefix(issue);
  let cleaned = prefix ? raw.slice(prefix.length).trim() : raw;

  // 被去掉的前缀通常就是对应教学环节正文；若剩余句子以“中……”开头，
  // 补回短环节名，让用户读起来仍然完整。
  if (prefix && /^中/.test(cleaned) && issue.targetLessonSection) {
    cleaned = `${issueSectionDisplayTitle(issue.targetLessonSection)}${cleaned}`;
  }

  return cleaned || "暂无问题说明。";
}
const downloads = computed(() => detail.value ? [
  { key: "md", label: "课堂简报", href: artifactBase(detail.value.simulationRunId) + "/md" },
  { key: "json", label: "完整课堂记录", href: artifactBase(detail.value.simulationRunId) + "/json" },
] : []);
const liveStatus = computed(() => classroom.value?.status || launch.value?.state || "QUEUED");
const liveRoleLabels = computed(() => (classroom.value?.activeRoles || launch.value?.activeRoles || ["teacher", ...selectedStudents.value]).map(roleLabel));
const liveCoverage = computed(() => liveEvents.value.reduce((items, event) => {
  if (event.material?.materialId && !items.some(item => item.materialId === event.material?.materialId))
    items.push({ materialId: event.material.materialId, title: event.material.title || "教学环节" });
  return items;
}, [] as Array<{ materialId: string; title: string }>));
function toggleStudent(role: string) {
  selectedStudents.value = selectedStudents.value.includes(role)
    ? selectedStudents.value.filter(item => item !== role)
    : [...selectedStudents.value, role];
}
function scrollToLatest() {
  if (chatList.value) chatList.value.scrollTop = chatList.value.scrollHeight;
  hasNewEvents.value = false;
}
async function refreshClassroom(id: string) {
  if (!launch.value?.f3SessionId) return;
  try {
    const [state, feed] = await Promise.all([
      axios.get<{ status?: string; activeRoles?: string[]; limits?: { timeoutSeconds?: number } }>(`/api/platform/simulation-launches/${encodeURIComponent(id)}/classroom`),
      axios.get<{ events?: ClassroomEvent[] }>(`/api/platform/simulation-launches/${encodeURIComponent(id)}/events`),
    ]);
    if (!classroom.value && state.data.limits?.timeoutSeconds) timeoutSeconds.value = state.data.limits.timeoutSeconds;
    classroom.value = state.data;
    const nearBottom = !chatList.value || chatList.value.scrollHeight - chatList.value.scrollTop - chatList.value.clientHeight < 100;
    const latest = (feed.data.events || []).sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
    const changed = latest.length > liveEvents.value.length;
    liveEvents.value = latest;
    pendingMessages.value = pendingMessages.value.filter(message => !latest.some(event => event.trigger?.content === message));
    if (changed) {
      await nextTick();
      if (nearBottom) scrollToLatest(); else hasNewEvents.value = true;
    }
    liveError.value = "";
  } catch (reason) {
    liveError.value = axios.isAxiosError(reason) ? (reason.response?.data as { detail?: string })?.detail || reason.message : "读取课堂过程失败";
  }
}
async function sendMessage() {
  const content = messageDraft.value.trim();
  if (!content || !launch.value?.f3SessionId || sending.value) return;
  sending.value = true; liveError.value = "";
  try {
    await axios.post(`/api/platform/simulation-launches/${encodeURIComponent(launch.value.launchId)}/messages`, { message: content });
    pendingMessages.value.push(content);
    messageDraft.value = "";
    await nextTick(); scrollToLatest();
  } catch (reason) {
    liveError.value = axios.isAxiosError(reason) ? (reason.response?.data as { detail?: string })?.detail || reason.message : "消息未能发送";
  } finally { sending.value = false; }
}
async function classroomAction(action: "pause" | "resume" | "end") {
  if (!launch.value?.f3SessionId || controlling.value) return;
  controlling.value = true; liveError.value = "";
  try {
    classroom.value = (await axios.post<typeof classroom.value>(`/api/platform/simulation-launches/${encodeURIComponent(launch.value.launchId)}/${action}`)).data;
    if (action === "end") endDialogOpen.value = false;
  } catch (reason) {
    liveError.value = axios.isAxiosError(reason) ? (reason.response?.data as { detail?: string })?.detail || reason.message : "课堂操作未完成";
  } finally { controlling.value = false; }
}
async function changeTimeout() {
  if (!launch.value?.f3SessionId || controlling.value) return;
  controlling.value = true; liveError.value = "";
  const previous = classroom.value?.limits?.timeoutSeconds;
  try {
    classroom.value = (await axios.patch<typeof classroom.value>(`/api/platform/simulation-launches/${encodeURIComponent(launch.value.launchId)}/settings`, { timeoutSeconds: timeoutSeconds.value })).data;
  } catch (reason) {
    if (previous) timeoutSeconds.value = previous;
    liveError.value = axios.isAxiosError(reason) ? (reason.response?.data as { detail?: string })?.detail || reason.message : "课堂设置未能保存";
  } finally { controlling.value = false; }
}
const elapsed = computed(() => {
  if (!detail.value?.startedAt || !detail.value?.finishedAt) return "—";
  const seconds = Math.max(0, Math.round((Date.parse(detail.value.finishedAt) - Date.parse(detail.value.startedAt)) / 1000));
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
});
function onSelection(lesson: LessonOption | null, version: VersionOption | null) {
  chosenLessonId.value = lesson?.id || ""; versionId.value = version?.id || "";
}
function confirmSelection(lesson: LessonOption, version: VersionOption) {
  chosenLessonId.value = lesson.id; versionId.value = version.id;
  if (workflow.activeRun && !workflow.activeRun.lessonId && workflow.currentStep?.id === "F3") {
    workflow.bindLesson({ lessonId: lesson.id, lessonTitle: lesson.title, versionId: version.id, versionNumber: version.versionNumber });
  }
  void enter();
}
async function chooseLesson(id: string) {
  chosenLessonId.value = id; versions.value = []; versionId.value = ""; error.value = "";
  try {
    const selected = lessons.value.find(item => item.id === id);
    const detail = (await axios.get<LessonDetail>(`/api/platform/lessons/${encodeURIComponent(id)}`)).data;
    versions.value = [...detail.versions].sort((a, b) => b.versionNumber - a.versionNumber);
    versionId.value = selected?.currentVersionId || "";
  } catch (reason) { error.value = axios.isAxiosError(reason) ? reason.message : "读取版本失败"; }
}
async function enter() {
  if (!chosenLessonId.value || !versionId.value) return;
  lessonId.value = chosenLessonId.value; entered.value = true;
  await router.push({ path: "/simulate", query: { lessonId: lessonId.value, versionId: versionId.value } });
  await loadRuns();
}
async function poll(id: string) {
  if (polling) return;
  polling = true;
  try {
    const current = (await axios.get<Launch>(`/api/platform/simulation-launches/${encodeURIComponent(id)}`)).data;
    launch.value = current;
    if (current.f3SessionId && current.state === "RUNNING") await refreshClassroom(id);
    if (current.state === "COMPLETED" || current.state === "INTERRUPTED") {
      if (timer) window.clearInterval(timer); timer = undefined; starting.value = false;
      await loadRuns();
      if (current.simulationRunId) await openRun(current.simulationRunId);
      if (current.state === "COMPLETED" && workflow.activeRun?.lessonId === lessonId.value && workflow.activeRun.versionId === versionId.value) {
        workflow.rememberPath("F3", `/simulate?lessonId=${encodeURIComponent(lessonId.value)}&versionId=${encodeURIComponent(versionId.value)}`);
        workflow.completeStep("F3");
      }
    } else if (current.state === "FAILED") {
      if (timer) window.clearInterval(timer); timer = undefined; starting.value = false;
      error.value = current.message;
    }
  } catch (reason) {
    if (timer) window.clearInterval(timer); timer = undefined; starting.value = false;
    if (axios.isAxiosError(reason) && reason.response?.status === 404) {
      launch.value = null;
      error.value = "";
      await router.replace({ path: "/simulate", query: { lessonId: lessonId.value, versionId: versionId.value } });
      return;
    }
    error.value = axios.isAxiosError(reason)
      ? (reason.response?.data as { detail?: string })?.detail || reason.message
      : "查询模拟状态失败";
  } finally { polling = false; }
}
async function start() {
  if (starting.value || !lessonId.value || !versionId.value) return;
  starting.value = true; error.value = "";
  try {
    classroom.value = null; liveEvents.value = []; pendingMessages.value = []; detail.value = null;
    launch.value = (await axios.post<Launch>("/api/platform/simulation-launches", {
      lessonId: lessonId.value, versionId: versionId.value, requestKey: crypto.randomUUID(),
      activeRoles: ["teacher", ...selectedStudents.value], timeoutSeconds: timeoutSeconds.value,
    })).data;
    const id = launch.value.launchId;
    await router.replace({ path: "/simulate", query: { lessonId: lessonId.value, versionId: versionId.value, launchId: id } });
    await poll(id);
    if (starting.value) timer = window.setInterval(() => { void poll(id); }, 2500);
  } catch (reason) { starting.value = false; error.value = axios.isAxiosError(reason) ? (reason.response?.data as { detail?: string })?.detail || reason.message : "启动模拟失败"; }
}

async function loadRuns() {
  runs.value = []; versions.value = []; detail.value = null; error.value = "";
  if (!lessonId.value) return;
  loading.value = true;
  try {
    const selected = lessons.value.find(item => item.id === lessonId.value);
    const lesson = (await axios.get<LessonDetail>(`/api/platform/lessons/${encodeURIComponent(lessonId.value)}`)).data;
    versions.value = [...lesson.versions].sort((a, b) => b.versionNumber - a.versionNumber);
    if (versionId.value && !versions.value.some(v => v.id === versionId.value)) versionId.value = "";
    if (!versionId.value) versionId.value = selected?.currentVersionId || "";
    runs.value = (await axios.get<SimulationSummary[]>(`/api/platform/lessons/${encodeURIComponent(lessonId.value)}/simulations`)).data;
  } catch (reason) { error.value = axios.isAxiosError(reason) ? reason.message : "读取模拟记录失败"; }
  finally { loading.value = false; }
}
async function openRun(runId: string) {
  detail.value = null; error.value = "";
  try {
    detail.value = (await axios.get<SimulationDetail>(`/api/platform/lessons/${encodeURIComponent(lessonId.value)}/simulations/${encodeURIComponent(runId)}`)).data;
  } catch (reason) { error.value = axios.isAxiosError(reason) ? reason.message : "读取模拟详情失败"; }
}
onMounted(async () => {
  try {
    lessons.value = (await axios.get<Lesson[]>("/api/platform/lessons")).data;
  } catch (reason) { error.value = axios.isAxiosError(reason) ? reason.message : "读取教案列表失败"; }
  if (lessonId.value) {
    entered.value = true; await chooseLesson(lessonId.value);
    const requested = typeof route.query.versionId === "string" ? route.query.versionId : "";
    if (versions.value.some(v => v.id === requested)) versionId.value = requested;
    await loadRuns();
    const id = typeof route.query.launchId === "string" ? route.query.launchId : "";
    if (id) { starting.value = true; await poll(id); if (starting.value) timer = window.setInterval(() => { void poll(id); }, 2500); }
  }
});
watch(lessonId, () => { if (entered.value) void loadRuns(); });
watch(() => route.query.lessonId, value => {
  if (typeof value === "string" && value !== lessonId.value) lessonId.value = value;
  if (typeof value !== "string") {
    lessonId.value = ""; entered.value = false; detail.value = null; launch.value = null;
    if (timer) window.clearInterval(timer); timer = undefined; starting.value = false;
  }
});
watch(versionId, () => { detail.value = null; });
onBeforeUnmount(() => { if (timer) window.clearInterval(timer); });
</script>

<template>
  <div class="simulation-page">
    <AppPageHeader title="课堂推演" description="通过虚拟课堂预演教学过程，查看课堂记录与改进建议。" />
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <LessonSelectorBar v-if="!entered" :initial-lesson-id="chosenLessonId" :initial-version-id="versionId" action-label="确认使用此教案" @selection="onSelection" @action="confirmSelection" />

    <template v-if="entered">
      <BaseCard class="start-card">
        <div class="start-heading"><div><span class="subtle">当前教案</span><h2>{{ selectedLesson?.title || '所选教案' }} · V{{ versions.find(v => v.id === versionId)?.versionNumber ?? '—' }}</h2></div>
          <RouterLink v-if="!workflow.activeRun?.lessonId" to="/simulate">重新选择</RouterLink></div>
        <p v-if="!starting">开始后将按教案自主推进课堂。角色和等待时间在本次课堂开始后确定。</p>
        <p v-else class="running-status" role="status">{{ launch?.message || '正在建立课堂' }}。离开后可通过当前页面地址查看进度。</p>
      </BaseCard>

      <template v-if="!starting">
        <BaseCard class="roles-card"><h3>课堂角色</h3><p class="subtle">教师固定参与。勾选需要进入课堂的学生角色。</p>
          <div class="teacher-role"><strong>教师</strong><span>固定参与</span></div>
          <div class="role-options"><label v-for="role in studentRoles" :key="role.id" class="role-option" :class="{ selected: selectedStudents.includes(role.id) }">
            <input type="checkbox" :checked="selectedStudents.includes(role.id)" @change="toggleStudent(role.id)" />
            <span><strong>{{ role.label }}</strong><small>{{ role.description }}</small></span>
          </label></div>
          <p class="subtle">本次课堂：1 位教师 + {{ selectedStudents.length }} 类学生角色</p>
        </BaseCard>
        <BaseCard class="settings-card"><h3>课堂设置</h3><label for="initial-timeout">自动继续等待时间</label>
          <select id="initial-timeout" v-model.number="timeoutSeconds"><option :value="15">15 秒</option><option :value="30">30 秒</option><option :value="45">45 秒</option><option :value="60">60 秒</option></select>
          <p class="subtle">等待期间没有新的输入，课堂将自主继续。</p>
        </BaseCard>
        <button type="button" class="v2-button v2-button--primary" :disabled="starting || !versionId" @click="start">{{ starting ? '正在推演……' : '开始课堂推演' }}</button>
      </template>

      <div v-if="starting" class="live-section">
        <div class="live-title"><h2>虚拟课堂</h2><span class="v2-status v2-status--active">{{ statusLabel(liveStatus) }}</span></div>
        <p v-if="liveError" class="error" role="alert">{{ liveError }}</p>
        <div v-if="launch?.f3SessionId" class="live-layout">
          <BaseCard class="chat-card">
            <div ref="chatList" class="chat-list" aria-live="polite"><p v-if="!liveEvents.length" class="subtle">课堂正在准备发言……</p>
              <template v-for="(event, index) in liveEvents" :key="event.eventId || index">
                <div v-if="event.trigger?.type === 'USER_INPUT' && event.trigger.content" class="chat-entry own"><strong>教师 · 你的输入</strong><p>{{ event.trigger.content }}</p></div>
                <div class="chat-entry"><div><strong>{{ event.roleLabel || roleLabel(event.speaker) }}</strong><small>{{ materialDisplayTitle(event.material?.title) }}</small></div><p>{{ event.content || '课堂已推进到下一环节。' }}</p></div>
              </template>
              <div v-for="(message, index) in pendingMessages" :key="`pending-${index}`" class="chat-entry own"><strong>教师 · 你的输入 <small>等待课堂处理</small></strong><p>{{ message }}</p></div>
            </div>
            <button v-if="hasNewEvents" type="button" class="new-events" @click="scrollToLatest">有新课堂消息，查看最新</button>
            <div class="compose"><label for="classroom-message">向课堂发送内容</label><textarea id="classroom-message" v-model="messageDraft" rows="3" :disabled="liveStatus !== 'RUNNING' || sending" placeholder="可以补充讲解、提出问题或调整课堂方向" />
              <button type="button" class="v2-button v2-button--primary" :disabled="!messageDraft.trim() || sending || liveStatus !== 'RUNNING'" @click="sendMessage">{{ sending ? '发送中……' : '发送' }}</button>
            </div>
          </BaseCard>
          <aside class="live-side">
            <BaseCard><h3>本次课堂角色</h3><p class="role-list">{{ liveRoleLabels.join(' · ') }}</p></BaseCard>
            <BaseCard><h3>已涉及的教学环节</h3><p v-if="!liveCoverage.length" class="subtle">等待课堂开始……</p><ol v-else class="coverage-list"><li v-for="item in liveCoverage" :key="item.materialId"><span>·</span>{{ materialDisplayTitle(item.title) }}</li></ol></BaseCard>
            <BaseCard><h3>课堂设置</h3><label for="live-timeout">自动继续等待时间</label><select id="live-timeout" v-model.number="timeoutSeconds" :disabled="controlling || !['RUNNING', 'PAUSED'].includes(liveStatus)" @change="changeTimeout"><option :value="15">15 秒</option><option :value="30">30 秒</option><option :value="45">45 秒</option><option :value="60">60 秒</option></select></BaseCard>
          </aside>
        </div>
        <p v-else class="subtle">正在建立课堂会话，准备完成后会显示实时记录。</p>
        <div v-if="launch?.f3SessionId" class="live-actions"><button v-if="liveStatus === 'RUNNING'" type="button" class="v2-button v2-button--secondary" :disabled="controlling" @click="classroomAction('pause')">暂停课堂</button>
          <button v-if="liveStatus === 'PAUSED'" type="button" class="v2-button v2-button--secondary" :disabled="controlling" @click="classroomAction('resume')">继续课堂</button>
          <button v-if="['RUNNING', 'PAUSED'].includes(liveStatus)" type="button" class="v2-button v2-button--secondary" :disabled="controlling" @click="endDialogOpen = true">结束课堂</button></div>
      </div>

      <BaseCard class="history-card">
        <h2>课堂推演记录</h2>
        <p v-if="loading" role="status">正在读取记录……</p>
        <p v-else-if="!visibleRuns.length" class="subtle">当前版本还没有课堂推演记录。</p>
        <div v-for="run in visibleRuns" :key="run.simulationRunId" class="run-row">
          <div><strong>V{{ run.versionNumber }} · {{ statusLabel(run.status) }}</strong><small>{{ new Date(run.createdAt).toLocaleString('zh-CN') }}</small></div>
          <span class="mode-badge" :class="{ mock: run.f3ModelContent === 'MOCK', real: run.f3ModelContent === 'REAL' }">{{ modeLabel(run.f3ModelContent) }}</span>
          <button type="button" class="v2-button v2-button--secondary" @click="openRun(run.simulationRunId)">查看结果</button>
        </div>
      </BaseCard>

      <template v-if="detail">
        <div class="result-heading"><div><span class="subtle">课堂推演结果</span><h2>{{ selectedLesson?.title || '所选教案' }} · V{{ detail.versionNumber }}</h2></div><span class="mode-badge" :class="{ mock: detail.f3ModelContent === 'MOCK', real: detail.f3ModelContent === 'REAL' }">{{ modeLabel(detail.f3ModelContent) }}</span></div>
        <p v-if="detail.f3ModelContent === 'MOCK'" class="mock-notice">这次使用模拟回复，供流程测试；正式使用请重新启动真实模型推演。</p>
        <div class="result-stats">
          <div><small>课堂状态</small><strong>{{ statusLabel(detail.status) }}</strong></div>
          <div><small>课堂事件</small><strong>{{ events.length }}</strong></div>
          <div><small>教学环节</small><strong>{{ coverage.length || detail.materialCount || detail.sessionRecord?.materials?.length || 0 }}</strong></div>
          <div><small>运行耗时</small><strong>{{ elapsed }}</strong></div>
        </div>

        <div class="result-layout">
          <BaseCard class="events-card"><h3>课堂记录</h3><p v-if="!events.length" class="subtle">这次记录没有可展示的课堂事件，请查看完整记录文件。</p>
            <template v-for="(event, index) in events" :key="event.eventId || index">
              <div v-if="event.trigger?.type === 'USER_INPUT' && event.trigger.content" class="event-row own-input"><strong>教师 · 你的输入</strong><p>{{ event.trigger.content }}</p></div>
              <div class="event-row"><div class="event-meta"><strong>{{ event.roleLabel || roleLabel(event.speaker) }}</strong><span>{{ materialDisplayTitle(event.material?.title || materialTitle(event.material?.materialId)) }}</span><time v-if="event.occurredAt">{{ new Date(event.occurredAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</time></div>
                <p>{{ event.content || '本事件没有文字内容。' }}</p></div>
            </template>
          </BaseCard>
          <aside v-if="coverage.length || detail.sessionRecord?.session?.activeRoles?.length" class="progress-side">
            <BaseCard v-if="coverage.length"><h3>教学进度</h3><ol class="coverage-list"><li v-for="item in coverage" :key="item.materialId" :class="{ covered: item.covered }"><span>{{ item.covered ? '✓' : '○' }}</span>{{ materialDisplayTitle(item.title) }}</li></ol></BaseCard>
            <BaseCard v-if="detail.sessionRecord?.session?.activeRoles?.length"><h3>参与角色</h3><p class="role-list">{{ detail.sessionRecord.session.activeRoles.map(roleLabel).join(' · ') }}</p></BaseCard>
          </aside>
        </div>

        <BaseCard class="summary-card"><h3>课堂简报</h3><p>本次推演记录了 {{ events.length }} 个课堂事件，涉及 {{ detail.sessionRecord?.summary?.materialsCovered?.length ?? coverage.length ?? detail.materialCount }} 个教学环节；发现 {{ issues.length }} 项值得关注的问题。</p></BaseCard>
        <BaseCard class="issues-card"><h3>发现的问题 <span>{{ issues.length }}</span></h3><p v-if="!issues.length" class="subtle">本次没有通过分析校验的课堂问题。</p>
          <article v-for="(issue, index) in issues" :key="issue.nativeIssueId || index" class="issue-row"><h4>{{ issueDisplayTitle(issue) }}</h4><p>{{ issueDisplayProblem(issue) }}</p><p v-if="issue.targetLessonSection" class="subtle">对应环节：{{ issueSectionDisplayTitle(issue.targetLessonSection) }}</p><p v-if="issue.suggestedAction"><strong>改进建议：</strong>{{ issue.suggestedAction }}</p>
            <details v-if="issue.evidence?.length"><summary>查看课堂依据</summary><blockquote v-for="(evidence, evidenceIndex) in issue.evidence" :key="evidence.eventId || evidenceIndex">{{ roleLabel(evidence.speaker) }}：{{ evidence.contentQuote }}</blockquote></details>
          </article>
        </BaseCard>
        <BaseCard v-if="actions.length"><h3>后续改进建议</h3><ul class="action-list"><li v-for="(action, index) in actions" :key="action.actionId || index">{{ action.action }}</li></ul></BaseCard>
        <ResultDownloadPanel :files="downloads" title="结果文件" description="下载课堂简报或完整记录。" />
      </template>
    </template>
    <ConfirmDialog :open="endDialogOpen" title="提前结束本次课堂？" description="将保存已经发生的课堂记录；这次推演会标记为提前结束。" confirm-text="结束课堂" @cancel="endDialogOpen = false" @confirm="classroomAction('end')" />
  </div>
</template>

<style scoped>
.simulation-page { color: var(--color-text); }
.simulation-page > .error { margin: 18px 0; padding: 12px 14px; border-radius: var(--radius-md); color: var(--color-danger); background: var(--color-danger-soft); }
.simulation-page .v2-card { margin-top: var(--space-6); }
.start-heading, .result-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-4); }
.start-heading h2, .result-heading h2 { margin: 5px 0 0; font-size: 20px; }
.start-heading a { color: var(--color-primary); font-size: 13px; }
.start-card p { color: var(--color-text-secondary); }
.start-card .running-status { margin-bottom: 0; color: var(--color-primary); }
.subtle { color: var(--color-text-muted); font-size: 13px; }
.history-card h2 { margin: 0 0 14px; font-size: 20px; }
.history-card .run-row { display: flex; align-items: center; gap: 14px; padding: 12px 0; border-top: 1px solid var(--color-border); }
.history-card .run-row > div { flex: 1; min-width: 0; }
.history-card .run-row small { display: block; margin-top: 3px; color: var(--color-text-muted); }
.history-card .run-row button { margin-left: auto; white-space: nowrap; }
.result-heading { align-items: center; margin-top: var(--space-8); }
.mode-badge { padding: 5px 10px; border-radius: var(--radius-sm); color: var(--color-text-secondary); background: var(--color-surface-soft); font-size: 12px; white-space: nowrap; }
.mode-badge.real { color: var(--color-primary); background: var(--color-primary-soft); }
.mode-badge.mock { color: var(--color-attention); background: var(--color-attention-soft); }
.mock-notice { padding: 12px 14px; border-radius: var(--radius-md); color: var(--color-attention); background: var(--color-attention-soft); }
.result-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 20px 0; }
.result-stats > div { padding: 14px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); }
.result-stats small, .result-stats strong { display: block; }
.result-stats small { color: var(--color-text-muted); }
.result-stats strong { margin-top: 6px; font-size: 19px; }
.result-layout { display: grid; grid-template-columns: minmax(0, 1fr) 270px; align-items: start; gap: 18px; }
.result-layout > .v2-card, .progress-side .v2-card { margin-top: 0; }
.progress-side { display: grid; gap: 18px; }
.simulation-page h3 { margin: 0 0 16px; font-size: 18px; }
.events-card { min-width: 0; }
.event-row { padding: 16px 0; border-top: 1px solid var(--color-border); }
.event-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 14px; }
.event-meta strong { color: var(--color-primary); }
.event-meta span, .event-meta time { color: var(--color-text-muted); font-size: 12px; }
.event-meta time { margin-left: auto; }
.event-row p { margin: 10px 0 0; color: var(--color-text); line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.own-input { margin-left: 10%; padding: 12px; border-color: var(--color-primary-border); background: var(--color-primary-soft); }
.own-input strong { color: var(--color-primary); }
.coverage-list { display: grid; gap: 10px; padding: 0; list-style: none; }
.coverage-list li { display: flex; align-items: flex-start; gap: 8px; color: var(--color-text-muted); font-size: 13px; }
.coverage-list li.covered { color: var(--color-text); }
.coverage-list span { color: var(--color-primary); }
.role-list { margin: 0; color: var(--color-text-secondary); line-height: 1.7; }
.summary-card { border-color: var(--color-border); background: var(--color-surface); }
.summary-card p, .issue-row p, .action-list { color: var(--color-text-secondary); line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.issues-card h3 span { color: var(--color-text-muted); font-size: 14px; }
.issue-row { padding: 18px 0; border-top: 1px solid var(--color-border); }
.issue-row h4 { margin: 0; font-size: 16px; }
.issue-row p { margin: 8px 0 0; }
.issue-row details { margin-top: 12px; }
.issue-row summary { color: var(--color-primary); cursor: pointer; }
.issue-row blockquote { margin: 9px 0; padding: 10px 14px; border-left: 3px solid var(--color-primary-border); background: var(--color-surface-soft); white-space: pre-wrap; }
.action-list { display: grid; gap: 12px; padding-left: 20px; }
.roles-card h3, .settings-card h3 { margin-bottom: 8px; }
.teacher-role { display: flex; align-items: center; justify-content: space-between; gap: 12px; max-width: 520px; margin: 18px 0; padding: 14px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-md); background: var(--color-primary-soft); }
.teacher-role span { color: var(--color-primary); font-size: 12px; font-weight: 700; }
.role-options { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }
.role-option { display: flex; align-items: flex-start; gap: 10px; min-height: 74px; padding: 14px; border: 1px solid var(--color-border); border-radius: var(--radius-md); cursor: pointer; }
.role-option.selected { border-color: var(--color-primary); background: var(--color-primary-soft); }
.role-option input { margin-top: 3px; accent-color: var(--color-primary); }
.role-option span, .role-option small { display: block; }
.role-option small { margin-top: 4px; color: var(--color-text-secondary); line-height: 1.5; }
.settings-card label, .live-side label { display: block; margin-bottom: 8px; font-weight: 700; }
.settings-card select, .live-side select { min-height: 40px; padding: 0 12px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: #fff; }
.settings-card + .v2-button { margin-top: 18px; }
.live-section { margin-top: var(--space-8); }
.live-title { display: flex; align-items: center; gap: 14px; }
.live-title h2 { margin: 0; font-size: 22px; }
.live-layout { display: grid; grid-template-columns: minmax(0, 1fr) 250px; gap: 18px; margin-top: 16px; }
.live-layout .v2-card { margin-top: 0; }
.live-side { display: grid; align-content: start; gap: 16px; }
.chat-card { min-width: 0; }
.chat-list { height: min(56vh, 600px); min-height: 280px; overflow-y: auto; overscroll-behavior: contain; padding-right: 8px; }
.chat-entry { max-width: 90%; margin: 0 0 18px; padding: 13px 15px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface-soft); }
.chat-entry.own { margin-left: auto; border-color: var(--color-primary-border); background: var(--color-primary-soft); }
.chat-entry > div { display: flex; flex-wrap: wrap; gap: 10px; }
.chat-entry strong { color: var(--color-primary); }
.chat-entry small { color: var(--color-text-muted); font-weight: 400; }
.chat-entry p { margin: 8px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; }
.new-events { display: block; margin: 8px auto; border: 0; color: var(--color-primary); background: transparent; cursor: pointer; }
.compose { display: grid; gap: 8px; padding-top: 15px; border-top: 1px solid var(--color-border); }
.compose label { font-weight: 700; }
.compose textarea { width: 100%; min-height: 80px; resize: vertical; padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius-md); font: inherit; }
.compose button { justify-self: end; }
.live-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 16px; }
.live-section .error { padding: 12px; border-radius: var(--radius-md); color: var(--color-danger); background: var(--color-danger-soft); }
@media (max-width: 850px) { .result-layout { grid-template-columns: 1fr; }.progress-side { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 850px) { .live-layout { grid-template-columns: 1fr; }.live-side { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 650px) { .result-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }.progress-side, .live-side { grid-template-columns: 1fr; }.history-card .run-row { align-items: flex-start; flex-wrap: wrap; }.history-card .run-row button { margin: 0; }.start-heading, .result-heading { flex-direction: column; } }
</style>
