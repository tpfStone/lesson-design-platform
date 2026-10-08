import { defineStore } from "pinia";
import { getArtifacts, getJob, getResult, listJobs } from "../api/client";
import type {
  Artifact,
  JobDetail,
  JobMode,
  JobStatus,
  JobSummary,
  LessonResult,
} from "../types/api";

const recentPageSize = 12;

export const useJobStore = defineStore("jobs", {
  state: () => ({
    recent: [] as JobSummary[],
    recentPage: -1,
    recentTotal: 0,
    recentTotalPages: 0,
    recentMode: undefined as JobMode | undefined,
    recentStatus: undefined as JobStatus | undefined,
    recentRequestId: 0,
    current: null as JobDetail | null,
    result: null as LessonResult | null,
    artifacts: [] as Artifact[],
    artifactWarning: "",
    resultError: "",
    resultLoading: false,
    resultReady: false,
    artifactLoading: false,
    artifactsReady: false,
    terminalEpoch: 0,
    loading: false,
  }),
  actions: {
    async loadRecent(mode?: JobMode, status?: JobStatus) {
      const filtersChanged =
        this.recentMode !== mode || this.recentStatus !== status;
      const requestId = ++this.recentRequestId;
      this.recentMode = mode;
      this.recentStatus = status;
      if (filtersChanged) {
        this.recent = [];
        this.recentPage = -1;
        this.recentTotal = 0;
        this.recentTotalPages = 0;
      }
      this.loading = true;
      try {
        const page = await listJobs(0, recentPageSize, mode, status);
        if (requestId !== this.recentRequestId) return;
        this.recent = page.items;
        this.recentPage = page.page;
        this.recentTotal = page.totalElements;
        this.recentTotalPages = page.totalPages;
      } catch (error) {
        if (requestId === this.recentRequestId) throw error;
      } finally {
        if (requestId === this.recentRequestId) this.loading = false;
      }
    },
    async loadMoreRecent() {
      const nextPage = this.recentPage + 1;
      if (
        this.loading ||
        this.recentPage < 0 ||
        nextPage >= this.recentTotalPages
      )
        return;
      const requestId = ++this.recentRequestId;
      this.loading = true;
      try {
        const page = await listJobs(
          nextPage,
          recentPageSize,
          this.recentMode,
          this.recentStatus,
        );
        if (requestId !== this.recentRequestId) return;
        const existingIds = new Set(this.recent.map((job) => job.jobId));
        this.recent.push(
          ...page.items.filter((job) => {
            if (existingIds.has(job.jobId)) return false;
            existingIds.add(job.jobId);
            return true;
          }),
        );
        this.recentPage = page.page;
        this.recentTotal = page.totalElements;
        this.recentTotalPages = page.totalPages;
      } catch (error) {
        if (requestId === this.recentRequestId) throw error;
      } finally {
        if (requestId === this.recentRequestId) this.loading = false;
      }
    },
    async loadJob(id: string) {
      this.current = await getJob(id);
      return this.current;
    },
    async loadArtifacts(id: string) {
      const epoch = this.terminalEpoch;
      this.artifactLoading = true;
      try {
        const artifacts = await getArtifacts(id);
        if (epoch !== this.terminalEpoch) return false;
        this.artifacts = artifacts;
        this.artifactsReady = true;
        this.artifactWarning = "";
      } catch (reason) {
        if (epoch !== this.terminalEpoch) return false;
        const notFound =
          reason instanceof Error &&
          "httpStatus" in reason &&
          reason.httpStatus === 404;
        if (notFound) this.artifactsReady = true;
        this.artifactWarning = notFound
          ? "下载文件列表暂不可用；教案内容仍可查看。"
          : "下载文件暂时无法读取；已显示的教案内容不受影响。";
      } finally {
        if (epoch === this.terminalEpoch) this.artifactLoading = false;
      }
      return this.artifactsReady;
    },
    async loadResult(id: string, allowMissingResult = false) {
      const epoch = this.terminalEpoch;
      this.resultLoading = true;
      try {
        const result = await getResult(id);
        if (epoch !== this.terminalEpoch) return false;
        this.result = result;
        this.resultReady = true;
        this.resultError = "";
      } catch (reason) {
        if (epoch !== this.terminalEpoch) return false;
        const response = reason as {
          httpStatus?: number;
          problem?: { code?: string };
        };
        const expectedMissing =
          allowMissingResult &&
          reason instanceof Error &&
          (response.httpStatus === 404 ||
            (response.httpStatus === 409 &&
              response.problem?.code === "RESULT_NOT_READY"));
        if (expectedMissing) {
          this.result = null;
          this.resultReady = true;
          this.resultError = "";
        } else {
          this.resultError =
            "教案结果暂时无法读取，请重试；已取得的下载文件仍可使用。";
        }
      } finally {
        if (epoch === this.terminalEpoch) this.resultLoading = false;
      }
      return this.resultReady;
    },
    async loadTerminalData(id: string, allowMissingResult = false) {
      await Promise.all([
        this.artifactsReady ? Promise.resolve(true) : this.loadArtifacts(id),
        this.resultReady
          ? Promise.resolve(true)
          : this.loadResult(id, allowMissingResult),
      ]);
      return this.artifactsReady && this.resultReady;
    },
    resetCurrent() {
      this.terminalEpoch += 1;
      this.current = null;
      this.result = null;
      this.artifacts = [];
      this.artifactWarning = "";
      this.resultError = "";
      this.resultLoading = false;
      this.resultReady = false;
      this.artifactLoading = false;
      this.artifactsReady = false;
    },
  },
});
