export interface BindingContext {
  lessonId: string | null; title: string | null; sourceVersionId: string | null;
  sourceVersionNumber: number | null; currentVersionId: string | null;
  currentVersionNumber: number | null; currentContent: string | null;
}
export interface WritebackResult {
  lessonId: string; versionId: string; versionNumber: number; alreadySaved: boolean;
  roundNumber: number; nativeStatus: string;
}

export async function bridgeRequest<T>(path: string, body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 190000);
  try {
    const response = await fetch("/api/platform/navigation" + path, {
      method: body === undefined ? "GET" : "POST",
      headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal,
    });
    const text = await response.text();
    let data: unknown;
    try { data = JSON.parse(text); }
    catch { throw new Error(`HTTP ${response.status}：接口未返回有效数据，请确认 Java 后端已更新。`); }
    if (!response.ok) {
      const detail = (data as { detail?: unknown }).detail;
      throw new Error(`HTTP ${response.status}：${typeof detail === "string" ? detail : "保存失败，请恢复状态后重试。"}`);
    }
    return data as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw new Error("请求超时，请恢复状态后检查保存结果，再重试。");
    if (error instanceof TypeError) throw new Error("连接失败，请检查 Java 后端和 F4 服务。");
    throw error;
  } finally { window.clearTimeout(timer); }
}

export async function contentHash(content: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(content));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}
