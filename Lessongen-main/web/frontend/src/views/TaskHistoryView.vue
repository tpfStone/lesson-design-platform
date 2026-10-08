<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter, type RouteLocationRaw } from "vue-router";
import axios from "axios";
import AppPageHeader from "../components/AppPageHeader.vue";
import { listJobs } from "../api/client";
import type { JobSummary } from "../types/api";

interface Lesson { id:string; title:string }
interface Version { id:string; versionNumber:number }
interface LessonDetail { lesson:Lesson; versions:Version[] }
interface Binding { jobId:string; lessonId:string; lessonTitle:string; sourceVersionId:string; savedVersionId:string|null; status:string }
interface Annotation { createdAt?:string; id:string; versionId:string; state:{status:string}|null }
interface Simulation { createdAt?:string; simulationRunId:string; versionId:string; status:string; f4SessionId?:string }
interface SimulationLaunch { launchId:string; lessonId:string; versionId:string; state:string; simulationRunId?:string|null; f3SessionId?:string|null; f4SessionId?:string|null; message?:string; createdAt?:string }
interface F4Session { id:string; status:string; created_at?:string; createdAt?:string; updated_at?:string; updatedAt?:string; lesson_metadata?:{topic?:string} }
interface F4Binding { lessonId:string; title:string; sourceVersionId:string; sourceVersionNumber:number; currentVersionId:string; currentVersionNumber:number }
interface TaskRow { createdAt?:string; key:string; title:string; version:string; kind:string; status:string; to:RouteLocationRaw }

const router = useRouter();
const rows = ref<TaskRow[]>([]), loading = ref(false), error = ref("");
const kindFilter = ref("ALL"), statusFilter = ref("ALL"), order = ref("DESC");
const statusText:Record<string,string>={QUEUED:"排队中",DISPATCHING:"准备中",PREPROCESSING:"解析中",RUNNING:"进行中",EXPORTING:"整理结果",COMPLETED:"已完成",NEEDS_HUMAN:"待教师确认",REVIEWED:"教师已复核",FAILED:"失败",CREATED:"已创建",ACTIVE:"修订中",ROUND_COMPLETED:"本轮已完成",TERMINATED:"已完成",INTERRUPTED:"已中断"};
const statusGroup=(status:string)=>status==="FAILED"||status==="INTERRUPTED"?"FAILED":status==="COMPLETED"||status==="REVIEWED"||status==="TERMINATED"?"DONE":"ACTIVE";
const filtered=computed(()=>rows.value.filter(row=>(kindFilter.value==="ALL"||row.kind===kindFilter.value)&&(statusFilter.value==="ALL"||statusGroup(row.status)===statusFilter.value)).sort((a,b)=>(Date.parse(b.createdAt||"")-Date.parse(a.createdAt||""))*(order.value==="DESC"?1:-1)));
function describe(reason:unknown){return axios.isAxiosError(reason)?((reason.response?.data as {detail?:string})?.detail||reason.message):String(reason)}
function versionLabel(map:Map<string,number>,id?:string|null){const value=id?map.get(id):undefined;return typeof value==="number"?`V${value}`:"—"}
async function load(){
  loading.value=true;error.value="";
  try{
    const lessons=(await axios.get<Lesson[]>("/api/platform/lessons")).data;
    const details=await Promise.all(lessons.map(lesson=>axios.get<LessonDetail>(`/api/platform/lessons/${encodeURIComponent(lesson.id)}`).then(r=>r.data)));
    const versionNumbers=new Map(details.flatMap(detail=>detail.versions.map(version=>[version.id,version.versionNumber] as const)));
    const [jobPage,bindingsResult,f4Result,launches,annotations,simulations]=await Promise.all([
      listJobs(0,50),axios.get<Binding[]>("/api/platform/optimizations").then(r=>r.data).catch(()=>[]),axios.get<F4Session[]>("/api/platform/f4/sessions").then(r=>r.data).catch(()=>[]),
      axios.get<SimulationLaunch[]>("/api/platform/simulation-launches").then(r=>r.data).catch(()=>[]),
      Promise.all(lessons.map(async lesson=>{
        const runs=await axios.get<Annotation[]>(`/api/platform/lessons/${encodeURIComponent(lesson.id)}/annotations`).then(r=>r.data).catch(()=>[]);
        const withState=await Promise.all(runs.map(async run=>axios.get<Annotation>(`/api/platform/lessons/${encodeURIComponent(lesson.id)}/annotations/${encodeURIComponent(run.id)}`).then(r=>r.data).catch(()=>run)));
        return {lesson,runs:withState};
      })),
      Promise.all(lessons.map(async lesson=>({lesson,runs:await axios.get<Simulation[]>(`/api/platform/lessons/${encodeURIComponent(lesson.id)}/simulations`).then(r=>r.data).catch(()=>[])})))
    ]);
    const bindings=new Map(bindingsResult.map(item=>[item.jobId,item]));
    const f2:TaskRow[]=jobPage.items.map((job:JobSummary)=>{const binding=bindings.get(job.jobId);return{key:`F2:${job.jobId}`,title:binding?.lessonTitle||job.topic||"未命名教案",version:versionLabel(versionNumbers,binding?.savedVersionId||binding?.sourceVersionId),kind:job.mode==="GENERATE"?"教案生成":"设计修改",createdAt:job.createdAt,status:binding?.savedVersionId?"REVIEWED":job.status,to:{path:`/jobs/${job.jobId}`,query:binding?{lessonId:binding.lessonId}:{}}}});
    const f1=annotations.flatMap(({lesson,runs})=>runs.map<TaskRow>(run=>({key:`F1:${run.id}`,title:lesson.title,version:versionLabel(versionNumbers,run.versionId),kind:"智能评价",createdAt:run.createdAt,status:run.state?.status||"CREATED",to:{path:`/lessons/${lesson.id}/annotate`,query:{version:run.versionId}}})));
    const simulationEntries=simulations.flatMap(({lesson,runs})=>runs.map(run=>({lesson,run})));
    const simulationDetails=await Promise.all(simulationEntries.map(({lesson,run})=>
      axios.get<Simulation>(`/api/platform/lessons/${encodeURIComponent(lesson.id)}/simulations/${encodeURIComponent(run.simulationRunId)}`)
        .then(response=>response.data).catch(()=>run)));
    const f3=simulationEntries.map<TaskRow>(({lesson,run})=>({key:`F3:${run.simulationRunId}`,title:lesson.title,version:versionLabel(versionNumbers,run.versionId),kind:"课堂推演",createdAt:run.createdAt,status:run.status,to:{path:"/simulate",query:{lessonId:lesson.id,versionId:run.versionId}}}));
    const savedSimulationIds=new Set(f3.map(row=>row.key.slice(3)));
    const lessonTitles=new Map(lessons.map(lesson=>[lesson.id,lesson.title]));
    const f3Launches=launches.filter(item=>!item.simulationRunId||!savedSimulationIds.has(item.simulationRunId)).map<TaskRow>(item=>({
      key:`F3L:${item.launchId}`,title:lessonTitles.get(item.lessonId)||"未命名教案",
      version:versionLabel(versionNumbers,item.versionId),kind:"课堂推演",createdAt:item.createdAt,status:item.state,
      to:{path:"/simulate",query:{lessonId:item.lessonId,versionId:item.versionId,launchId:item.launchId}}
    }));
    const internalF4Ids=new Set([
      ...launches.map(item=>item.f4SessionId),
      ...simulationDetails.map(item=>item.f4SessionId),
    ].filter((id):id is string=>Boolean(id)));
    const visibleF4=f4Result.filter(session=>!internalF4Ids.has(session.id));
    const f4=await Promise.all(visibleF4.map(async session=>{const binding=await axios.get<F4Binding>(`/api/platform/navigation/sessions/${encodeURIComponent(session.id)}/binding`).then(r=>r.data).catch(()=>null);return{key:`F4:${session.id}`,title:binding?.title||session.lesson_metadata?.topic||"未命名教案",version:binding?`V${binding.currentVersionNumber}`:"—",kind:"协同共析",createdAt:session.created_at||session.createdAt||session.updated_at||session.updatedAt,status:session.status,to:{path:"/platform/navigation",query:{session:session.id}}} as TaskRow;}));
    rows.value=[...f1,...f2,...f3,...f3Launches,...f4];
  }catch(reason){error.value=describe(reason)}finally{loading.value=false}
}
function formatTime(value?:string){if(!value||Number.isNaN(Date.parse(value)))return"—";return new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(value))}
function open(row:TaskRow){void router.push(row.to)}
onMounted(()=>{void load()});
</script>

<template><main class="task-page"><AppPageHeader title="任务记录" />
  <section class="filters v2-card"><label>功能<select v-model="kindFilter"><option value="ALL">全部功能</option><option>智能评价</option><option>教案生成</option><option>设计修改</option><option>课堂推演</option><option>协同共析</option></select></label><label>状态<select v-model="statusFilter"><option value="ALL">全部状态</option><option value="ACTIVE">进行中</option><option value="DONE">已完成</option><option value="FAILED">异常</option></select></label><label>时间顺序<select v-model="order"><option value="DESC">最新优先</option><option value="ASC">最早优先</option></select></label><button type="button" :disabled="loading" @click="load">{{ loading?"正在刷新……":"刷新" }}</button></section>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <section class="table-card v2-card"><div class="table-head"><span>教案</span><span>版本</span><span>任务</span><span>创建时间</span><span>状态</span></div><button v-for="row in filtered" :key="row.key" type="button" class="table-row" @click="open(row)"><strong>{{ row.title }}</strong><span>{{ row.version }}</span><span>{{ row.kind }}</span><span>{{ formatTime(row.createdAt) }}</span><i :class="`status-${statusGroup(row.status).toLowerCase()}`">{{ statusText[row.status]||row.status }}</i></button><p v-if="!loading&&!filtered.length" class="empty">没有符合条件的任务记录。</p><p v-if="loading&&!rows.length" class="empty">正在读取任务记录……</p></section>
</main></template>

<style scoped>
.task-page{display:grid;gap:20px}.filters{display:flex;align-items:end;gap:13px;padding:16px}.filters label{display:grid;gap:6px;color:var(--color-text-secondary);font-size:12px;font-weight:700}.filters select{min-width:150px;min-height:40px;padding:0 10px;border:1px solid var(--color-border);border-radius:var(--radius-sm);background:#fff}.filters button{min-height:40px;margin-left:auto;padding:0 16px;border:1px solid var(--color-primary-border);border-radius:var(--radius-md);color:var(--color-primary);background:#fff;cursor:pointer}.table-card{overflow:hidden}.table-head,.table-row{display:grid;grid-template-columns:minmax(220px,1.5fr) 80px 120px 170px 110px;align-items:center;gap:14px;padding:15px 20px}.table-head{color:var(--color-text-muted);background:var(--color-surface-soft);font-size:12px;font-weight:800}.table-row{width:100%;border:0;border-top:1px solid var(--color-border);color:var(--color-text);background:#fff;text-align:left;cursor:pointer}.table-row:hover{background:#f7f9fd}.table-row span{color:var(--color-text-secondary);font-size:13px}.table-row i{justify-self:start;padding:5px 9px;border-radius:999px;font-size:12px;font-style:normal;font-weight:700}.status-done{color:var(--color-primary);background:var(--color-primary-soft)}.status-active{color:var(--color-attention);background:var(--color-attention-soft)}.status-failed,.error{color:var(--color-danger)}.status-failed{background:var(--color-danger-soft)}.empty{padding:28px;text-align:center;color:var(--color-text-muted)}@media(max-width:850px){.filters{align-items:stretch;flex-direction:column}.filters select{width:100%}.filters button{margin:0}.table-card{overflow-x:auto}.table-head,.table-row{min-width:760px}}
</style>
