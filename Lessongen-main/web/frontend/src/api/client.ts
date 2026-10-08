import axios, { AxiosError } from "axios";
import type {
  Artifact,
  JobAccepted,
  JobDetail,
  JobEvent,
  JobMode,
  JobPage,
  JobStatus,
  LessonInput,
  LessonResult,
  OptimizeInput,
  ProblemDetail,
} from "../types/api";

const client = axios.create({ baseURL: "/api/v1", timeout: 20_000 });

export class ApiProblem extends Error {
  constructor(
    public readonly problem: ProblemDetail,
    public readonly httpStatus?: number,
  ) {
    super(problem.detail || "请求未能完成");
  }
}

client.interceptors.response.use(
  undefined,
  (error: AxiosError<ProblemDetail>) => {
    if (error.response?.data)
      throw new ApiProblem(error.response.data, error.response.status);
    throw new ApiProblem({
      code: "NETWORK_ERROR",
      detail: "无法连接服务，请检查后端是否启动",
    });
  },
);

export const makeIdempotencyKey = () => crypto.randomUUID();

function normalized<T extends LessonInput>(input: T): T {
  return {
    ...input,
    classSize:
      typeof input.classSize === "number" ? input.classSize : undefined,
  };
}

export async function createGenerate(input: LessonInput, key: string) {
  return (
    await client.post<JobAccepted>("/lesson-jobs/generate", normalized(input), {
      headers: { "Idempotency-Key": key },
    })
  ).data;
}

export async function createOptimize(
  input: OptimizeInput,
  document: File,
  key: string,
) {
  const data = new FormData();
  data.append(
    "request",
    new Blob([JSON.stringify(normalized(input))], { type: "application/json" }),
  );
  data.append("document", document, document.name);
  return (
    await client.post<JobAccepted>("/lesson-jobs/optimize", data, {
      headers: { "Idempotency-Key": key },
      timeout: 30_000,
    })
  ).data;
}

export async function listJobs(
  page = 0,
  size = 12,
  mode?: JobMode,
  status?: JobStatus,
) {
  return (
    await client.get<JobPage>("/lesson-jobs", {
      params: { page, size, mode, status },
    })
  ).data;
}
export async function getJob(id: string) {
  return (await client.get<JobDetail>(`/lesson-jobs/${id}`)).data;
}
export async function getResult(id: string) {
  return (await client.get<LessonResult>(`/lesson-jobs/${id}/result`)).data;
}
export async function getArtifacts(id: string) {
  return (await client.get<Artifact[]>(`/lesson-jobs/${id}/artifacts`)).data;
}

export function connectJobEvents(
  id: string,
  onEvent: (event: JobEvent) => void,
  onConnectionChange: (connected: boolean) => void,
) {
  const source = new EventSource(`/api/v1/lesson-jobs/${id}/events`);
  const consume = (raw: Event) => {
    const message = raw as MessageEvent<string>;
    try {
      onEvent(JSON.parse(message.data) as JobEvent);
    } catch {
      /* malformed events are ignored */
    }
  };
  source.addEventListener("job.snapshot", consume);
  source.addEventListener("job.progress", consume);
  source.addEventListener("job.terminal", consume);
  source.onopen = () => onConnectionChange(true);
  source.onerror = () => onConnectionChange(false);
  return () => source.close();
}
