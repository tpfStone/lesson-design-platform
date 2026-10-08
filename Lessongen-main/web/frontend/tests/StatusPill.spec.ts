import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StatusPill from "../src/components/StatusPill.vue";

describe("StatusPill", () => {
  it("exposes a text label in addition to colour", () => {
    const wrapper = mount(StatusPill, { props: { status: "NEEDS_HUMAN" } });
    expect(wrapper.text()).toContain("待教师复核");
    expect(wrapper.classes()).toContain("status-needs_human");
  });
});
