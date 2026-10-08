import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import ScorePanel from "../src/components/ScorePanel.vue";
import {
  formatTeachingContent,
  lessonPathLabel,
} from "../src/utils/lessonPresentation";

describe("teacher-readable lesson evidence", () => {
  it("names JSON pointer sections without hiding the original path elsewhere", () => {
    expect(lessonPathLabel("/procedure_steps/0/teacher_actions")).toBe(
      "教学过程 · 第 1 环节 · 教师活动",
    );
    expect(lessonPathLabel("/learning_objectives/1")).toBe(
      "学习目标 · 第 2 项",
    );
    expect(lessonPathLabel("not-a-pointer")).toBe("教案整体");
  });

  it("formats structured teaching content without leading with machine IDs", () => {
    const value = [
      {
        step_id: "step-01",
        stage: "证据分类",
        teacher_actions: ["提供材料", "追问依据"],
      },
    ];
    expect(formatTeachingContent(value)).toContain("环节：证据分类");
    expect(formatTeachingContent(value)).toContain("教师活动：1. 提供材料");
    expect(formatTeachingContent(value)).not.toContain("step-01");
    expect(formatTeachingContent([])).toBe("（未填写）");
  });

  it("keeps an incomplete score payload unknown rather than drawing a false zero-score chart", () => {
    const wrapper = mount(ScorePanel, {
      props: {
        scores: null as unknown as Record<string, number>,
        overall: null,
      },
    });
    expect(wrapper.find(".overall-score").text()).toContain("暂不可用");
    expect(wrapper.findAll(".score-list dd")).toHaveLength(8);
    expect(
      wrapper
        .findAll(".score-list dd")
        .every((cell) => cell.text() === "暂不可用"),
    ).toBe(true);
    expect(wrapper.find(".radar-svg").exists()).toBe(false);
    wrapper.unmount();
  });
});
