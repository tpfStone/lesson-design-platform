export const navigationBase = "/api/platform/f4";

export class NavigationError extends Error {
  constructor(message: string, public status: number, public code?: string) {
    super(message);
  }
}

export async function request<T>(path: string, body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 190000);
  try {
    const response = await fetch(navigationBase + path, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Accept": "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const text = await response.text();
    let data: unknown;
    try { data = JSON.parse(text); }
    catch {
      throw new NavigationError(`HTTP ${response.status}：接口未返回 JSON，请检查 Java 后端和 F4 服务。`, response.status);
    }
    if (!response.ok) {
      const error = data as { detail?: unknown; code?: string };
      let detail = typeof error.detail === "string" ? error.detail : "服务暂时无法处理请求，请恢复最新状态。";
      if (Array.isArray(error.detail)) {
        detail = error.detail.map((item: { loc?: string[]; msg?: string }) => `${item.loc?.join(".") || "输入"}：${item.msg || "格式不正确"}`).join("；");
      }
      throw new NavigationError(`HTTP ${response.status}：${detail}`, response.status, error.code);
    }
    return data as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("请求等待超时，服务器可能仍在处理。请先恢复最新状态，确认结果后再重试。");
    }
    if (error instanceof TypeError) throw new Error("网页连接失败，请检查当前前端、Java 后端和 F4 服务。");
    throw error;
  } finally { window.clearTimeout(timer); }
}

export interface SessionSummary {
  id: string;
  status: "ACTIVE" | "ROUND_COMPLETED" | "TERMINATED" | "CREATED";
  current_section_id: string | null;
  lesson_metadata: { subject: string; grade: string; topic: string };
  config_snapshot: { provider: string; max_rounds: number; model?: string };
  updated_at: string;
}
export interface Suggestion {
  id: string; issue: string; reason: string; pedagogical_basis: string; revision: string;
  revision_mode: "append" | "replace"; target_text?: string; basis_type?: string;
  basis_sources?: { id: string; source: string; source_locator: string; content: string }[];
  decision: { id: string; decision: "ACCEPT" | "REJECT" } | null;
}
export interface Section {
  id: string; order_index: number; title: string; current_content: string;
  version: { id: string; version_number: number };
  review: { generated_at: string | null; completed_at: string | null };
  suggestions: Suggestion[];
}
export interface NavigationState {
  session: SessionSummary;
  round: { id: string; round_number: number };
  sections: Section[];
  lesson_plan: { current_content: string };
  lesson_plan_versions: { id: string; round_number: number; content: string }[];
  revision_candidate?: { suggestion_id: string; reason: string; candidate: string; expected_version_id: string };
}
