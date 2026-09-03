import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import type { ModuleInfo } from "@/api/types";
import { Card } from "@/components/Card";
import { PageFrame } from "@/components/PageFrame";
import { useModules } from "@/modules/ModuleContext";
import { getModulePage } from "@/modules/registry";
import { HomePage } from "@/pages/HomePage";
import { SettingsPage } from "@/pages/SettingsPage";

type Tab = {
  id: string;
  to: string;
  label: string;
  moduleId?: string;
};

const HOME_TAB: Tab = { id: "home", to: "/", label: "首页" };

function tabFromPath(pathname: string, modules: ModuleInfo[]): Tab | null {
  if (pathname === "/") return HOME_TAB;
  if (pathname === "/settings") return { id: "settings", to: "/settings", label: "设置" };
  if (pathname === "/portal") return { id: "module:portal", to: "/m/portal", label: "网站入口", moduleId: "portal" };

  if (pathname.startsWith("/m/")) {
    const moduleId = pathname.slice(3).split("/")[0] || "";
    if (!moduleId) return null;
    const found = modules.find((item) => item.id === moduleId);
    const entry = getModulePage(moduleId);
    return {
      id: `module:${moduleId}`,
      to: `/m/${moduleId}`,
      label: found?.name || entry?.title || moduleId,
      moduleId,
    };
  }
  return null;
}

/** 同一窗口里用标签切换页面，模块保持挂载 */
export function Workspace() {
  const location = useLocation();
  const navigate = useNavigate();
  const { modules } = useModules();
  const [tabs, setTabs] = useState<Tab[]>([HOME_TAB]);

  const current = tabFromPath(location.pathname, modules);

  useEffect(() => {
    if (location.pathname === "/modules") {
      navigate("/m/hub", { replace: true });
      return;
    }
    if (location.pathname === "/portal") {
      navigate("/m/portal", { replace: true });
      return;
    }
    if (!current && location.pathname !== "/") {
      if (location.pathname.startsWith("/m/") && modules.length === 0) return;
      navigate("/", { replace: true });
    }
  }, [current, location.pathname, modules.length, navigate]);

  useEffect(() => {
    if (!current) return;
    if (current.moduleId) {
      const found = modules.find((item) => item.id === current.moduleId);
      if (found && found.kind === "app" && !found.enabled) {
        navigate("/", { replace: true });
        return;
      }
    }
    setTabs((prev) => (prev.some((tab) => tab.id === current.id) ? prev : [...prev, current]));
  }, [current, modules, navigate]);

  useEffect(() => {
    setTabs((prev) =>
      prev.filter((tab) => {
        if (!tab.moduleId) return true;
        const found = modules.find((item) => item.id === tab.moduleId);
        if (!found) return true;
        return found.kind === "common" || found.enabled;
      }),
    );
  }, [modules]);

  function closeTab(id: string) {
    if (id === HOME_TAB.id) return;
    setTabs((prev) => {
      const next = prev.filter((tab) => tab.id !== id);
      if (current?.id === id) {
        const fallback = next[next.length - 1] || HOME_TAB;
        navigate(fallback.to);
      }
      return next.length > 0 ? next : [HOME_TAB];
    });
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-[var(--line)] bg-[var(--paper)] px-3 py-2">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            className={`flex shrink-0 items-center rounded-md border text-[13px] ${
              current?.id === tab.id
                ? "border-[var(--line)] bg-[var(--bg)]"
                : "border-transparent text-[var(--muted)] hover:bg-[var(--hover)]"
            }`}
          >
            <NavLink to={tab.to} className="px-2.5 py-1">
              {tab.label}
            </NavLink>
            {tab.id !== HOME_TAB.id ? (
              <button
                type="button"
                title="关闭"
                className="pr-2 text-[var(--muted)]"
                onClick={() => closeTab(tab.id)}
              >
                ×
              </button>
            ) : null}
          </div>
        ))}
      </div>
      <div className="relative min-h-0 flex-1">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            className={tab.id === current?.id ? "flex h-full min-h-0 flex-col" : "hidden"}
          >
            <TabPane tab={tab} />
          </div>
        ))}
      </div>
    </div>
  );
}

function TabPane({ tab }: { tab: Tab }) {
  if (tab.id === "home") return <HomePage />;
  if (tab.id === "settings") return <SettingsPage />;
  if (tab.moduleId) {
    const entry = getModulePage(tab.moduleId);
    if (!entry) {
      return (
        <PageFrame hideHeader wide>
          <Card className="px-5 py-4">
            <p className="text-[13px] leading-6 text-[var(--muted)]">这个模块还没有接入页面。</p>
          </Card>
        </PageFrame>
      );
    }
    const Page = entry.page;
    return (
      <PageFrame hideHeader wide={entry.wide} fill={entry.fill}>
        <Page />
      </PageFrame>
    );
  }
  return null;
}
