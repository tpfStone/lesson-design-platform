import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ChipInput from "../src/components/ChipInput.vue";
import GenerateView from "../src/views/GenerateView.vue";
import OptimizeView from "../src/views/OptimizeView.vue";

const { createGenerate, createOptimize, routerPush } = vi.hoisted(() => ({
  createGenerate: vi.fn(),
  createOptimize: vi.fn(),
  routerPush: vi.fn(),
}));

vi.mock("vue-router", () => ({ useRouter: () => ({ push: routerPush }) }));
vi.mock("../src/api/client", () => ({
  ApiProblem: class extends Error {},
  createGenerate,
  createOptimize,
  makeIdempotencyKey: () => "test-key",
}));

let wrapper: VueWrapper | undefined;

beforeEach(() => {
  sessionStorage.clear();
  setActivePinia(createPinia());
  createGenerate.mockReset();
  createOptimize.mockReset();
  routerPush.mockReset();
  routerPush.mockResolvedValue(undefined);
  createGenerate.mockResolvedValue({ jobId: "job-1" });
  createOptimize.mockResolvedValue({ jobId: "job-1" });
  Element.prototype.scrollTo = vi.fn();
  vi.stubGlobal("crypto", {
    randomUUID: () => "test-key",
    subtle: { digest: async () => new Uint8Array(32).buffer },
  });
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.unstubAllGlobals();
});

async function fillBasics() {
  await wrapper!.get('input[id$="-subject"]').setValue("化学");
  await wrapper!.get('input[id$="-grade"]').setValue("高二");
  await wrapper!.get('input[id$="-topic"]').setValue("官能团");
}

describe("form interactions", () => {
  it("gives a chip field its own accessible name and commits typed text on blur", async () => {
    const chip = mount(ChipInput, {
      props: { modelValue: [], ariaLabel: "课程标准" },
    });
    const input = chip.get("input");
    expect(input.attributes("aria-label")).toBe("课程标准");
    expect(chip.get("button").attributes("aria-label")).toBe("添加课程标准");
    await input.setValue("依据真实课标设计活动");
    await input.trigger("blur");
    expect(chip.emitted("update:modelValue")?.at(-1)?.[0]).toEqual([
      "依据真实课标设计活动",
    ]);
    chip.unmount();
  });

  it("includes pending chip text in a generate submission", async () => {
    wrapper = mount(GenerateView, { attachTo: document.body });
    await fillBasics();
    await wrapper.get('input[aria-label="课程标准"]').setValue("真实课标要点");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(createGenerate).toHaveBeenCalledWith(
      expect.objectContaining({ curriculumStandards: ["真实课标要点"] }),
      "test-key",
    );
  });

  it("focuses and describes invalid duration and class size in generation", async () => {
    wrapper = mount(GenerateView, { attachTo: document.body });
    await fillBasics();
    await wrapper.get("#generate-durationMinutes").setValue("241");
    await wrapper.get("#generate-classSize").setValue("201");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(document.activeElement?.id).toBe("generate-durationMinutes");
    expect(
      wrapper.get("#generate-durationMinutes").attributes("aria-describedby"),
    ).toBe("generate-durationMinutes-error");
    expect(createGenerate).not.toHaveBeenCalled();

    await wrapper.get("#generate-durationMinutes").setValue("45");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(document.activeElement?.id).toBe("generate-classSize");
    expect(wrapper.get("#generate-classSize").attributes("aria-invalid")).toBe(
      "true",
    );
    expect(createGenerate).not.toHaveBeenCalled();
  });

  it("clears a missing-file error after selection and validates optimize numbers", async () => {
    wrapper = mount(OptimizeView, { attachTo: document.body });
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.get("#optimize-file").attributes("aria-invalid")).toBe(
      "true",
    );
    expect(wrapper.get("#optimize-file").attributes("aria-describedby")).toBe(
      "optimize-file-error",
    );

    const contents = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x00]);
    const file = {
      name: "lesson.docx",
      size: contents.length,
      slice: () => ({ arrayBuffer: async () => contents.slice(0, 4).buffer }),
      arrayBuffer: async () => contents.buffer,
    } as unknown as File;
    Object.defineProperty(wrapper.get("#optimize-file").element, "files", {
      configurable: true,
      value: [file],
    });
    await wrapper.get("#optimize-file").trigger("change");
    await flushPromises();
    expect(wrapper.find("#optimize-file-error").exists()).toBe(false);
    expect(
      wrapper.get("#optimize-file").attributes("aria-invalid"),
    ).toBeUndefined();

    await fillBasics();
    await wrapper.get("#optimize-durationMinutes").setValue("4");
    await wrapper.get("#optimize-classSize").setValue("201");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(document.activeElement?.id).toBe("optimize-durationMinutes");
    expect(createOptimize).not.toHaveBeenCalled();

    await wrapper.get("#optimize-durationMinutes").setValue("45");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(document.activeElement?.id).toBe("optimize-classSize");
    expect(
      wrapper.get("#optimize-classSize").attributes("aria-describedby"),
    ).toBe("optimize-classSize-error");
    expect(createOptimize).not.toHaveBeenCalled();

    await wrapper.get("#optimize-classSize").setValue("35");
    await wrapper.get('input[aria-label="优化重点"]').setValue("增强提问层次");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(createOptimize).toHaveBeenCalledWith(
      expect.objectContaining({ optimizationFocus: ["增强提问层次"] }),
      file,
      "test-key",
    );
  });
});
