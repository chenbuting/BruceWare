/** 后端统一返回 */
export type ApiResult<T> = {
  ok: boolean;
  data: T;
  message: string;
};

export type DatabaseForm = {
  mode: "local" | "mysql" | "postgres";
  sqlite_path: string;
  host: string;
  port: number;
  name: string;
  user: string;
  has_password: boolean;
};

export type DatabaseInfo = {
  mode: "local" | "remote";
  engine: string;
  label: string;
  target: string;
  connected: boolean;
  error: string;
  form: DatabaseForm;
};

export type LlmInfo = {
  base_url: string;
  model: string;
  image_base_url: string;
  image_model: string;
  has_key: boolean;
  has_image_key: boolean;
};

export type FilesSftpSettings = {
  host: string;
  port: number;
  user: string;
  remote: string;
  has_password: boolean;
  configured: boolean;
  ready: boolean;
};

export type FilesSettings = {
  root: string;
  ready: boolean;
  sftp?: FilesSftpSettings;
  generated?: { path: string; has_files: boolean; follow: boolean; needs_move?: boolean };
};

export type FolderBrowse = {
  path: string;
  parent: string;
  crumbs: { name: string; path: string }[];
  folders: { name: string; path: string }[];
};

export type SettingsInfo = {
  app_name: string;
  api_host: string;
  api_port: number;
  database: DatabaseInfo;
  llm: LlmInfo;
  files: FilesSettings;
};

export type FilesSource = {
  id: "local" | "sftp";
  label: string;
  configured: boolean;
  ready: boolean;
  root: string;
  message: string;
};

export type FilesStatus = {
  configured: boolean;
  ready: boolean;
  root: string;
  message: string;
  sources: FilesSource[];
};

export type FilesEntry = {
  name: string;
  path: string;
  kind: "dir" | "file";
  size: number;
  mtime: string;
  preview: string;
};

export type FilesList = {
  root: string;
  path: string;
  crumbs: { name: string; path: string }[];
  items: FilesEntry[];
};

export type LlmWrite = {
  base_url: string;
  model: string;
  image_base_url: string;
  image_model: string;
  api_key: string;
  image_api_key: string;
};

export type WardrobeItem = {
  id: number;
  name: string;
  part: string;
  part_label: string;
  color: string;
  secondary_color: string;
  tags: string[];
  source_name: string;
  has_cutout: boolean;
  has_modeled: boolean;
  cutout_url: string;
  modeled_url: string;
  original_url: string;
  created_at: string;
};

export type WardrobeLook = {
  id: number;
  title: string;
  item_ids: number[];
  image_url: string;
  source_image_url: string;
  prompt: string;
  style_name: string;
  style_image_urls: string[];
  image_ratio: string;
  image_quality: string;
  created_at: string;
};

export type WardrobeSuggest = {
  item_ids: number[];
  reason: string;
  items: WardrobeItem[];
};

export type WardrobeStyle = {
  id: number;
  name: string;
  active: boolean;
  image_urls: string[];
  created_at: string;
};

export type WardrobeDetected = {
  name: string;
  part: string;
  color: string;
  secondaryColor: string;
  tags: string[];
  boundingBox: { x: number; y: number; width: number; height: number };
};

export type DatabaseWrite = {
  mode: "local" | "mysql" | "postgres";
  sqlite_path: string;
  host: string;
  port: number | null;
  name: string;
  user: string;
  password: string;
};

export type ModuleInfo = {
  id: string;
  name: string;
  description: string;
  version: string;
  path: string;
  route: string;
  kind: "common" | "app";
  enabled: boolean;
  pinned: boolean;
};

export type ModuleList = {
  items: ModuleInfo[];
  count: number;
};

export type PortalLink = {
  id: number;
  title: string;
  url: string;
  remark: string;
  category: string;
  created_at: string;
};

export type ResumeDoc = {
  id: number;
  title: string;
  target_job: string;
  content: string;
  analysis: string;
  intro: string;
  updated_at: string;
};

export type InterviewMessage = {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
};

export type InterviewSession = {
  id: number | null;
  resume_id: number;
  messages: InterviewMessage[];
};

export type KbEvidenceMode = "strict" | "loose";

export type KbVisionEngine = "vision" | "ocr";

export type KbLibrary = {
  id: number;
  name: string;
  description: string;
  wiki_enabled: boolean;
  wiki_learn: boolean;
  vision_enabled: boolean;
  vision_engine: KbVisionEngine;
  evidence_mode: KbEvidenceMode;
  rule: string;
  created_at: string;
};

export type KbWikiItem = {
  id: number;
  title: string;
  wiki_updated_at: string;
  wiki_stale: boolean;
};

export type KbWikiList = {
  items: KbWikiItem[];
  total: number;
  page: number;
  page_size: number;
  all_count: number;
  stale_count: number;
};

export type KbFolder = {
  id: number;
  library_id: number;
  parent_id: number | null;
  name: string;
};

export type KbAskImage = {
  id: number;
  alt: string;
  page: number;
  url: string;
};

export type KbDocAsset = {
  id: number;
  alt: string;
  page: number;
  url: string;
  caption: string;
  keywords: string;
  ocr_text: string;
};

export type KbAskHit = {
  id: number;
  title: string;
  score: number;
  images?: KbAskImage[];
};

export type KbAskResult = {
  answer: string;
  citations: KbAskHit[];
  used_llm: boolean;
  evidence_mode?: KbEvidenceMode;
  wiki_update_hint?: string;
  used_vector?: boolean;
};

/** 发给后端的上一轮问答，只帮听懂指代。 */
export type KbAskHistoryItem = {
  question: string;
  answer: string;
};

export type KbDocument = {
  id: number;
  library_id: number;
  folder_id: number | null;
  title: string;
  file_name: string;
  tags: string;
  kind: string;
  preview: string;
  parse_status: string;
  has_wiki: boolean;
  wiki_summary: string;
  wiki_updated_at: string;
  wiki_stale: boolean;
  created_at: string;
  updated_at: string;
};
