import type { ReactNode } from "react";

/** 克制的内容卡片：细边、小圆角，不当装饰块 */
export function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`.trim()}>
      {title ? <div className="card-title">{title}</div> : null}
      {children}
    </section>
  );
}
