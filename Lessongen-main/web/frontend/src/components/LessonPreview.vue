<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ plan: Record<string, any> }>();
const metadata = computed(() => props.plan.metadata || {});
const duration = computed(() => {
  const value = metadata.value.duration_minutes;
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? `${value} 分钟`
    : "课时待确认";
});
const text = (value: unknown) => (typeof value === "string" ? value : "");
const list = (value: unknown) => (Array.isArray(value) ? value : []);
const minutes = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) && value > 0
    ? `${value} 分钟`
    : "时长待确认";
</script>
<template>
  <article class="lesson-paper">
    <header class="paper-header">
      <span
        >{{ metadata.subject || "学科" }} · {{ metadata.grade || "年级" }}</span
      >
      <h1>{{ metadata.topic || "教案" }}</h1>
      <p>
        {{ duration
        }}<span v-if="metadata.textbook_version">
          · {{ metadata.textbook_version }}</span
        >
      </p>
    </header>
    <section
      v-if="plan.design_thesis || plan.driving_question"
      class="design-lead"
    >
      <span class="section-number">01</span>
      <div>
        <h2>设计主张</h2>
        <p>{{ text(plan.design_thesis) }}</p>
        <blockquote v-if="plan.driving_question">
          核心问题：{{ plan.driving_question }}
        </blockquote>
      </div>
    </section>
    <section v-if="plan.content_analysis || plan.student_analysis">
      <span class="section-number">02</span>
      <div class="paper-grid">
        <div>
          <h2>内容分析</h2>
          <p>{{ text(plan.content_analysis) }}</p>
        </div>
        <div>
          <h2>学情分析</h2>
          <p>{{ text(plan.student_analysis) }}</p>
        </div>
      </div>
    </section>
    <section v-if="list(plan.learning_objectives).length">
      <span class="section-number">03</span>
      <div>
        <h2>学习目标与达成证据</h2>
        <ol class="objective-list">
          <li
            v-for="objective in list(plan.learning_objectives)"
            :key="objective.objective_id"
          >
            <strong>{{ objective.description }}</strong
            ><span v-if="objective.evidence_of_achievement">{{
              objective.evidence_of_achievement
            }}</span>
          </li>
        </ol>
      </div>
    </section>
    <section
      v-if="list(plan.key_points).length || list(plan.difficult_points).length"
    >
      <span class="section-number">04</span>
      <div class="paper-grid">
        <div>
          <h2>教学重点</h2>
          <ul>
            <li v-for="item in list(plan.key_points)" :key="item">
              {{ item }}
            </li>
          </ul>
        </div>
        <div>
          <h2>教学难点</h2>
          <ul>
            <li v-for="item in list(plan.difficult_points)" :key="item">
              {{ item }}
            </li>
          </ul>
        </div>
      </div>
    </section>
    <section v-if="list(plan.procedure_steps).length" class="procedure-section">
      <span class="section-number">05</span>
      <div>
        <h2>教学过程</h2>
        <div class="procedure-table" role="table" aria-label="教学过程">
          <div class="procedure-head" role="row">
            <strong role="columnheader">环节 / 时间</strong
            ><strong role="columnheader">教师活动与材料</strong
            ><strong role="columnheader">学生活动与证据</strong>
          </div>
          <div
            v-for="step in list(plan.procedure_steps)"
            :key="step.step_id"
            class="procedure-row"
            role="row"
          >
            <div role="cell">
              <strong>{{ step.stage }}</strong
              ><span>{{ minutes(step.duration_minutes) }}</span>
            </div>
            <div role="cell">
              <span class="cell-heading">教师活动与材料</span>
              <ul>
                <li v-for="item in list(step.teacher_actions)" :key="item">
                  {{ item }}
                </li>
              </ul>
              <p v-if="step.questions?.[0]">
                <b>关键问题：</b>{{ step.questions[0].question }}
              </p>
            </div>
            <div role="cell">
              <span class="cell-heading">学生活动与证据</span>
              <ul>
                <li v-for="item in list(step.student_actions)" :key="item">
                  {{ item }}
                </li>
              </ul>
              <p v-if="step.assessment">
                <b>观察证据：</b>{{ step.assessment }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
    <section v-if="plan.assessment_plan || plan.differentiation">
      <span class="section-number">06</span>
      <div class="paper-grid">
        <div>
          <h2>评价设计</h2>
          <p>{{ text(plan.assessment_plan) }}</p>
        </div>
        <div>
          <h2>差异化支持</h2>
          <p>{{ text(plan.differentiation) }}</p>
        </div>
      </div>
    </section>
    <section v-if="plan.homework || plan.board_design">
      <span class="section-number">07</span>
      <div class="paper-grid">
        <div>
          <h2>作业设计</h2>
          <p>{{ text(plan.homework) }}</p>
        </div>
        <div>
          <h2>板书设计</h2>
          <pre>{{ text(plan.board_design) }}</pre>
        </div>
      </div>
    </section>
  </article>
</template>
