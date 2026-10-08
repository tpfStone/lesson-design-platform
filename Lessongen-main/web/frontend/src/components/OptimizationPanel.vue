<script setup lang="ts">
import { computed } from "vue";
import type { OptimizationSummary } from "../types/api";
import { formatTeachingContent, lessonPathLabel } from "../utils/lessonPresentation";

const props = defineProps<{ summary: OptimizationSummary }>();

const changedSections = computed(() => props.summary.changed_sections || []);
const reviewedIssues = computed(() => props.summary.reviewed_issues || []);
const alternateSections = computed(() => props.summary.unselected_candidate_changed_sections || []);
const gate = computed(() => props.summary.quality_gate);
const comparison = computed(() => props.summary.pairwise_comparison);

const outcomeText = computed(() => {
  if (props.summary.stop_reason === "rewrite_failed") return "本次未形成可采用的修改稿";
  if (props.summary.content_changed) return "交付稿有内容变化·待复核";
  return "本次保留原稿";
});

const gateLabel = computed(() => {
  if (!gate.value) return "本次未保存内部修订门槛判定";
  return gate.value.passed ? "达到设定的内部修订门槛" : "未达到设定的内部修订门槛";
});

const comparisonLabel = computed(() => {
  switch (comparison.value?.verdict) {
    case "candidate_preferred": return "双顺序比较倾向修改稿";
    case "baseline_preferred": return "双顺序比较更倾向原稿";
    case "uncertain": return "双顺序比较尚无一致结论";
    default: return "本次未进行双顺序比较";
  }
});

const comparisonReason = computed(() => {
  const reason = comparison.value?.reason?.trim();
  if (!reason) return "当前结果未保存对照原因，不能据此判断修改稿优于原稿。";
  if (/budget|token|cost|预算|额度/i.test(reason)) return "本次运行剩余预算不足，未完成双顺序比较；建议教师直接复核修改稿。";
  if (/identity|duration changed|身份|课时变化/i.test(reason)) return "原稿与修改稿的课程身份或课时不一致，不能直接比较。";
  if (/deterministic.*rules|hard.rules|结构规则/i.test(reason)) return "修改稿未通过确定性结构规则检查，不能自动判断为更优。";
  if (/no canonical|no content|unchanged|没有.*内容变化/i.test(reason)) return "原稿与修改稿没有可比较的正文变化，不能据此判断质量提升。";
  if (/input|payload|character|too large|输入过大/i.test(reason)) return "比较内容超过单次对照上限，建议教师直接对照原稿与修改稿。";
  if (/failed|failure|error|失败/i.test(reason)) return "对照检查未全部完成，无法自动判断哪份教案更好。";
  if (/both.*required|两次.*必须/i.test(reason)) return "只有完成两个展示顺序的对照，才能形成较稳妥的内部倾向。";
  if (/disagree|inconclusive|uncertain|不一致|无法判断/i.test(reason)) return "交换展示顺序后的判断不一致或证据不足，需要教师复核。";
  if (/favor.*baseline|baseline.preferred|倾向原稿/i.test(reason)) return "两种展示顺序下均更倾向原稿，请检查修改稿是否引入退步。";
  if (/favor.*candidate|candidate.preferred|倾向修改稿/i.test(reason)) return "两种展示顺序下均倾向修改稿，但仍不代表课堂效果已经得到验证。";
  return reason;
});

const reviewConclusion = computed(() => {
  if (!props.summary.content_changed) return "本次没有形成新的正文版本，任务结果仍会保留供教师查看。";
  if (gate.value?.passed && comparison.value?.verdict === "candidate_preferred") return "修改稿通过内部修订门槛，双顺序比较也倾向修改稿；是否用于课堂仍需教师判断。";
  if (comparison.value?.verdict === "baseline_preferred") return "虽有修改，但双顺序比较更倾向原稿；建议教师重点复核后再决定是否采用。";
  if (gate.value && !gate.value.passed) return "修改稿有真实内容变化，但尚未达到设定的内部修订门槛；建议教师重点复核。";
  return "修改稿有真实内容变化，但尚无足够证据证明质量提升；请教师复核。";
});

function progressLabel(progress?: string) {
  switch (progress) {
    case "improved": return "倾向有进展";
    case "unchanged": return "未发现明显进展";
    case "worse": return "疑似退步";
    default: return "未能判定";
  }
}

function treatmentLabel(item: OptimizationSummary["reviewed_issues"][number]) {
  const value = `${item.status || ""} ${item.decision || ""}`.toLowerCase();
  if (/unresolved|reject|blocked|failed|open|pending/.test(value)) return "仍需关注";
  if (/implement|accept|approve|applied|resolved|complete/.test(value)) return "已针对";
  return "已调整";
}

function treatmentClass(item: OptimizationSummary["reviewed_issues"][number]) {
  return treatmentLabel(item) === "仍需关注" ? "attention" : "handled";
}

function cleanText(value?: string | null) {
  const text = (value || "").trim();
  return text || "暂无补充说明";
}
</script>

<template>
  <section class="optimization-panel v2-card" aria-label="设计修改结果摘要">
    <header class="panel-heading">
      <div>
        <p class="section-kicker">修改摘要</p>
        <h2>这份教案具体改了什么</h2>
        <p>这里只展示本次修改的重点变化，完整修改稿可在下方预览或结果文件中查看。</p>
      </div>
      <span class="outcome-pill">{{ outcomeText }}</span>
    </header>

    <p class="review-conclusion">{{ reviewConclusion }}</p>

    <details class="quality-drawer">
      <summary>查看内部质量依据</summary>
      <div class="quality-grid">
        <div class="quality-item">
          <strong>{{ gateLabel }}</strong>
          <p v-if="gate">
            八维总评 {{ gate.absolute_target_met ? "达标" : "未达标" }}；相对原稿提升与维度退步约束
            {{ gate.relative_target_met ? "达标" : "未达标" }}；结构规则 {{ gate.hard_rules_ok ? "通过" : "未通过" }}。
          </p>
          <p v-else>当前任务没有保存完整的内部门槛信息，不据此宣称质量已经提升。</p>
        </div>
        <div class="quality-item">
          <strong>{{ comparisonLabel }}</strong>
          <p v-if="comparison?.votes?.length === 2 && !comparison.failed_calls">
            已交换原稿与修改稿展示顺序完成两次对照；聚焦内容进展：{{ progressLabel(comparison.target_issue_progress) }}。
          </p>
          <p v-else-if="comparison">本次只完成 {{ comparison.votes?.length ?? 0 }} / 2 次有效对照，未形成可靠的双顺序判断。</p>
          <p v-else>当前结果未包含对照记录；不能据此判断修改稿优于原稿。</p>
          <p v-if="comparison">对照说明：{{ comparisonReason }}</p>
          <p v-if="comparison?.regression_flags.length">疑似退步：{{ comparison.regression_flags.join("；") }}</p>
          <p v-if="comparison?.evidence.length">对照依据：{{ comparison.evidence.slice(0, 2).join("；") }}</p>
        </div>
      </div>
      <p class="scope-note">内部评分和模型对照只用于筛选修改稿，不是教学效果证明；最终是否采用仍需教师判断。</p>
    </details>

    <div v-if="changedSections.length" class="change-list">
      <article v-for="(section, index) in changedSections" :key="section.field" class="change-card">
        <div class="change-title">
          <span>{{ String(index + 1).padStart(2, '0') }}</span>
          <div>
            <h3>{{ section.label || lessonPathLabel(section.field) }}</h3>
            <small>已修改</small>
          </div>
        </div>
        <div class="diff-grid">
          <div>
            <b>修改前</b>
            <pre>{{ formatTeachingContent(section.before) }}</pre>
          </div>
          <div>
            <b>修改后</b>
            <pre>{{ formatTeachingContent(section.after) }}</pre>
          </div>
        </div>
      </article>
    </div>
    <div v-else class="empty-change">
      <strong>没有检测到正文变化</strong>
      <p>本次任务结果仍会保留在任务记录中，但不会因为没有正文变化而创建新的教案版本。</p>
    </div>

    <section v-if="reviewedIssues.length" class="issue-section">
      <header>
        <p class="section-kicker">优化关注项处理情况</p>
        <h3>本次重点处理了哪些问题</h3>
      </header>
      <div class="issue-list">
        <article v-for="item in reviewedIssues" :key="item.critique_id" class="issue-row">
          <span class="issue-state" :class="treatmentClass(item)">{{ treatmentLabel(item) }}</span>
          <div>
            <strong>{{ cleanText(item.issue) }}</strong>
            <p v-if="item.suggestion">{{ cleanText(item.suggestion) }}</p>
            <small>{{ lessonPathLabel(item.target_path) }}</small>
          </div>
        </article>
      </div>
      <p class="scope-note">“已针对 / 已调整”表示本次修改已对此作出处理，不等同于课堂效果已经得到验证。</p>
    </section>

    <details v-if="alternateSections.length" class="alternate-drawer">
      <summary>可参考的其他修改方案</summary>
      <p class="drawer-note">以下内容来自优化过程中未被选为最终稿的中间方案，仅供教师对照参考。</p>
      <article v-for="section in alternateSections" :key="section.field" class="alternate-item">
        <h4>{{ section.label || lessonPathLabel(section.field) }}</h4>
        <div class="diff-grid compact">
          <div><b>原内容</b><pre>{{ formatTeachingContent(section.before) }}</pre></div>
          <div><b>参考方案</b><pre>{{ formatTeachingContent(section.after) }}</pre></div>
        </div>
      </article>
    </details>
  </section>
</template>

<style scoped>
.optimization-panel{padding:24px;color:var(--color-text)}
.panel-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding-bottom:20px;border-bottom:1px solid var(--color-border)}
.section-kicker{margin:0;color:var(--color-primary);font-size:12px;font-weight:800}
.panel-heading h2{margin:6px 0 8px;font-size:22px}.panel-heading p:last-child{max-width:720px;margin:0;color:var(--color-text-secondary);font-size:13px;line-height:1.7}
.outcome-pill{flex:none;min-height:30px;display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;color:var(--color-primary);background:var(--color-primary-soft);font-size:12px;font-weight:800}
.review-conclusion{margin:18px 0 0;padding:13px 15px;border-radius:var(--radius-md);color:var(--color-text-secondary);background:var(--color-surface-soft);font-size:13px;line-height:1.7}
.quality-drawer{margin-top:14px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff}.quality-drawer>summary{padding:13px 15px;color:var(--color-primary);font-weight:800;cursor:pointer}.quality-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:0 15px 14px}.quality-item{padding:14px;border-radius:var(--radius-md);background:var(--color-surface-soft)}.quality-item strong{display:block;margin-bottom:7px}.quality-item p{margin:5px 0 0;color:var(--color-text-secondary);font-size:12px;line-height:1.7}.quality-drawer>.scope-note{margin:0 15px 15px}
.change-list{display:grid;gap:14px;margin-top:20px}.change-card{padding:18px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff}.change-title{display:flex;align-items:center;gap:12px;margin-bottom:14px}.change-title>span{width:34px;height:34px;display:grid;place-items:center;flex:none;border-radius:var(--radius-md);color:#fff;background:var(--color-primary);font-size:12px;font-weight:800}.change-title h3{margin:0;font-size:17px}.change-title small{display:block;margin-top:3px;color:var(--color-primary);font-size:12px;font-weight:700}
.diff-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.diff-grid>div{min-width:0;padding:13px;border-radius:var(--radius-md);background:var(--color-surface-soft)}.diff-grid>div:last-child{background:var(--color-primary-soft)}.diff-grid b{display:block;margin-bottom:8px;color:var(--color-text-secondary);font-size:12px}.diff-grid pre{max-height:300px;overflow:auto;margin:0;color:var(--color-text);background:transparent;font:inherit;font-size:13px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere}
.empty-change{margin-top:20px;padding:18px;border-radius:var(--radius-md);background:var(--color-surface-soft)}.empty-change p{margin:6px 0 0;color:var(--color-text-secondary);font-size:13px;line-height:1.7}
.issue-section{margin-top:24px;padding-top:22px;border-top:1px solid var(--color-border)}.issue-section h3{margin:6px 0 14px;font-size:19px}.issue-list{display:grid;gap:10px}.issue-row{display:grid;grid-template-columns:auto minmax(0,1fr);gap:12px;align-items:start;padding:14px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff}.issue-state{min-width:64px;padding:5px 8px;border-radius:999px;text-align:center;font-size:11px;font-weight:800}.issue-state.handled{color:var(--color-primary);background:var(--color-primary-soft)}.issue-state.attention{color:var(--color-attention);background:var(--color-attention-soft)}.issue-row strong{display:block;line-height:1.55}.issue-row p{margin:6px 0;color:var(--color-text-secondary);font-size:13px;line-height:1.7}.issue-row small{color:var(--color-text-muted)}.scope-note{margin:12px 0 0;color:var(--color-text-muted);font-size:12px;line-height:1.65}
.alternate-drawer{margin-top:20px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:#fff}.alternate-drawer>summary{padding:14px 16px;color:var(--color-primary);font-weight:800;cursor:pointer}.drawer-note{margin:0;padding:0 16px 14px;color:var(--color-text-secondary);font-size:13px;line-height:1.7}.alternate-item{margin:0 16px 14px;padding-top:14px;border-top:1px solid var(--color-border)}.alternate-item h4{margin:0 0 10px}.compact pre{max-height:220px}
@media(max-width:760px){.panel-heading{flex-direction:column}.diff-grid,.quality-grid{grid-template-columns:1fr}.outcome-pill{align-self:flex-start}.issue-row{grid-template-columns:1fr}.issue-state{justify-self:start}}
</style>
