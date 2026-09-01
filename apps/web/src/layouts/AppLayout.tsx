import { Boxes, CircleHelp, FileText, Globe, GripVertical, Home, PanelLeftClose, PanelLeftOpen, Settings, Shirt } from "lucide-react";
import { NavLink } from "react-router-dom";
import { useEffect, useRef, useState, type ElementType } from "react";

import { fetchSettings, setModuleOrder } from "@/api/client";
import type { ModuleInfo } from "@/api/types";
import { useModules } from "@/modules/ModuleContext";
import { Workspace } from "@/workspace/Workspace";

const MODULE_ICONS: Record<string, ElementType> = {
  help: CircleHelp,
  hub: Boxes,
  portal: Globe,
  resume: FileText,
  wardrobe: Shirt,
};

const SIDEBAR_KEY = "bruceware.sidebar-collapsed";

function readCollapsed() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  } catch {
    return false;
  }
}

function moduleTo(item: ModuleInfo) {
  return item.route.startsWith("/m/") ? item.route : `/m/${item.id}`;
}

function navClass(isActive: boolean, collapsed: boolean) {
  return `flex min-w-0 flex-1 items-center rounded-md text-[13px] ${
    collapsed ? "justify-center px-0 py-2" : "gap-2 px-2.5 py-2"
  } ${
    isActive
      ? "bg-[var(--paper)] font-medium text-[var(--text)]"
      : "text-[var(--muted)] hover:bg-[var(--hover)] hover:text-[var(--text)]"
  }`;
}

function NavItem({
  to,
  label,
  icon: Icon,
  end,
  collapsed,
}: {
  to: string;
  label: string;
  icon: ElementType;
  end?: boolean;
  collapsed: boolean;
}) {
  return (
    <NavLink to={to} end={end} title={label} className={({ isActive }) => navClass(isActive, collapsed)}>
      <Icon size={16} />
      {collapsed ? null : label}
    </NavLink>
  );
}

/** 右侧抓手才能拖，点名称不会误拖 */
function DraggableNavItem({
  to,
  label,
  icon: Icon,
  collapsed,
  dragging,
  onDragStartItem,
  onDropItem,
  onDragEndItem,
}: {
  to: string;
  label: string;
  icon: ElementType;
  collapsed: boolean;
  dragging: boolean;
  onDragStartItem: () => void;
  onDropItem: () => void;
  onDragEndItem: () => void;
}) {
  const rowRef = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={rowRef}
      className={`flex items-center rounded-md ${dragging ? "opacity-50" : ""}`}
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDropItem}
    >
      <NavLink to={to} title={label} className={({ isActive }) => navClass(isActive, collapsed)}>
        <Icon size={16} />
        {collapsed ? null : label}
      </NavLink>
      {collapsed ? null : (
        <span
          draggable
          title="按住拖动"
          className="shrink-0 cursor-grab px-1.5 py-2 text-[var(--muted)] hover:text-[var(--text)]"
          onClick={(event) => event.preventDefault()}
          onDragStart={(event) => {
            onDragStartItem();
            event.dataTransfer.effectAllowed = "move";
            if (rowRef.current) {
              event.dataTransfer.setDragImage(rowRef.current, rowRef.current.clientWidth - 8, 16);
            }
          }}
          onDragEnd={onDragEndItem}
        >
          <GripVertical size={14} />
        </span>
      )}
    </div>
  );
}

/** 侧栏：首页 + 已开启功能 + 公共模块；设置单独放底部 */
export function AppLayout() {
  const { modules, reload } = useModules();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [dbLabel, setDbLabel] = useState("检测数据源…");
  const [connected, setConnected] = useState<boolean | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);

  useEffect(() => {
    fetchSettings()
      .then((info) => {
        setDbLabel(info.database.label);
        setConnected(info.database.connected);
      })
      .catch(() => {
        setDbLabel("后端未连接");
        setConnected(false);
      });
  }, []);

  function toggleSidebar() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
      } catch {
        /* 忽略本地存储失败 */
      }
      return next;
    });
  }

  const apps = modules.filter((item) => item.kind === "app" && item.enabled && item.pinned);
  const commons = modules.filter((item) => item.kind === "common");

  function moveIn(group: ModuleInfo[], fromId: string, toId: string) {
    if (fromId === toId) return;
    if (!group.some((item) => item.id === fromId) || !group.some((item) => item.id === toId)) return;
    const ids = group.map((item) => item.id);
    const from = ids.indexOf(fromId);
    const to = ids.indexOf(toId);
    if (from < 0 || to < 0) return;
    ids.splice(from, 1);
    ids.splice(to, 0, fromId);
    const isApp = group[0]?.kind === "app";
    const appIds = isApp ? ids : apps.map((item) => item.id);
    const commonIds = isApp ? commons.map((item) => item.id) : ids;
    setModuleOrder([...appIds, ...commonIds])
      .then(() => reload())
      .catch(() => undefined);
  }

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg)] text-[var(--text)]">
      <aside
        className={`flex shrink-0 flex-col border-r border-[var(--line)] bg-[var(--sidebar)] transition-[width] duration-200 ${
          collapsed ? "w-14" : "w-52"
        }`}
      >
        <div className={`flex items-center ${collapsed ? "flex-col gap-3 px-2 py-4" : "justify-between px-3 py-4"}`}>
          {collapsed ? <div className="text-[13px] font-medium">B</div> : <div className="text-[13px] font-medium">BruceWare</div>}
          <button
            type="button"
            onClick={toggleSidebar}
            title={collapsed ? "展开侧栏" : "收起侧栏"}
            className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>
        <nav className={`min-h-0 flex-1 space-y-0.5 overflow-y-auto ${collapsed ? "px-1.5" : "px-2"}`}>
          <NavItem to="/" label="首页" icon={Home} end collapsed={collapsed} />
          {apps.length > 0 && !collapsed ? (
            <div className="px-2.5 pb-1 pt-3 text-[11px] text-[var(--muted)]">功能</div>
          ) : null}
          {apps.map((item) => (
            <DraggableNavItem
              key={item.id}
              to={moduleTo(item)}
              label={item.name}
              icon={MODULE_ICONS[item.id] || Globe}
              collapsed={collapsed}
              dragging={dragId === item.id}
              onDragStartItem={() => setDragId(item.id)}
              onDropItem={() => {
                if (dragId) moveIn(apps, dragId, item.id);
                setDragId(null);
              }}
              onDragEndItem={() => setDragId(null)}
            />
          ))}
          {commons.length > 0 && !collapsed ? (
            <div className="px-2.5 pb-1 pt-3 text-[11px] text-[var(--muted)]">公共</div>
          ) : null}
          {commons.map((item) => (
            <DraggableNavItem
              key={item.id}
              to={moduleTo(item)}
              label={item.name}
              icon={MODULE_ICONS[item.id] || CircleHelp}
              collapsed={collapsed}
              dragging={dragId === item.id}
              onDragStartItem={() => setDragId(item.id)}
              onDropItem={() => {
                if (dragId) moveIn(commons, dragId, item.id);
                setDragId(null);
              }}
              onDragEndItem={() => setDragId(null)}
            />
          ))}
        </nav>
        <div className={`border-t border-[var(--line)] ${collapsed ? "px-1.5 py-3" : "px-2 py-3"}`}>
          <NavItem to="/settings" label="设置" icon={Settings} collapsed={collapsed} />
          <div className={`mt-2 text-[12px] text-[var(--muted)] ${collapsed ? "text-center" : "px-2.5"}`} title={dbLabel}>
            <span>{connected === true ? "已连接" : connected === false ? "未连接" : "…"}</span>
            {collapsed ? null : <span> {dbLabel}</span>}
          </div>
        </div>
      </aside>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-[var(--bg)]">
        <Workspace />
      </main>
    </div>
  );
}
