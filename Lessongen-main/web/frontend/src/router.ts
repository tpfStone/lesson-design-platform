import { createRouter, createWebHistory } from "vue-router";
import AppShell from "./layouts/AppShell.vue";
import PlatformDashboardView from "./views/PlatformDashboardView.vue";

export default createRouter({
  history: createWebHistory(),
  scrollBehavior: (_to, _from, saved) => saved || { top: 0 },
  routes: [
    {
      path: "/",
      component: AppShell,
      children: [
        { path: "", name: "platform-dashboard", component: PlatformDashboardView },
        { path: "lessons", name: "lesson-space", component: () => import("./views/LessonSpaceView.vue") },
        { path: "lessons/:lessonId", name: "lesson-detail", component: () => import("./views/LessonSpaceView.vue") },
        { path: "workflows", name: "workflows", component: () => import("./views/WorkflowView.vue") },
        { path: "tasks", name: "task-history", component: () => import("./views/TaskHistoryView.vue") },
        { path: "review", name: "review", component: () => import("./views/FeatureEntryView.vue"), props: { feature: "F1" } },
        { path: "review/batch", name: "review-batch", component: () => import("./views/BatchReviewView.vue") },
        { path: "lessons/:lessonId/annotate", name: "lesson-annotate", component: () => import("./views/AnnotationView.vue") },
        { path: "design", name: "design", component: () => import("./views/DesignEntryView.vue") },
        { path: "create/generate", name: "generate", component: () => import("./views/GenerateView.vue") },
        { path: "create/optimize", name: "optimize", component: () => import("./views/OptimizeView.vue") },
        { path: "optimize-lesson", name: "platform-optimize", component: () => import("./views/PlatformOptimizeView.vue") },
        { path: "jobs/:jobId", name: "job", component: () => import("./views/JobView.vue"), props: true },
        { path: "simulate", name: "simulate", component: () => import("./views/SimulationView.vue") },
        { path: "navigation", name: "navigation-entry", component: () => import("./views/NavigationEntryView.vue") },
        { path: "platform/navigation", name: "f4-navigation-workbench", component: () => import("./views/NavigationWorkbenchView.vue") },
        { path: "navigator", redirect: "/navigation" },
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});
