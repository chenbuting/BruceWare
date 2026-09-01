import { useState } from "react";
import { Link } from "react-router-dom";

import { setModuleEnabled, setModulePinned } from "@/api/client";
import { Card } from "@/components/Card";
import { useModules } from "@/modules/ModuleContext";

/** 公共模块页：开关功能，并控制是否固定到侧栏 */
export function ModulesPage() {
  const { modules, reload } = useModules();
  const [error, setError] = useState("");
  const apps = modules.filter((item) => item.kind === "app");

  function moduleTo(id: string, route: string) {
    return route.startsWith("/m/") ? route : `/m/${id}`;
  }

  return (
    <div>
      {error ? <p className="mb-4 text-[var(--err)]">{error}</p> : null}

      {apps.length === 0 ? (
        <Card className="px-5 py-4">
          <p className="text-[13px] leading-6 text-[var(--muted)]">
            还没有功能模块。以后放到 modules 里的功能会出现在这里。
          </p>
        </Card>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {apps.map((item) => (
            <li key={item.id}>
              <Card className="px-5 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    {item.enabled ? (
                      <Link to={moduleTo(item.id, item.route)} className="underline">
                        {item.name}
                      </Link>
                    ) : (
                      <span>{item.name}</span>
                    )}
                    <p className="mt-2 text-[13px] leading-6 text-[var(--muted)]">{item.description || "暂无说明"}</p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-4 text-[13px]">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={item.enabled}
                      onChange={(event) => {
                        setModuleEnabled(item.id, event.target.checked)
                          .then(() => reload())
                          .catch((err: Error) => setError(err.message));
                      }}
                    />
                    {item.enabled ? "已开启" : "已关闭"}
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={item.pinned}
                      onChange={(event) => {
                        setModulePinned(item.id, event.target.checked)
                          .then(() => reload())
                          .catch((err: Error) => setError(err.message));
                      }}
                    />
                    {item.pinned ? "已固定到侧栏" : "未固定到侧栏"}
                  </label>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
