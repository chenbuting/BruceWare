import type {
  ApiResult,
  DatabaseWrite,
  FilesEntry,
  FilesList,
  FilesStatus,
  FolderBrowse,
  InterviewSession,
  KbAskResult,
  KbDocAsset,
  KbDocument,
  KbEvidenceMode,
  KbVisionEngine,
  KbFolder,
  KbLibrary,
  KbWikiList,
  LlmWrite,
  ModuleList,
  PortalLink,
  ResumeDoc,
  SettingsInfo,
  WardrobeDetected,
  WardrobeItem,
  WardrobeLook,
  WardrobeSuggest,
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

export function saveFilesRoot(root: string, moveGenerated = false) {
  return request<SettingsInfo>("/api/v1/settings/files", {
    method: "PUT",
    body: JSON.stringify({ root, move_generated: moveGenerated }),
  });
}

export function saveFilesSftp(body: { host: string; port: number; user: string; password: string; remote: string }) {
  return request<SettingsInfo>("/api/v1/settings/files/sftp", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function testFilesSftp(body: { host: string; port: number; user: string; password: string; remote: string }) {
  return request<boolean>("/api/v1/settings/files/sftp/test", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function browseFolders(path = "") {
  return request<FolderBrowse>(`/api/v1/settings/files/browse?path=${encodeURIComponent(path)}`);
}

export function fetchFilesStatus() {
  return request<FilesStatus>("/api/v1/files/status");
}

export function fetchFilesList(path = "", source = "local") {
  return request<FilesList>(`/api/v1/files/list?path=${encodeURIComponent(path)}&source=${encodeURIComponent(source)}`);
}

export function searchFiles(query: string, path = "", source = "local") {
  return request<{ query: string; path: string; items: FilesEntry[] }>(
    `/api/v1/files/search?q=${encodeURIComponent(query)}&path=${encodeURIComponent(path)}&source=${encodeURIComponent(source)}`,
  );
}

export function makeFilesDir(path: string, name: string, source = "local") {
  return request<FilesEntry>("/api/v1/files/mkdir", {
    method: "POST",
    body: JSON.stringify({ path, name, source }),
  });
}

export function uploadFiles(path: string, files: File[], source = "local") {
  const body = new FormData();
  body.append("path", path);
  body.append("source", source);
  files.forEach((file) => body.append("files", file));
  return request<{ items: FilesEntry[] }>("/api/v1/files/upload", { method: "POST", body });
}

export function renameFilesEntry(path: string, name: string, source = "local") {
  return request<FilesEntry>("/api/v1/files/rename", {
    method: "POST",
    body: JSON.stringify({ path, name, source }),
  });
}

export function moveFilesEntry(path: string, dest: string, source = "local") {
  return request<FilesEntry>("/api/v1/files/move", {
    method: "POST",
    body: JSON.stringify({ path, dest, source }),
  });
}

export function deleteFilesEntry(path: string, source = "local") {
  return request<boolean>("/api/v1/files/delete", {
    method: "POST",
    body: JSON.stringify({ path, source }),
  });
}

export function openFilesEntry(path: string, source = "local") {
  return request<boolean>("/api/v1/files/open", {
    method: "POST",
    body: JSON.stringify({ path, source }),
  });
}

export async function downloadFilesEntry(path: string, filename: string, source = "local") {
  const res = await fetch(`/api/v1/files/download?path=${encodeURIComponent(path)}&source=${encodeURIComponent(source)}`);
  if (!res.ok) {
    let message = "下载失败";
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

export function createPortalLink(payload: { title: string; url: string; remark: string; category: string }) {
  return request<PortalLink>("/api/v1/portal/links", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updatePortalLink(id: number, payload: { title: string; url: string; remark: string; category: string }) {
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

/** 改衣橱单件的分类或名称 */
export function updateWardrobeItem(id: number, payload: { part?: string; name?: string }) {
  return request<WardrobeItem>(`/api/v1/wardrobe/items/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
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

export function createWardrobeLook(itemIds: number[], title: string, ratio = "", quality = "") {
  return request<WardrobeLook>("/api/v1/wardrobe/looks", {
    method: "POST",
    body: JSON.stringify({ item_ids: itemIds, title, ratio, quality }),
  });
}

export function deleteWardrobeLook(id: number) {
  return request<boolean>(`/api/v1/wardrobe/looks/${id}`, { method: "DELETE" });
}

/** 按改过的提示词重做这一套搭配 */
export function remakeWardrobeLook(lookId: number, prompt: string, ratio = "", quality = "") {
  return request<WardrobeLook>(`/api/v1/wardrobe/looks/${lookId}/remake`, {
    method: "POST",
    body: JSON.stringify({ prompt, ratio, quality }),
  });
}

/** 看本人照片，从衣橱里出 2 套适合这个人的搭配方案 */
export function suggestWardrobeLooks() {
  return request<{ items: WardrobeSuggest[] }>("/api/v1/wardrobe/suggest", { method: "POST" });
}

/** 人、衣服、姿势不变，只换场景 */
export function changeWardrobeScene(lookId: number, scene: string, ratio = "", quality = "") {
  return request<WardrobeLook>("/api/v1/wardrobe/looks/scene", {
    method: "POST",
    body: JSON.stringify({ look_id: lookId, scene, ratio, quality }),
  });
}

/** 从现有搭配或上传图做姿势裂变，张数 1～3 */
export function varyWardrobeLook(lookId?: number, file?: File, count = 2, ratio = "", quality = "") {
  const body = new FormData();
  if (lookId) body.append("look_id", String(lookId));
  if (file) body.append("file", file);
  body.append("count", String(Math.max(1, Math.min(3, count))));
  if (ratio) body.append("ratio", ratio);
  if (quality) body.append("quality", quality);
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

export function fetchKbLibraries() {
  return request<{ items: KbLibrary[] }>("/api/v1/kb/libraries");
}

export function createKbLibrary(name: string, description = "") {
  return request<KbLibrary>("/api/v1/kb/libraries", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
}

export function updateKbLibrary(id: number, name: string, description = "") {
  return request<KbLibrary>(`/api/v1/kb/libraries/${id}`, {
    method: "PUT",
    body: JSON.stringify({ name, description }),
  });
}

export function deleteKbLibrary(id: number) {
  return request<boolean>(`/api/v1/kb/libraries/${id}`, { method: "DELETE" });
}

export function updateKbLibraryPolicy(
  id: number,
  wikiEnabled: boolean,
  evidenceMode: KbEvidenceMode,
  rule: string,
  wikiLearn = false,
  visionEnabled = false,
  visionEngine: KbVisionEngine = "vision",
) {
  return request<KbLibrary>(`/api/v1/kb/libraries/${id}/policy`, {
    method: "PUT",
    body: JSON.stringify({
      wiki_enabled: wikiEnabled,
      wiki_learn: wikiLearn,
      vision_enabled: visionEnabled,
      vision_engine: visionEngine,
      evidence_mode: evidenceMode,
      rule,
    }),
  });
}

export function fetchKbWikis(
  libraryId: number,
  query: { q?: string; stale?: string; sort?: string; order?: string; page?: number } = {},
) {
  const params = new URLSearchParams();
  if (query.q?.trim()) params.set("q", query.q.trim());
  if (query.stale) params.set("stale", query.stale);
  if (query.sort) params.set("sort", query.sort);
  if (query.order) params.set("order", query.order);
  if (query.page) params.set("page", String(query.page));
  const qs = params.toString();
  return request<KbWikiList>(`/api/v1/kb/libraries/${libraryId}/wikis${qs ? `?${qs}` : ""}`);
}

export function fetchKbFolders(libraryId: number) {
  return request<{ items: KbFolder[] }>(`/api/v1/kb/libraries/${libraryId}/folders`);
}

export function createKbFolder(libraryId: number, name: string, parentId: number | null) {
  return request<KbFolder>(`/api/v1/kb/libraries/${libraryId}/folders`, {
    method: "POST",
    body: JSON.stringify({ name, parent_id: parentId }),
  });
}

export function renameKbFolder(id: number, name: string) {
  return request<KbFolder>(`/api/v1/kb/folders/${id}`, {
    method: "PUT",
    body: JSON.stringify({ name }),
  });
}

export function deleteKbFolder(id: number) {
  return request<boolean>(`/api/v1/kb/folders/${id}`, { method: "DELETE" });
}

export function fetchKbDocuments(libraryId: number, folderId: number | null, q = "", tag = "") {
  const params = new URLSearchParams();
  if (folderId != null) params.set("folder_id", String(folderId));
  if (q.trim()) params.set("q", q.trim());
  if (tag.trim()) params.set("tag", tag.trim());
  const query = params.toString();
  return request<{ items: KbDocument[] }>(`/api/v1/kb/libraries/${libraryId}/documents${query ? `?${query}` : ""}`);
}

export function uploadKbDocument(libraryId: number, file: File, folderId: number | null, tags = "", force = false) {
  const body = new FormData();
  body.append("file", file);
  if (folderId != null) body.append("folder_id", String(folderId));
  if (tags) body.append("tags", tags);
  if (force) body.append("force", "true");
  return request<KbDocument>(`/api/v1/kb/libraries/${libraryId}/documents`, { method: "POST", body });
}

export function updateKbDocument(id: number, payload: { title?: string; tags?: string; folder_id?: number | null }) {
  return request<KbDocument>(`/api/v1/kb/documents/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteKbDocument(id: number) {
  return request<boolean>(`/api/v1/kb/documents/${id}`, { method: "DELETE" });
}

export function kbDocumentFileUrl(id: number) {
  return `/api/v1/kb/documents/${id}/file`;
}

export function kbAssetFileUrl(id: number) {
  return `/api/v1/kb/assets/${id}/file`;
}

export function fetchKbDocumentAssets(id: number) {
  return request<{ items: KbDocAsset[] }>(`/api/v1/kb/documents/${id}/assets`);
}

export function saveKbAssetOcr(id: number, ocrText: string) {
  return request<KbDocAsset>(`/api/v1/kb/assets/${id}`, {
    method: "PUT",
    body: JSON.stringify({ ocr_text: ocrText }),
  });
}

export function recognizeKbDocument(id: number) {
  return request<{ done: number; left: number; message: string }>(`/api/v1/kb/documents/${id}/vision`, { method: "POST" });
}

export function recognizeKbAsset(id: number) {
  return request<KbDocAsset>(`/api/v1/kb/assets/${id}/vision`, { method: "POST" });
}

export function fetchKbDocument(id: number) {
  return request<KbDocument>(`/api/v1/kb/documents/${id}`);
}

export function fetchKbDocumentText(id: number) {
  return request<{ text: string }>(`/api/v1/kb/documents/${id}/text`);
}

export function askKbLibrary(
  libraryId: number,
  question: string,
  folderId: number | null,
  onlyFolder: boolean,
  evidenceMode: KbEvidenceMode | "",
) {
  return request<KbAskResult>(`/api/v1/kb/libraries/${libraryId}/ask`, {
    method: "POST",
    body: JSON.stringify({
      question,
      folder_id: onlyFolder ? folderId : null,
      only_folder: onlyFolder && folderId != null,
      evidence_mode: evidenceMode || null,
    }),
  });
}

export function generateKbWiki(id: number) {
  return request<KbDocument>(`/api/v1/kb/documents/${id}/wiki`, { method: "POST" });
}

export function saveKbWiki(id: number, summary: string) {
  return request<KbDocument>(`/api/v1/kb/documents/${id}/wiki`, {
    method: "PUT",
    body: JSON.stringify({ summary }),
  });
}

export function deleteKbWiki(id: number) {
  return request<KbDocument>(`/api/v1/kb/documents/${id}/wiki`, { method: "DELETE" });
}
