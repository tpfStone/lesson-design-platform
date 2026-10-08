import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EvidenceMeter from "../src/components/EvidenceMeter.vue";

describe("EvidenceMeter", () => {
  it("treats minimal input as allowed and explains missing evidence", () => {
    const wrapper = mount(EvidenceMeter, {
      props: {
        value: {
          subject: "化学",
          grade: "高二",
          topic: "官能团",
          durationMinutes: 45,
          curriculumStandards: [],
          learningObjectives: [],
          textbookContent: "",
          studentProfile: "",
        },
      },
    });
    expect(wrapper.text()).toContain("极简输入");
    expect(wrapper.text()).toContain("必填信息足以开始");
  });
});
