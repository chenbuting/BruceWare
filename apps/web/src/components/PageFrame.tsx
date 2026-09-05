import type { ReactNode } from "react";

/** 页面骨架。模块页可隐藏标题，避免顶部再多一块。fill 时铺满工作区高度。 */
export function PageFrame({
  title,
  desc,
  children,
  wide,
  hideHeader,
  fill,
}: {
  title?: string;
  desc?: string;
  children: ReactNode;
  wide?: boolean;
  hideHeader?: boolean;
  fill?: boolean;
}) {
  return (
    <div
      className={`flex min-h-0 flex-1 flex-col bg-[var(--bg)] px-8 py-6 ${fill ? "overflow-hidden" : "overflow-auto"}`}
    >
      <div className={`${wide ? "" : "max-w-[52rem]"} ${fill ? "flex h-full min-h-0 flex-1 flex-col" : ""}`}>
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
