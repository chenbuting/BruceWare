import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { fetchModules } from "@/api/client";
import type { ModuleInfo } from "@/api/types";

type ModulesContextValue = {
  modules: ModuleInfo[];
  reload: () => Promise<void>;
};

const ModulesContext = createContext<ModulesContextValue>({
  modules: [],
  reload: async () => undefined,
});

/** 模块列表共享，开关后侧栏立刻更新 */
export function ModulesProvider({ children }: { children: ReactNode }) {
  const [modules, setModules] = useState<ModuleInfo[]>([]);

  async function reload() {
    try {
      const data = await fetchModules();
      setModules(data.items);
    } catch {
      setModules([]);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  return <ModulesContext.Provider value={{ modules, reload }}>{children}</ModulesContext.Provider>;
}

export function useModules() {
  return useContext(ModulesContext);
}
