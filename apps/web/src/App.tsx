import { ModulesProvider } from "@/modules/ModuleContext";
import { AppLayout } from "@/layouts/AppLayout";

/** 单窗口壳：所有页面都嵌在同一工作区 */
export function App() {
  return (
    <ModulesProvider>
      <AppLayout />
    </ModulesProvider>
  );
}
