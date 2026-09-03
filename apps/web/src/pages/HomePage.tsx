import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import {
  fetchFilesStatus,
  fetchPortalLinks,
  fetchResumeDocs,
  fetchSettings,
  fetchWardrobeItems,
  saveFilesRoot,
} from "@/api/client";
import type { FilesStatus, ModuleInfo, SettingsInfo } from "@/api/types";
import { Card } from "@/components/Card";
import { PageFrame } from "@/components/PageFrame";
import { useModules } from "@/modules/ModuleContext";

type HomeStats = {
  resume: number | null;
  wardrobe: number | null;
  portal: number | null;
};

function moduleNote(id: string, stats: HomeStats, files: FilesStatus | null) {
  if (id === "resume") {
    if (stats.resume === null) return "打开后可写简历、做模拟面试。";
    return stats.resume ? `${stats.resume} 份简历` : "还没有简历";
  }
  if (id === "wardrobe") {
    if (stats.wardrobe === null) return "打开后可管衣服和搭配。";
    return stats.wardrobe ? `${stats.wardrobe} 件衣服` : "衣橱还是空的";
  }
  if (id === "files") {
    if (!files?.configured) return "还没指定文件夹，先去设置。";
    const ready = (files.sources || []).filter((item) => item.ready).map((item) => item.label);
    return ready.length ? `可用：${ready.join("、")}` : files.message || "文件夹还不能用";
  }
  if (id === "portal") {
    if (stats.portal === null) return "打开后可收藏常用网站。";
    return stats.portal ? `${stats.portal} 个入口` : "还没有收藏";
  }
  return "";
}

/** 首页：一眼看到各模块和当前状态，点卡片就能进去 */
export function HomePage() {
  const location = useLocation();
  const { modules } = useModules();
  const [settings, setSettings] = useState<SettingsInfo | null>(null);
  const [files, setFiles] = useState<FilesStatus | null>(null);
  const [stats, setStats] = useState<HomeStats>({ resume: null, wardrobe: null, portal: null });
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState("");
  const [error, setError] = useState("");

  const apps = modules.filter((item) => item.kind === "app");

  useEffect(() => {
    if (location.pathname !== "/") return;
    let cancelled = false;
    Promise.allSettled([fetchSettings(), fetchFilesStatus(), fetchResumeDocs(), fetchWardrobeItems(), fetchPortalLinks()]).then(
      ([settingsRes, filesRes, resumeRes, wardrobeRes, portalRes]) => {
        if (cancelled) return;
        if (settingsRes.status === "fulfilled") setSettings(settingsRes.value);
        if (filesRes.status === "fulfilled") setFiles(filesRes.value);
        setStats({
          resume: resumeRes.status === "fulfilled" ? resumeRes.value.items.length : null,
          wardrobe: wardrobeRes.status === "fulfilled" ? wardrobeRes.value.items.length : null,
          portal: portalRes.status === "fulfilled" ? portalRes.value.items.length : null,
        });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  function moduleTo(item: ModuleInfo) {
    return item.enabled ? item.route || `/m/${item.id}` : "/m/hub";
  }

  function onMove() {
    const root = (settings?.files?.root || "").trim();
    if (!root) return;
    setBusy(true);
    setError("");
    setHint("");
    saveFilesRoot(root, true)
      .then((data) => {
        setSettings(data);
        setHint("项目文件已搬到根目录下的 BruceWare");
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }

  const needMove = Boolean(settings?.files?.generated?.needs_move && settings.files.root);

  return (
    <PageFrame hideHeader wide>
      {error ? <p className="mb-4 text-[13px] text-[var(--err)]">{error}</p> : null}
      {hint ? <p className="mb-4 text-[13px] text-[var(--ok)]">{hint}</p> : null}

      {needMove ? (
        <Card className="mb-4 px-5 py-4">
          <p className="text-[13px] leading-6 text-[var(--muted)]">衣橱图或本地库还没完全进根目录下的 BruceWare。搬过去后，换电脑把这个文件夹拷走就行。</p>
          <button
            type="button"
            className="mt-3 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px] disabled:opacity-50"
            disabled={busy}
            onClick={onMove}
          >
            搬过去
          </button>
        </Card>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {apps.map((item) => (
          <Link key={item.id} to={moduleTo(item)} className="block">
            <Card title={item.name} className="h-full px-5 py-4">
              <p className="text-[13px] leading-6 text-[var(--muted)]">{item.description || moduleNote(item.id, stats, files)}</p>
              <p className="mt-3 text-[13px] text-[var(--text)]">
                {item.enabled ? moduleNote(item.id, stats, files) : "已关闭，点这里去模块里打开"}
              </p>
            </Card>
          </Link>
        ))}
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <Link to="/settings" className="block">
          <Card title="数据源" className="px-5 py-4">
            <p className="text-[13px] leading-6 text-[var(--muted)]">
              {settings ? `${settings.database.label} · ${settings.database.connected ? "正常" : "连不上"}` : "正在读取…"}
            </p>
          </Card>
        </Link>
        <Link to="/settings" className="block">
          <Card title="AI" className="px-5 py-4">
            <p className="text-[13px] leading-6 text-[var(--muted)]">
              {settings ? (settings.llm.has_key ? `${settings.llm.model} · 已配置` : "还没填 Key，简历和衣橱用不了 AI") : "正在读取…"}
            </p>
          </Card>
        </Link>
        <Link to="/settings" className="block">
          <Card title="文件位置" className="px-5 py-4">
            <p className="text-[13px] leading-6 text-[var(--muted)]">
              {settings?.files?.root ? settings.files.root : settings ? "还没指定本地根目录" : "正在读取…"}
            </p>
          </Card>
        </Link>
      </div>
    </PageFrame>
  );
}
