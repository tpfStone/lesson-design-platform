<script setup lang="ts">
import { computed } from "vue";
import type { LessonInput } from "../types/api";
const props = withDefaults(
  defineProps<{ value: LessonInput; compact?: boolean }>(),
  { compact: false },
);
const items = computed(() => [
  {
    name: "课程标准",
    ok: !!props.value.curriculumStandards?.length,
    note: "帮助目标与评价有据可依",
  },
  {
    name: "教材内容",
    ok: !!props.value.textbookContent?.trim(),
    note: "减少学科边界和难度偏差",
  },
  {
    name: "学习目标",
    ok: !!props.value.learningObjectives?.length,
    note: "让活动与达成证据更清晰",
  },
  {
    name: "学生情况",
    ok: !!props.value.studentProfile?.trim(),
    note: "支持支架与差异化设计",
  },
]);
const count = computed(() => items.value.filter((item) => item.ok).length);
const missing = computed(() =>
  items.value
    .filter((item) => !item.ok)
    .map((item) => item.name)
    .join("、"),
);
const level = computed(() =>
  count.value >= 3 ? "证据较完整" : count.value >= 1 ? "基础证据" : "极简输入",
);
</script>
<template>
  <aside
    class="evidence-card"
    :class="{ 'is-compact': compact }"
    aria-label="输入证据完整度"
  >
    <div class="evidence-heading">
      <div>
        <span class="eyebrow">生成前检查</span>
        <h2>{{ level }}</h2>
      </div>
      <span class="evidence-count">{{ count }} / 4 类依据</span>
    </div>
    <div
      class="meter"
      role="meter"
      aria-label="已提供的推荐教学依据类别"
      aria-valuemin="0"
      aria-valuemax="4"
      :aria-valuenow="count"
    >
      <i :style="{ width: `${count * 25}%` }" />
    </div>
    <p v-if="compact">
      必填信息足以开始。{{
        missing ? `可选补充：${missing}。` : "四类推荐依据均已补充。"
      }}
    </p>
    <p v-else>必填信息足以开始。补充依据可让目标、活动和评价更贴近真实课堂。</p>
    <ul v-if="!compact">
      <li v-for="item in items" :key="item.name" :class="{ ready: item.ok }">
        <span aria-hidden="true">{{ item.ok ? "✓" : "○" }}</span>
        <div>
          <strong>{{ item.name }}</strong
          ><small>{{ item.note }}</small>
        </div>
      </li>
    </ul>
    <div class="cost-note">
      <strong>任务说明</strong
      ><span>提交后任务会在后台继续运行；离开页面不会中断，可从任务记录返回查看。</span>
    </div>
  </aside>
</template>
