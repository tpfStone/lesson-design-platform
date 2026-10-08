<script setup lang="ts">
import { ref } from "vue";
import ChipInput from "./ChipInput.vue";
import type { LessonInput } from "../types/api";
const model = defineModel<LessonInput>({ required: true });
type PendingChipInput = { commitPending: () => void };
const curriculumInput = ref<PendingChipInput | null>(null);
const objectivesInput = ref<PendingChipInput | null>(null);
const resourcesInput = ref<PendingChipInput | null>(null);
function commitPending() {
  curriculumInput.value?.commitPending();
  objectivesInput.value?.commitPending();
  resourcesInput.value?.commitPending();
}
defineExpose({ commitPending });
withDefaults(
  defineProps<{
    compact?: boolean;
    idPrefix?: string;
    invalidField?:
      "subject" | "grade" | "topic" | "durationMinutes" | "classSize" | null;
  }>(),
  {
    compact: false,
    idPrefix: "lesson",
  },
);
const styles = [
  ["choose_the_best_fit_for_this_topic", "由系统为课题择优"],
  ["inquiry_through_cognitive_conflict", "认知冲突与探究"],
  ["authentic_problem_driven", "真实问题驱动"],
  ["dialogue_and_discussion", "对话与讨论"],
  ["project_or_task_based", "项目 / 任务学习"],
  ["close_reading_and_evidence", "细读与证据推理"],
];
</script>
<template>
  <div :id="`${idPrefix}-basic`" class="form-section">
    <div class="form-section-title">
      <span>01</span>
      <div>
        <h2>基本信息</h2>
        <p>先告诉系统这节课要解决什么。</p>
      </div>
    </div>
    <div class="field-grid three">
      <label
        ><span>科目 <b>*</b></span
        ><input
          :id="`${idPrefix}-subject`"
          v-model.trim="model.subject"
          :aria-invalid="invalidField === 'subject' ? true : undefined"
          :aria-describedby="
            invalidField === 'subject' ? `${idPrefix}-subject-error` : undefined
          "
          required
          maxlength="64"
          placeholder="如：高中化学"
        /><small
          v-if="invalidField === 'subject'"
          :id="`${idPrefix}-subject-error`"
          class="inline-field-error"
          >请输入科目。</small
        ></label
      >
      <label
        ><span>年级 <b>*</b></span
        ><input
          :id="`${idPrefix}-grade`"
          v-model.trim="model.grade"
          :aria-invalid="invalidField === 'grade' ? true : undefined"
          :aria-describedby="
            invalidField === 'grade' ? `${idPrefix}-grade-error` : undefined
          "
          required
          maxlength="64"
          placeholder="如：高二"
        /><small
          v-if="invalidField === 'grade'"
          :id="`${idPrefix}-grade-error`"
          class="inline-field-error"
          >请输入年级。</small
        ></label
      >
      <label
        ><span>课时</span>
        <div class="input-suffix">
          <input
            :id="`${idPrefix}-durationMinutes`"
            v-model.number="model.durationMinutes"
            type="number"
            min="5"
            max="240"
            step="1"
            :aria-invalid="
              invalidField === 'durationMinutes' ? true : undefined
            "
            :aria-describedby="
              invalidField === 'durationMinutes'
                ? `${idPrefix}-durationMinutes-error`
                : undefined
            "
          /><i>分钟</i>
        </div>
        <small
          v-if="invalidField === 'durationMinutes'"
          :id="`${idPrefix}-durationMinutes-error`"
          class="inline-field-error"
          >课时请输入 5–240 分钟的整数。</small
        ></label
      >
    </div>
    <label
      ><span>课题 <b>*</b></span
      ><input
        :id="`${idPrefix}-topic`"
        v-model.trim="model.topic"
        :aria-invalid="invalidField === 'topic' ? true : undefined"
        :aria-describedby="
          invalidField === 'topic' ? `${idPrefix}-topic-error` : undefined
        "
        required
        maxlength="255"
        placeholder="如：官能团与有机物性质的关系"
      /><small
        v-if="invalidField === 'topic'"
        :id="`${idPrefix}-topic-error`"
        class="inline-field-error"
        >请输入课题。</small
      ></label
    >
    <label
      ><span>课程信息</span
      ><textarea
        v-model="model.courseInformation"
        rows="2"
        placeholder="可补充单元位置、课型或本节课承接关系"
      />
    </label>
  </div>

  <div :id="`${idPrefix}-evidence`" class="form-section">
    <div class="form-section-title">
      <span>02</span>
      <div>
        <h2>教学依据</h2>
        <p>不填也能启动；真实依据有助于减少空泛内容，仍需教师核验。</p>
      </div>
    </div>
    <div class="field-grid two">
      <label
        ><span>教材版本</span
        ><input
          v-model="model.textbookVersion"
          placeholder="如：人教版选择性必修三"
      /></label>
      <label
        ><span>课程标准</span
        ><ChipInput
          ref="curriculumInput"
          v-model="model.curriculumStandards!"
          aria-label="课程标准"
          placeholder="逐条输入课标原文或要点"
      /></label>
    </div>
    <label
      ><span>教材内容摘要</span
      ><textarea
        v-model="model.textbookContent"
        rows="4"
        placeholder="粘贴本节教材核心内容、例题或概念边界；不要填写虚构课标编号"
      />
    </label>
  </div>

  <div :id="`${idPrefix}-learning`" class="form-section">
    <div class="form-section-title">
      <span>03</span>
      <div>
        <h2>学习设计</h2>
        <p>让 Agent 知道学生从哪里出发、最后用什么证据判断学会。</p>
      </div>
    </div>
    <label
      ><span>预设学习目标</span
      ><ChipInput
        ref="objectivesInput"
        v-model="model.learningObjectives!"
        aria-label="预设学习目标"
        placeholder="一个目标一条，按回车添加"
    /></label>
    <div class="field-grid two">
      <label
        ><span>学情描述</span
        ><textarea
          v-model="model.studentProfile"
          rows="4"
          placeholder="已有知识、常见误解、班级差异与学习习惯"
        />
      </label>
      <div class="field-stack">
        <label
          ><span>班级人数</span
          ><input
            :id="`${idPrefix}-classSize`"
            v-model.number="model.classSize"
            type="number"
            min="1"
            max="200"
            step="1"
            placeholder="可选"
            :aria-invalid="invalidField === 'classSize' ? true : undefined"
            :aria-describedby="
              invalidField === 'classSize'
                ? `${idPrefix}-classSize-error`
                : undefined
            "
          /><small
            v-if="invalidField === 'classSize'"
            :id="`${idPrefix}-classSize-error`"
            class="inline-field-error"
            >班级人数请输入 1–200 的整数，或留空。</small
          ></label
        >
        <label
          ><span>可用资源</span
          ><ChipInput
            ref="resourcesInput"
            v-model="model.availableResources!"
            aria-label="可用资源"
            placeholder="实验器材、设备、材料等"
        /></label>
      </div>
    </div>
  </div>

  <details
    :id="`${idPrefix}-advanced`"
    class="advanced-fields"
    :open="!compact"
  >
    <summary>
      <span>04</span>
      <div>
        <strong>风格与高级要求</strong
        ><small>控制教学设计取向，不会锁死具体内容</small>
      </div>
      <i>展开</i>
    </summary>
    <div class="advanced-body">
      <div class="field-grid two">
        <label
          ><span>教学设计取向</span
          ><select v-model="model.lessonStyle">
            <option v-for="item in styles" :key="item[0]" :value="item[0]">
              {{ item[1] }}
            </option>
          </select></label
        >
        <label
          ><span>详细程度</span
          ><select v-model="model.detailLevel">
            <option value="showcase">展示级：可直接试教</option>
            <option value="standard">标准级：完整但简洁</option>
          </select></label
        >
      </div>
      <label
        ><span>其他要求</span
        ><textarea
          v-model="model.additionalRequirements"
          rows="3"
          placeholder="如：加入可操作实验、避免依赖电子设备、强调学生作品等"
        />
      </label>
    </div>
  </details>
</template>
