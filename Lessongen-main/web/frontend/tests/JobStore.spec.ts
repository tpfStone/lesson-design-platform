import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { getArtifacts, getResult } from "../src/api/client";
import { useJobStore } from "../src/stores/jobs";

vi.mock("../src/api/client", () => ({
  getArtifacts: vi.fn(),
  getResult: vi.fn(),
}));

describe("job terminal data recovery", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.resetAllMocks();
  });

  it("retries a transient result failure without treating the terminal data as loaded", async () => {
    vi.mocked(getArtifacts).mockResolvedValue([]);
    vi.mocked(getResult)
      .mockRejectedValueOnce(new Error("temporary 503"))
      .mockResolvedValueOnce({ jobId: "job-1" } as Awaited<
        ReturnType<typeof getResult>
      >);
    const store = useJobStore();

    expect(await store.loadTerminalData("job-1")).toBe(false);
    expect(store.result).toBeNull();
    expect(await store.loadTerminalData("job-1")).toBe(true);
    expect(store.result?.jobId).toBe("job-1");
  });

  it("accepts a failed run with recoverable artifacts and no displayable result", async () => {
    vi.mocked(getArtifacts).mockResolvedValue([]);
    vi.mocked(getResult).mockRejectedValue(
      Object.assign(new Error("no completed result"), { httpStatus: 404 }),
    );
    const store = useJobStore();

    expect(await store.loadTerminalData("failed-job", true)).toBe(true);
    expect(store.result).toBeNull();
  });

  it("keeps a completed lesson visible when only the artifact list returns 404", async () => {
    vi.mocked(getArtifacts).mockRejectedValue(
      Object.assign(new Error("missing artifact list"), { httpStatus: 404 }),
    );
    vi.mocked(getResult).mockResolvedValue({ jobId: "job-1" } as Awaited<
      ReturnType<typeof getResult>
    >);
    const store = useJobStore();

    expect(await store.loadTerminalData("job-1")).toBe(true);
    expect(store.result?.jobId).toBe("job-1");
    expect(store.artifacts).toEqual([]);
    expect(store.artifactWarning).toContain("下载文件列表暂不可用");
  });

  it("keeps the result visible when artifact retrieval fails and supports separate retry", async () => {
    vi.mocked(getArtifacts)
      .mockRejectedValueOnce(new Error("temporary 503"))
      .mockResolvedValueOnce([{ artifactId: "file-1" }] as Awaited<
        ReturnType<typeof getArtifacts>
      >);
    vi.mocked(getResult).mockResolvedValue({ jobId: "job-1" } as Awaited<
      ReturnType<typeof getResult>
    >);
    const store = useJobStore();

    expect(await store.loadTerminalData("job-1")).toBe(false);
    expect(store.result?.jobId).toBe("job-1");
    expect(store.artifactWarning).toContain("下载文件暂时无法读取");
    expect(await store.loadArtifacts("job-1")).toBe(true);
    expect(store.artifacts[0]?.artifactId).toBe("file-1");
    expect(store.artifactWarning).toBe("");
  });

  it("keeps previously loaded files while a result request fails", async () => {
    vi.mocked(getArtifacts).mockResolvedValue([
      { artifactId: "file-1" } as Awaited<ReturnType<typeof getArtifacts>>[0],
    ]);
    vi.mocked(getResult)
      .mockRejectedValueOnce(new Error("temporary 503"))
      .mockResolvedValueOnce({ jobId: "job-1" } as Awaited<
        ReturnType<typeof getResult>
      >);
    const store = useJobStore();

    expect(await store.loadTerminalData("job-1")).toBe(false);
    expect(store.artifacts[0]?.artifactId).toBe("file-1");
    expect(store.resultError).toContain("教案结果暂时无法读取");
    expect(await store.loadResult("job-1")).toBe(true);
    expect(store.resultError).toBe("");
    expect(store.artifacts[0]?.artifactId).toBe("file-1");
  });
});
