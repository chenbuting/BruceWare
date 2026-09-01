import type { ComponentType } from "react";

import { HelpPage } from "@/pages/HelpPage";
import { ModulesPage } from "@/pages/ModulesPage";
import { PortalPage } from "@/pages/PortalPage";

/** 模块页面注册表：侧栏点开后嵌进工作区，不另开窗口 */
export type ModulePageEntry = {
  title: string;
  desc?: string;
  wide?: boolean;
  page: ComponentType;
};

export const MODULE_PAGES: Record<string, ModulePageEntry> = {
  help: {
    title: "帮助",
    desc: "底座、公共模块和功能模块怎么用。",
    wide: true,
    page: HelpPage,
  },
  hub: {
    title: "模块",
    desc: "开启或关闭功能，并决定要不要固定在侧栏。",
    wide: true,
    page: ModulesPage,
  },
  portal: {
    title: "网站入口",
    desc: "收藏常用网站，点名称在新标签打开。",
    wide: true,
    page: PortalPage,
  },
};

export function getModulePage(id: string): ModulePageEntry | undefined {
  return MODULE_PAGES[id];
}
