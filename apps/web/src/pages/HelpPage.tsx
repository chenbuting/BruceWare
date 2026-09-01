import { Card } from "@/components/Card";
import { useModules } from "@/modules/ModuleContext";

/** 公共说明：只讲怎么用 */
export function HelpPage() {
  const { modules } = useModules();
  const apps = modules.filter((item) => item.kind === "app");
  const commons = modules.filter((item) => item.kind === "common");

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card title="底座" className="px-5 py-4">
        <p className="text-[13px] leading-6 text-[var(--muted)]">
          左边是菜单，右边是同一块工作区。点功能会嵌进来，上面用标签切换，不另开窗口。
        </p>
      </Card>
      <Card title="设置" className="px-5 py-4">
        <p className="text-[13px] leading-6 text-[var(--muted)]">
          设置在侧栏最下面，单独放，管数据源和 AI。模块开关不在这里。
        </p>
      </Card>
      <Card title="功能模块" className="px-5 py-4">
        <p className="text-[13px] leading-6 text-[var(--muted)]">
          去公共里的「模块」可以开启/关闭，也可以固定或取消固定到侧栏。关掉的不能用；没固定的不出现在侧栏，但可从「模块」点进去。
        </p>
        {apps.length === 0 ? (
          <p className="mt-3 text-[13px] text-[var(--muted)]">现在还没有功能模块。</p>
        ) : (
          <ul className="mt-3 space-y-2 text-[13px]">
            {apps.map((item) => (
              <li key={item.id}>
                {item.name}
                <span className="ml-2 text-[var(--muted)]">
                  {item.enabled ? "已开启" : "已关闭"} · {item.pinned ? "已固定" : "未固定"} ·{" "}
                  {item.description || "暂无说明"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="公共模块" className="px-5 py-4">
        <p className="text-[13px] leading-6 text-[var(--muted)]">
          帮助、模块这类公共入口始终在侧栏，不能关，也不能取消固定。
        </p>
        <ul className="mt-3 space-y-2 text-[13px]">
          {commons.map((item) => (
            <li key={item.id}>
              {item.name}
              <span className="ml-2 text-[var(--muted)]">{item.description || "暂无说明"}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
