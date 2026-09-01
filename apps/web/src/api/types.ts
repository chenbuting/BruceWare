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

export type SettingsInfo = {
  app_name: string;
  api_host: string;
  api_port: number;
  database: DatabaseInfo;
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
  created_at: string;
};
