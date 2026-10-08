import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import OptimizationPanel from "../src/components/OptimizationPanel.vue";
import type { OptimizationSummary } from "../src/types/api";

function summary(
  overrides: Partial<OptimizationSummary> = {},
): OptimizationSummary {
  return {
    outcome: "changed",
    message: "相对原稿有内容变化。",
    baseline_version_id: "v0",
    selected_version_id: "v2",
    content_changed: true,
    changed_section_count: 1,
    changed_sections: [
      {
        field: "procedure_steps",
        label: "教学过程",
        before: [],
        after: ["新活动"],
      },
    ],
    baseline_score: 7.7,
    selected_score: 7.7,
    score_delta: 0,
    score_notice: "同稿分差不算优化。",
    critique_count: 2,
    reviewed_issues: [],
    validation_batch_count: 1,
    rewrite_count: 2,
    rounds: [],
    stop_reason: "max_rounds",
    ...overrides,
  };
}

describe("OptimizationPanel", () => {
  it("does not claim pedagogical improvement from content edits or score drift", () => {
    const wrapper = mount(OptimizationPanel, { props: { summary: summary() } });
    expect(wrapper.text()).toContain("交付稿有内容变化·待复核");
    expect(wrapper.text()).toContain("尚无足够证据证明质量提升");
    expect(wrapper.text()).toContain("本次未进行双顺序比较");
  });

  it("presents an internal gate without claiming classroom effectiveness", () => {
    const wrapper = mount(OptimizationPanel, {
      props: {
        summary: summary({
          selected_score: 8.2,
          quality_gate: {
            passed: true,
            content_changed: true,
            score_gain: 0.5,
            dimension_drops: {},
            hard_rules_ok: true,
            no_high_risk: true,
            absolute_target_met: true,
            relative_target_met: true,
            thresholds: {
              overall: 8,
              minimum_dimension: 6,
              minimum_gain: 0.2,
              maximum_dimension_drop: 0.3,
            },
            note: "内部修订门槛",
          },
          pairwise_comparison: {
            baseline_version_id: "v0",
            candidate_version_id: "v2",
            verdict: "candidate_preferred",
            target_issue_progress: "improved",
            changed_sections: ["procedure_steps"],
            regression_flags: [],
            evidence: ["加入了可观察的学习活动"],
            failed_calls: 0,
            reason: "both orders agree",
          },
        }),
      },
    });
    expect(wrapper.text()).toContain("达到设定的内部修订门槛");
    expect(wrapper.text()).toContain("双顺序比较倾向修改稿");
    expect(wrapper.text()).toContain("仍需教师判断");
    expect(wrapper.text()).toContain("不是教学效果证明");
  });

  it("warns when the comparison favors the original", () => {
    const wrapper = mount(OptimizationPanel, {
      props: {
        summary: summary({
          pairwise_comparison: {
            baseline_version_id: "v0",
            candidate_version_id: "v2",
            verdict: "baseline_preferred",
            target_issue_progress: "worse",
            changed_sections: ["procedure_steps"],
            regression_flags: ["时间安排更紧张"],
            evidence: [],
            failed_calls: 0,
            reason: "both orders agree",
          },
        }),
      },
    });
    expect(wrapper.text()).toContain("双顺序比较更倾向原稿");
    expect(wrapper.text()).toContain("疑似退步：时间安排更紧张");
  });

  it("explains a skipped comparison instead of implying two comparisons ran", () => {
    const wrapper = mount(OptimizationPanel, {
      props: {
        summary: summary({
          pairwise_comparison: {
            baseline_version_id: "v0",
            candidate_version_id: "v2",
            verdict: "uncertain",
            target_issue_progress: "uncertain",
            changed_sections: ["procedure_steps"],
            regression_flags: [],
            evidence: [],
            votes: [],
            failed_calls: 0,
            reason:
              "Insufficient remaining token budget for a pairwise comparison.",
          },
        }),
      },
    });
    expect(wrapper.text()).toContain("0 / 2 次有效对照");
    expect(wrapper.text()).toContain("剩余预算不足");
    expect(wrapper.text()).not.toContain(
      "已交换原稿与修改稿展示顺序完成两次对照",
    );
  });
});
