import type { ApiResult, DatabaseWrite, ModuleList, PortalLink, SettingsInfo } from "./types";

/** 请求后端，失败时抛出中文错误 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
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
