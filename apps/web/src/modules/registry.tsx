import type { ComponentType } from "react";

import { FilesPage } from "@/pages/FilesPage";
import { HelpPage } from "@/pages/HelpPage";
import { ModulesPage } from "@/pages/ModulesPage";
import { PortalPage } from "@/pages/PortalPage";
import { ResumePage } from "@/pages/ResumePage";
import { WardrobePage } from "@/pages/WardrobePage";

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
  resume: {
    title: "简历",
    desc: "保存简历，用 AI 分析和打字模拟面试。先在设置里配好 AI。",
    wide: true,
    page: ResumePage,
  },
  wardrobe: {
    title: "衣橱",
    desc: "上传衣服照片，AI 抠单件、试穿和搭配。先在设置里配好 AI。",
    wide: true,
    page: WardrobePage,
  },
  files: {
    title: "文件",
    desc: "管理电脑上指定文件夹里的文件。先在设置里指定根目录。",
    wide: true,
    page: FilesPage,
  },
};

export function getModulePage(id: string): ModulePageEntry | undefined {
  return MODULE_PAGES[id];
}
