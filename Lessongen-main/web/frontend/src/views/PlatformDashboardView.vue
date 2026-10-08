<script setup lang="ts">
import { RouterLink } from "vue-router";
const modules = [
  { title: "设计修改", description: "生成新教案，或结合评价问题优化已有版本。", icon: "/module-icons/design.png", to: "/design" },
  { title: "课堂推演", description: "用真实模型推演课堂过程，发现潜在教学问题。", icon: "/module-icons/simulation.png", to: "/simulate" },
  { title: "智能评价", description: "从多维标准分析教案，并生成可追溯的评价结果。", icon: "/module-icons/review.png", to: "/review" },
  { title: "协同共析", description: "逐节查看建议、判断取舍并保存新的教案版本。", icon: "/module-icons/analysis.png", to: "/navigation" },
];
</script>

<template>
  <main class="dashboard-v2">
    <section class="module-grid" aria-label="核心功能">
      <RouterLink v-for="module in modules" :key="module.title" :to="module.to" class="module-card v2-card">
        <img :src="module.icon" alt="" /><div><h2>{{ module.title }}</h2><p>{{ module.description }}</p></div><span>进入功能</span>
      </RouterLink>
    </section>
    <section class="workflow-choice-grid" aria-label="工作流入口">
      <RouterLink class="workflow-card v2-card" :to="{ path: '/workflows', query: { mode: 'recommended' } }">
        <div><small>推荐工作流</small><h2>使用系统预设的典型教案设计流程</h2><p>适合微格教学、教案研磨和教研评审等常用场景。</p></div>
        <span>查看推荐工作流</span>
      </RouterLink>
      <RouterLink class="workflow-card v2-card" :to="{ path: '/workflows', query: { mode: 'custom' } }">
        <div><small>自定义工作流</small><h2>自由组合智能体完成教学任务</h2><p>按自己的备课节奏选择四个智能体的执行顺序。</p></div>
        <span>创建自定义工作流</span>
      </RouterLink>
    </section>
  </main>
</template>

<style scoped>
.dashboard-v2{display:grid;gap:28px}.module-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.module-card{min-height:190px;display:flex;flex-direction:column;padding:22px;color:var(--color-text);transition:.18s ease}.module-card:hover,.workflow-card:hover{border-color:var(--color-primary-border);box-shadow:var(--shadow-card);transform:translateY(-2px)}.module-card img{width:54px;height:54px;object-fit:contain}.module-card h2{margin:15px 0 7px;font-size:20px}.module-card p{margin:0;color:var(--color-text-secondary);font-size:14px;line-height:1.65}.module-card>span{margin-top:auto;padding-top:16px;color:var(--color-primary);font-size:13px;font-weight:700}.workflow-choice-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.workflow-card{min-height:190px;display:flex;align-items:flex-start;justify-content:space-between;gap:22px;padding:27px;color:var(--color-text);transition:.18s ease}.workflow-card small{color:var(--color-primary);font-weight:800}.workflow-card h2{max-width:360px;margin:8px 0;font-size:21px}.workflow-card p{margin:0;color:var(--color-text-secondary);line-height:1.65}.workflow-card>span{align-self:flex-end;white-space:nowrap;padding:10px 14px;border-radius:var(--radius-md);color:#fff;background:var(--color-primary);font-size:13px;font-weight:750}@media(max-width:1080px){.module-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.workflow-card{flex-direction:column}.workflow-card>span{align-self:flex-start}}@media(max-width:720px){.module-grid,.workflow-choice-grid{grid-template-columns:1fr}.module-card{min-height:165px}}
</style>
