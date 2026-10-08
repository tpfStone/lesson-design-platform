<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import WorkflowProgressBar from "../components/WorkflowProgressBar.vue";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import { useWorkflowStore } from "../stores/workflow";

const route = useRoute();
const workflow = useWorkflowStore();
const menuOpen = ref(false);
const finishDialogOpen = ref(false);
const active = computed(() => route.path);
const links = [
  { label: "首页", path: "/", match: (path: string) => path === "/" },
  { label: "我的教案", path: "/lessons", match: (path: string) => path.startsWith("/lessons") && !path.endsWith("/annotate") },
  { label: "任务记录", path: "/tasks", match: (path: string) => path === "/tasks" || path.startsWith("/jobs/") },
];

const inActiveWorkflow = computed(() => {
  if (!workflow.activeRun || workflow.isFinished) return false;

  // All module pages entered from a workflow carry workflow=1.  Keeping this
  // check here prevents the global "unfinished workflow" banner from being
  // repeated while the user is already working inside that workflow.
  if (route.query.workflow === "1") return true;

  const destination = workflow.currentDestination;
  const destinationPath = typeof destination === "string"
    ? destination.split("?")[0]
    : destination?.path;
  if (destinationPath && route.path === destinationPath) return true;

  // Completed/current step review pages may be remembered as /jobs/... paths.
  if (route.path === "/workflows") return true;
  return false;
});

function finishWorkflow() {
  workflow.clearRun();
  finishDialogOpen.value = false;
}
</script>

<template>
  <div class="app-shell-v2">
    <header class="app-topbar">
      <div class="topbar-inner">
        <RouterLink to="/" class="app-brand" aria-label="备课搭子首页" @click="menuOpen = false">
          <span class="brand-mark" aria-hidden="true">备</span>
          <span><strong>备课搭子</strong><small>教案设计多智能体支持系统</small></span>
        </RouterLink>
        <button type="button" class="mobile-menu" :aria-expanded="menuOpen" aria-label="打开导航" @click="menuOpen = !menuOpen"><span/><span/><span/></button>
        <nav class="top-nav" :class="{ open: menuOpen }" aria-label="主导航">
          <RouterLink v-for="item in links" :key="item.path" :to="item.path" :class="{ active: item.match(active) }" :aria-current="item.match(active) ? 'page' : undefined" @click="menuOpen = false">{{ item.label }}</RouterLink>
        </nav>
      </div>
    </header>

    <div v-if="workflow.activeRun && !workflow.isFinished && !inActiveWorkflow" class="resume-strip">
      <div class="resume-copy">
        <span>你有一个未完成的工作流</span>
        <strong>{{ workflow.activeRun.lessonTitle || '尚未确定教案' }} · {{ workflow.currentStep?.name }}</strong>
      </div>
      <div class="resume-actions">
        <button type="button" class="resume-end" @click="finishDialogOpen = true">结束工作流</button>
        <RouterLink v-if="workflow.currentDestination" :to="workflow.currentDestination">继续执行</RouterLink>
      </div>
    </div>

    <main id="main-content" class="app-main" tabindex="-1">
      <WorkflowProgressBar />
      <RouterView />
    </main>
    <footer class="app-footer-v2"><span>备课搭子 · 教案设计多智能体支持系统</span><span>AI生成内容请由教师复核后使用</span></footer>

    <ConfirmDialog
      :open="finishDialogOpen"
      title="结束当前工作流？"
      description="结束后不再推进后续步骤。已经启动的单个任务不会被强制取消，仍可在任务记录中查看；已保存的教案和版本不会被删除。"
      confirm-text="结束工作流"
      @cancel="finishDialogOpen = false"
      @confirm="finishWorkflow"
    />
  </div>
</template>

<style scoped>
.app-shell-v2{min-height:100vh;background:var(--color-bg)}.app-topbar{position:sticky;top:0;z-index:90;height:var(--header-height);border-bottom:1px solid var(--color-border);background:rgba(255,255,255,.96);backdrop-filter:blur(12px)}.topbar-inner{width:min(var(--page-width),calc(100% - 40px));height:100%;display:flex;align-items:center;justify-content:space-between;margin:auto}.app-brand{display:flex;align-items:center;gap:12px;color:var(--color-text)}.brand-mark{display:grid;place-items:center;width:42px;height:42px;border-radius:8px;color:#fff;background:var(--color-primary);font-size:18px;font-weight:800}.app-brand strong,.app-brand small{display:block}.app-brand strong{font-size:20px;line-height:1.05}.app-brand small{margin-top:4px;color:var(--color-text-muted);font-size:12px}.top-nav{display:flex;align-items:center;gap:4px}.top-nav a{display:inline-flex;align-items:center;min-height:40px;padding:0 15px;border-radius:var(--radius-md);color:var(--color-text-secondary);font-size:14px;font-weight:650}.top-nav a:hover,.top-nav a.active{color:var(--color-primary);background:var(--color-primary-soft)}.mobile-menu{display:none;width:40px;height:40px;border:0;border-radius:var(--radius-md);background:var(--color-surface-soft)}.mobile-menu span{display:block;width:18px;height:2px;margin:4px auto;background:var(--color-text)}
.resume-strip{width:min(var(--page-width),calc(100% - 40px));display:flex;align-items:center;justify-content:space-between;gap:18px;margin:14px auto 0;padding:10px 14px;border:1px solid #ead49e;border-radius:var(--radius-md);background:var(--color-attention-soft)}.resume-copy{display:flex;align-items:center;min-width:0;gap:12px;white-space:nowrap}.resume-copy span{color:var(--color-attention);font-size:12px}.resume-copy strong{min-width:0;overflow:hidden;text-overflow:ellipsis;color:var(--color-text);font-size:13px}.resume-actions{display:flex;align-items:center;flex:none;gap:10px}.resume-actions a,.resume-end{min-height:36px;display:inline-flex;align-items:center;justify-content:center;padding:0 13px;border-radius:var(--radius-sm);font-size:12px;font-weight:700;white-space:nowrap}.resume-actions a{color:#fff;background:var(--color-primary)}.resume-end{border:1px solid #dfc27b;color:var(--color-attention);background:#fff;cursor:pointer}.resume-end:hover{background:#fffaf0}
.app-main{width:min(var(--page-width),calc(100% - 40px));min-height:calc(100vh - 132px);margin:0 auto;padding:34px 0 72px}.app-footer-v2{display:flex;justify-content:space-between;gap:20px;padding:20px max(20px,calc((100vw - var(--page-width))/2));border-top:1px solid var(--color-border);color:var(--color-text-muted);background:#fff;font-size:12px}
@media(max-width:700px){.mobile-menu{display:block}.top-nav{position:absolute;left:20px;right:20px;top:60px;display:none;align-items:stretch;flex-direction:column;padding:8px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff;box-shadow:var(--shadow-subtle)}.top-nav.open{display:flex}.top-nav a{width:100%}.resume-strip{align-items:stretch;flex-direction:column}.resume-copy{align-items:flex-start;flex-direction:column;gap:3px;white-space:normal}.resume-actions{justify-content:flex-end}.app-main{width:calc(100% - 28px);padding-top:24px}.app-footer-v2{flex-direction:column}}
</style>
