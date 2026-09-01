import type { ReactNode } from "react";

/** 统一页面骨架：顶栏标题 + 下方内容 */
export function PageFrame({
  title,
  desc,
  children,
  wide,
}: {
  title: string;
  desc?: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="shrink-0 border-b border-[var(--line)] bg-[var(--paper)] px-8 py-5">
        <h1>{title}</h1>
        {desc ? <p className="mt-1.5 max-w-[36rem] text-[13px] leading-6 text-[var(--muted)]">{desc}</p> : null}
      </header>
      <div className={`min-h-0 flex-1 overflow-auto bg-[var(--bg)] px-8 py-6 ${wide ? "" : ""}`}>
        <div className={wide ? "" : "max-w-[52rem]"}>{children}</div>
      </div>
    </div>
  );
}
