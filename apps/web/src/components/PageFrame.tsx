import type { ReactNode } from "react";

/** 页面骨架。模块页可隐藏标题，避免顶部再多一块。 */
export function PageFrame({
  title,
  desc,
  children,
  wide,
  hideHeader,
}: {
  title?: string;
  desc?: string;
  children: ReactNode;
  wide?: boolean;
  hideHeader?: boolean;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-auto bg-[var(--bg)] px-8 py-6">
      <div className={wide ? "" : "max-w-[52rem]"}>
        {!hideHeader && title ? (
          <div className="mb-5">
            <h1>{title}</h1>
            {desc ? <p className="mt-1.5 max-w-[36rem] text-[13px] leading-6 text-[var(--muted)]">{desc}</p> : null}
          </div>
        ) : null}
        {children}
      </div>
    </div>
  );
}
