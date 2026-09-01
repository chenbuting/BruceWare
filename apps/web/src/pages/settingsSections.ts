/** 设置内容归类：分类是文件夹，设置项可以自己挪。存在本机。 */

export type SettingItemId = "overview" | "database" | "ai" | "backup";

export type SettingsCategory = {
  id: string;
  label: string;
};

export type SettingsItemPlace = {
  id: SettingItemId;
  categoryId: string;
};

export type SettingsLayout = {
  categories: SettingsCategory[];
  items: SettingsItemPlace[];
};

export const SETTING_ITEMS: { id: SettingItemId; label: string }[] = [
  { id: "overview", label: "当前" },
  { id: "database", label: "数据源" },
  { id: "backup", label: "备份" },
  { id: "ai", label: "AI" },
];

const KEY = "bruceware.settings-layout";
const OLD_KEY = "bruceware.settings-sections";

function defaultLayout(): SettingsLayout {
  return {
    categories: [
      { id: "cat-overview", label: "概览" },
      { id: "cat-database", label: "数据源" },
      { id: "cat-ai", label: "AI" },
    ],
    items: [
      { id: "overview", categoryId: "cat-overview" },
      { id: "database", categoryId: "cat-database" },
      { id: "backup", categoryId: "cat-database" },
      { id: "ai", categoryId: "cat-ai" },
    ],
  };
}

function normalize(layout: SettingsLayout): SettingsLayout {
  const categories = layout.categories.filter((item) => item && item.id && item.label !== undefined);
  const safeCats = categories.length > 0 ? categories : defaultLayout().categories;
  const fallback = safeCats[0].id;
  const seen = new Set<SettingItemId>();
  const items: SettingsItemPlace[] = [];
  for (const item of layout.items || []) {
    if (!SETTING_ITEMS.some((row) => row.id === item.id) || seen.has(item.id)) continue;
    seen.add(item.id);
    items.push({
      id: item.id,
      categoryId: safeCats.some((cat) => cat.id === item.categoryId) ? item.categoryId : fallback,
    });
  }
  for (const row of SETTING_ITEMS) {
    if (seen.has(row.id)) continue;
    const prefer = row.id === "backup" ? "cat-database" : fallback;
    items.push({
      id: row.id,
      categoryId: safeCats.some((cat) => cat.id === prefer) ? prefer : fallback,
    });
  }
  return { categories: safeCats, items };
}

function migrateOld(): SettingsLayout | null {
  try {
    const raw = JSON.parse(localStorage.getItem(OLD_KEY) || "[]") as Array<{
      id: string;
      label: string;
      builtin?: SettingItemId;
    }>;
    if (!Array.isArray(raw) || raw.length === 0) return null;
    const categories: SettingsCategory[] = [];
    const items: SettingsItemPlace[] = [];
    for (const row of raw) {
      if (!row?.id) continue;
      const catId = row.builtin ? `cat-${row.builtin}` : row.id;
      if (!categories.some((item) => item.id === catId)) {
        categories.push({ id: catId, label: row.label || row.id });
      }
      if (row.builtin) items.push({ id: row.builtin, categoryId: catId });
    }
    return normalize({ categories, items });
  } catch {
    return null;
  }
}

export function loadLayout(): SettingsLayout {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "null");
    if (raw && Array.isArray(raw.categories) && Array.isArray(raw.items)) {
      return normalize(raw as SettingsLayout);
    }
  } catch {
    /* 用旧数据或默认 */
  }
  const migrated = migrateOld();
  if (migrated) {
    saveLayout(migrated);
    return migrated;
  }
  return defaultLayout();
}

export function saveLayout(layout: SettingsLayout) {
  try {
    localStorage.setItem(KEY, JSON.stringify(normalize(layout)));
  } catch {
    /* 忽略本地存储失败 */
  }
}

export function newCategory(): SettingsCategory {
  return { id: `cat-${Date.now()}`, label: "新分类" };
}
