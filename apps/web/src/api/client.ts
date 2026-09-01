import type {
  ApiResult,
  DatabaseWrite,
  InterviewSession,
  LlmWrite,
  ModuleList,
  PortalLink,
  ResumeDoc,
  SettingsInfo,
} from "./types";

/** 请求后端，失败时抛出中文错误 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers || {});
  const isForm = typeof FormData !== "undefined" && init?.body instanceof FormData;
  if (init?.body && !isForm && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, {
    ...init,
    headers,
  });
  const body = (await res.json()) as ApiResult<T>;
  if (!res.ok || !body.ok) {
    throw new Error(body.message || "请求失败");
  }
  return body.data;
}

export function fetchSettings() {
  return request<SettingsInfo>("/api/v1/settings");
}

export function testDatabase(payload: DatabaseWrite) {
  return request<{ connected: boolean }>("/api/v1/settings/test-database", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function saveDatabase(payload: DatabaseWrite) {
  return request<SettingsInfo>("/api/v1/settings/database", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function saveLlm(payload: LlmWrite) {
  return request<SettingsInfo>("/api/v1/settings/llm", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function testLlm() {
  return request<{ reply: string }>("/api/v1/settings/test-llm", {
    method: "POST",
  });
}

export function fetchModules() {
  return request<ModuleList>("/api/v1/modules");
}

export function setModuleEnabled(id: string, enabled: boolean) {
  return request<ModuleList>(`/api/v1/modules/${id}/enabled`, {
    method: "PUT",
    body: JSON.stringify({ enabled }),
  });
}

export function setModulePinned(id: string, pinned: boolean) {
  return request<ModuleList>(`/api/v1/modules/${id}/pinned`, {
    method: "PUT",
    body: JSON.stringify({ pinned }),
  });
}

export function setModuleOrder(ids: string[]) {
  return request<ModuleList>("/api/v1/modules/order", {
    method: "PUT",
    body: JSON.stringify({ ids }),
  });
}

export function fetchPortalLinks() {
  return request<{ items: PortalLink[] }>("/api/v1/portal/links");
}

export function createPortalLink(payload: { title: string; url: string; remark: string }) {
  return request<PortalLink>("/api/v1/portal/links", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updatePortalLink(id: number, payload: { title: string; url: string; remark: string }) {
  return request<PortalLink>(`/api/v1/portal/links/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deletePortalLink(id: number) {
  return request<boolean>(`/api/v1/portal/links/${id}`, {
    method: "DELETE",
  });
}

export function fetchResumeDocs() {
  return request<{ items: ResumeDoc[] }>("/api/v1/resume/docs");
}

export function createResumeDoc(payload: { title: string; target_job: string; content: string }) {
  return request<ResumeDoc>("/api/v1/resume/docs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateResumeDoc(
  id: number,
  payload: { title: string; target_job: string; content: string },
) {
  return request<ResumeDoc>(`/api/v1/resume/docs/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteResumeDoc(id: number) {
  return request<boolean>(`/api/v1/resume/docs/${id}`, {
    method: "DELETE",
  });
}

export function analyzeResumeDoc(id: number) {
  return request<ResumeDoc>(`/api/v1/resume/docs/${id}/analyze`, {
    method: "POST",
  });
}

export function generateResumeIntro(id: number) {
  return request<ResumeDoc>(`/api/v1/resume/docs/${id}/intro`, {
    method: "POST",
  });
}

export function fetchInterview(id: number) {
  return request<InterviewSession>(`/api/v1/resume/docs/${id}/interview`);
}

export function startInterview(id: number) {
  return request<InterviewSession>(`/api/v1/resume/docs/${id}/interview/start`, {
    method: "POST",
  });
}

export function replyInterview(id: number, content: string) {
  return request<InterviewSession>(`/api/v1/resume/docs/${id}/interview/reply`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function importResumeDoc(file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<ResumeDoc>("/api/v1/resume/docs/import", {
    method: "POST",
    body,
  });
}

function filenameFrom(res: Response, fallback: string) {
  const header = res.headers.get("Content-Disposition") || "";
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      /* 用后备名 */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  if (plain?.[1] && plain[1] !== "resume.docx") return plain[1];
  return fallback.endsWith(".docx") ? fallback : `${fallback}.docx`;
}

export async function downloadResumeDoc(id: number, filename: string) {
  const res = await fetch(`/api/v1/resume/docs/${id}/export`);
  if (!res.ok) {
    let message = "导出失败";
    try {
      const body = (await res.json()) as ApiResult<null>;
      message = body.message || message;
    } catch {
      /* 不是 JSON */
    }
    throw new Error(message);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameFrom(res, filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
