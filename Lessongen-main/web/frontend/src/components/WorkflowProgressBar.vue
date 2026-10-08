<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { useWorkflowStore } from "../stores/workflow";
const workflow = useWorkflowStore();
const route = useRoute();
const run = computed(() => workflow.activeRun);
const plan = computed(() => workflow.activePlan);
const hidden = computed(() => route.path === "/" || route.path === "/workflows" || route.path === "/tasks" || route.path === "/lessons");
function state(index: number) {
  if (run.value?.completedIndexes.includes(index)) return "completed";
  if (!workflow.isFinished && run.value?.currentIndex === index) return "current";
  return "pending";
}
</script>

<template>
  <section v-if="run && plan && !hidden" class="workflow-guide" aria-label="当前工作流进度">
    <div class="guide-heading"><div><small>当前工作流</small><strong>{{ plan.name }}</strong><span>{{ run.lessonTitle ? `${run.lessonTitle} · V${run.versionNumber}` : '尚未确定教案' }}</span></div><RouterLink to="/workflows">查看工作流</RouterLink></div>
    <ol>
      <li v-for="(step,index) in plan.steps" :key="`${step.id}-${index}`" :class="state(index)">
        <RouterLink v-if="state(index) !== 'pending'" :to="workflow.stepDestination(step.id,index) || '/workflows'" :title="state(index)==='completed'?'查看之前的任务结果':`继续${step.name}`">
          <span class="step-dot">{{ state(index)==='completed'?'✓':index+1 }}</span><div><strong>{{ step.name }}</strong><small>{{ state(index)==='completed'?'已完成':'当前' }}</small></div>
        </RouterLink>
        <div v-else class="locked"><span class="step-dot">{{ index+1 }}</span><div><strong>{{ step.name }}</strong><small>未开始</small></div></div>
        <i v-if="index<plan.steps.length-1" aria-hidden="true"/>
      </li>
    </ol>
    <div v-if="!workflow.isFinished && workflow.currentDestination" class="guide-action"><RouterLink :to="workflow.currentDestination">{{ run.completedIndexes.length ? '继续当前步骤' : '开始第一步' }}</RouterLink></div>
    <p v-else-if="workflow.isFinished" class="workflow-finished">工作流已全部完成</p>
  </section>
</template>

<style scoped>
.workflow-guide{margin:0 0 28px;padding:17px 20px;border:1px solid var(--color-primary-border);border-radius:var(--radius-md);background:#fff}.guide-heading{display:flex;align-items:center;justify-content:space-between;gap:18px;padding-bottom:14px;border-bottom:1px solid #edf1f7}.guide-heading small,.guide-heading strong,.guide-heading span{display:inline}.guide-heading small{color:var(--color-primary);font-size:12px;font-weight:700}.guide-heading strong{margin-left:10px;color:var(--color-text)}.guide-heading span{margin-left:10px;color:var(--color-text-muted);font-size:12px}.guide-heading>a{color:var(--color-primary);font-size:12px;font-weight:700}.workflow-guide ol{display:flex;align-items:center;margin:16px 0 0;padding:0;list-style:none}.workflow-guide li{display:flex;align-items:center;min-width:0;flex:1}.workflow-guide li>a,.locked{display:flex;align-items:center;min-width:0;color:inherit}.step-dot{display:grid;place-items:center;flex:none;width:30px;height:30px;border:1px solid #cad5e5;border-radius:50%;color:var(--color-text-muted);background:#fff;font-size:12px;font-weight:800}.workflow-guide li div div{min-width:0;margin-left:9px}.workflow-guide li strong,.workflow-guide li small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.workflow-guide li strong{font-size:13px}.workflow-guide li small{margin-top:2px;color:var(--color-text-muted);font-size:10px}.workflow-guide li i{height:1px;min-width:18px;flex:1;margin:0 12px;background:#d8e0ec}.workflow-guide li.completed .step-dot{border-color:var(--color-primary);color:#fff;background:var(--color-primary)}.workflow-guide li.completed strong{color:var(--color-primary)}.workflow-guide li.current .step-dot{border:2px solid var(--color-primary);color:var(--color-primary);box-shadow:0 0 0 4px var(--color-primary-soft)}.workflow-guide li.current strong{color:var(--color-text)}.workflow-guide li.pending{color:#9aa7b8}.guide-action{display:flex;justify-content:flex-end;margin-top:15px}.guide-action a{padding:8px 13px;border-radius:var(--radius-sm);color:#fff;background:var(--color-primary);font-size:12px;font-weight:700}.workflow-finished{margin:14px 0 0;color:var(--color-primary);font-size:13px;font-weight:700}
@media(max-width:760px){.guide-heading{align-items:flex-start;flex-direction:column}.guide-heading small,.guide-heading strong,.guide-heading span{display:block;margin:3px 0}.workflow-guide ol{align-items:stretch;flex-direction:column;gap:11px}.workflow-guide li{width:100%}.workflow-guide li i{display:none}}
</style>
