import type {
  ApiResult,
  DatabaseWrite,
  InterviewSession,
  LlmWrite,
  ModuleList,
  PortalLink,
  ResumeDoc,
  SettingsInfo,
  WardrobeDetected,
  WardrobeItem,
  WardrobeLook,
  WardrobeStyle,
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

export function generateResumeIntro(id: number, style: string) {
  return request<ResumeDoc>(`/api/v1/resume/docs/${id}/intro`, {
    method: "POST",
    body: JSON.stringify({ style }),
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
  if (fallback.includes(".")) return fallback;
  return `${fallback}.docx`;
}

export async function downloadBackup() {
  const res = await fetch("/api/v1/settings/export");
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
  link.download = filenameFrom(res, "bruceware-backup.json");
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function importBackup(file: File, mode: "replace" | "merge") {
  const body = new FormData();
  body.append("file", file);
  body.append("mode", mode);
  return request<{ mode: string; portal: number; resume: number; interview: number }>("/api/v1/settings/import", {
    method: "POST",
    body,
  });
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

export function fetchWardrobeStatus() {
  return request<{ has_reference: boolean; reference_url: string; active_style_id: number; active_style_name: string }>(
    "/api/v1/wardrobe/status",
  );
}

export function saveWardrobeReference(file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<{ has_reference: boolean; reference_url: string }>("/api/v1/wardrobe/reference", {
    method: "POST",
    body,
  });
}

export function fetchWardrobeItems() {
  return request<{ items: WardrobeItem[] }>("/api/v1/wardrobe/items");
}

export function addWardrobeItem(file: File, name: string, part: string) {
  const body = new FormData();
  body.append("file", file);
  body.append("name", name);
  body.append("part", part);
  return request<WardrobeItem>("/api/v1/wardrobe/items", { method: "POST", body });
}

export function deleteWardrobeItem(id: number) {
  return request<boolean>(`/api/v1/wardrobe/items/${id}`, { method: "DELETE" });
}

export function analyzeWardrobePhoto(file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<{ upload_id: string; source_name: string; items: WardrobeDetected[] }>("/api/v1/wardrobe/analyze", {
    method: "POST",
    body,
  });
}

export function importWardrobeItems(uploadId: string, items: WardrobeDetected[]) {
  return request<{ items: WardrobeItem[] }>("/api/v1/wardrobe/import", {
    method: "POST",
    body: JSON.stringify({ upload_id: uploadId, items }),
  });
}

export function remakeWardrobeModeled(id: number) {
  return request<WardrobeItem>(`/api/v1/wardrobe/items/${id}/modeled`, { method: "POST" });
}

export function fetchWardrobeLooks() {
  return request<{ items: WardrobeLook[] }>("/api/v1/wardrobe/looks");
}

export function createWardrobeLook(itemIds: number[], title: string) {
  return request<WardrobeLook>("/api/v1/wardrobe/looks", {
    method: "POST",
    body: JSON.stringify({ item_ids: itemIds, title }),
  });
}

export function deleteWardrobeLook(id: number) {
  return request<boolean>(`/api/v1/wardrobe/looks/${id}`, { method: "DELETE" });
}

/** 从现有搭配或上传图做姿势裂变，一次 2 张 */
export function varyWardrobeLook(lookId?: number, file?: File) {
  const body = new FormData();
  if (lookId) body.append("look_id", String(lookId));
  if (file) body.append("file", file);
  return request<{ items: WardrobeLook[] }>("/api/v1/wardrobe/looks/vary", { method: "POST", body });
}

export function fetchWardrobeStyles() {
  return request<{ items: WardrobeStyle[]; active_id: number }>("/api/v1/wardrobe/styles");
}

export function addWardrobeStyle(name: string, files: File[]) {
  const body = new FormData();
  body.append("name", name);
  files.forEach((file) => body.append("files", file));
  return request<WardrobeStyle>("/api/v1/wardrobe/styles", { method: "POST", body });
}

export function setWardrobeStyleActive(id: number, active: boolean) {
  return request<{ items: WardrobeStyle[]; active_id: number }>(`/api/v1/wardrobe/styles/${id}/active`, {
    method: "PUT",
    body: JSON.stringify({ active }),
  });
}

export function deleteWardrobeStyle(id: number) {
  return request<boolean>(`/api/v1/wardrobe/styles/${id}`, { method: "DELETE" });
}
