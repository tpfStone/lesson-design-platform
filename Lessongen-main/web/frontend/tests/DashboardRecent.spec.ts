import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { listJobs } from "../src/api/client";
import { useJobStore } from "../src/stores/jobs";
import DashboardView from "../src/views/DashboardView.vue";
import type { JobMode, JobPage, JobStatus, JobSummary } from "../src/types/api";

vi.mock("../src/api/client", () => ({ listJobs: vi.fn() }));

function job(
  jobId: string,
  mode: JobMode = "GENERATE",
  status: JobStatus = "COMPLETED",
): JobSummary {
  return {
    jobId,
    mode,
    status,
    subject: "化学",
    grade: "高二",
    topic: jobId,
    currentStage: "finalize",
    currentRound: 2,
    progressPercent: 100,
    createdAt: "2026-09-11T07:00:00Z",
  };
}

function page(items: JobSummary[], number: number, total: number): JobPage {
  return {
    items,
    page: number,
    size: 12,
    totalElements: total,
    totalPages: Math.ceil(total / 12),
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("dashboard recent jobs", () => {
  let pinia: ReturnType<typeof createPinia>;

  beforeEach(() => {
    pinia = createPinia();
    setActivePinia(pinia);
    vi.resetAllMocks();
  });

  it("loads backend pages and preserves the first page when loading more fails", async () => {
    vi.mocked(listJobs)
      .mockResolvedValueOnce(page([job("first")], 0, 13))
      .mockRejectedValueOnce(new Error("temporary failure"))
      .mockResolvedValueOnce(page([job("second")], 1, 13));
    const store = useJobStore();

    await store.loadRecent("GENERATE", "COMPLETED");
    expect(listJobs).toHaveBeenCalledWith(0, 12, "GENERATE", "COMPLETED");
    await expect(store.loadMoreRecent()).rejects.toThrow("temporary failure");
    expect(store.recent.map((item) => item.jobId)).toEqual(["first"]);
    expect(store.recentPage).toBe(0);

    await store.loadMoreRecent();
    expect(listJobs).toHaveBeenLastCalledWith(1, 12, "GENERATE", "COMPLETED");
    expect(store.recent.map((item) => item.jobId)).toEqual(["first", "second"]);
    expect(store.recentTotal).toBe(13);
  });

  it("clears old results on filter changes and ignores an older response", async () => {
    const oldRequest = deferred<JobPage>();
    vi.mocked(listJobs)
      .mockReturnValueOnce(oldRequest.promise)
      .mockResolvedValueOnce(page([job("optimized", "OPTIMIZE")], 0, 1));
    const store = useJobStore();

    const firstLoad = store.loadRecent("GENERATE");
    const secondLoad = store.loadRecent("OPTIMIZE");
    expect(store.recent).toEqual([]);
    expect(store.recentPage).toBe(-1);
    await secondLoad;
    oldRequest.resolve(page([job("stale")], 0, 1));
    await firstLoad;

    expect(store.recent.map((item) => item.jobId)).toEqual(["optimized"]);
    expect(store.recentMode).toBe("OPTIMIZE");
    expect(store.loading).toBe(false);
  });

  it("sends changed filters to the backend and shows the returned total", async () => {
    vi.mocked(listJobs)
      .mockResolvedValueOnce(page([job("first")], 0, 1))
      .mockResolvedValueOnce(page([], 0, 0));
    const wrapper = mount(DashboardView, {
      global: {
        plugins: [pinia],
        stubs: {
          RouterLink: { template: "<a><slot /></a>" },
        },
      },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("共 1 条任务");

    await wrapper.get('select[aria-label="按模式筛选"]').setValue("OPTIMIZE");
    await flushPromises();
    expect(listJobs).toHaveBeenLastCalledWith(0, 12, "OPTIMIZE", undefined);
    expect(wrapper.text()).toContain("共 0 条任务");
    expect(wrapper.text()).toContain("没有符合当前筛选条件的任务");
    wrapper.unmount();
  });

  it("keeps visible cards and offers a retry after a later page fails", async () => {
    vi.mocked(listJobs)
      .mockResolvedValueOnce(page([job("first")], 0, 13))
      .mockRejectedValueOnce(new Error("temporary failure"))
      .mockResolvedValueOnce(page([job("second")], 1, 13));
    const wrapper = mount(DashboardView, {
      global: {
        plugins: [pinia],
        stubs: { RouterLink: { template: "<a><slot /></a>" } },
      },
    });
    await flushPromises();

    await wrapper.get(".recent-section .hero-actions button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("first");
    expect(wrapper.text()).toContain("更多任务暂时无法读取");
    expect(wrapper.text()).toContain("重试加载更多");

    await wrapper.get(".recent-section .hero-actions button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("second");
    expect(wrapper.text()).toContain("共 13 条任务");
    wrapper.unmount();
  });

  it("does not invent progress when a non-terminal job has no valid percentage", async () => {
    vi.mocked(listJobs).mockResolvedValueOnce(
      page(
        [
          {
            ...job("pending", "GENERATE", "RUNNING"),
            progressPercent: NaN,
            createdAt: "invalid-date",
          },
        ],
        0,
        1,
      ),
    );
    const wrapper = mount(DashboardView, {
      global: {
        plugins: [pinia],
        stubs: { RouterLink: { template: "<a><slot /></a>" } },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("阶段进度暂不可用");
    expect(wrapper.text()).toContain("时间待确认");
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false);
    wrapper.unmount();
  });
});
