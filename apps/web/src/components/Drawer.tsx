import { useEffect, type ReactNode } from "react";

/** 右侧抽屉：放长表单和列表，不压住整页。点遮罩或 Esc 关闭。 */
export function Drawer({
  title,
  children,
  wide,
  onClose,
}: {
  title: string;
  children: ReactNode;
  wide?: boolean;
  onClose: () => void;
}) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      // 上面还压着确认框等弹窗时，先由弹窗处理。
      if (document.querySelector('[data-overlay="modal"]')) return;
      onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      data-overlay="drawer"
      className="fixed inset-0 z-[45] flex justify-end bg-[rgb(31_30_27_/_0.18)]"
      onClick={onClose}
    >
      <aside
        className={`flex h-full w-full flex-col border-l border-[var(--line)] bg-[var(--paper)] shadow-xl ${wide ? "max-w-3xl" : "max-w-[30rem]"}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--line)] px-4 py-2.5">
          <span className="text-[13px] font-medium">{title}</span>
          <button type="button" className="text-[13px] text-[var(--muted)] hover:text-[var(--text)]" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto px-4 py-3">{children}</div>
      </aside>
    </div>
  );
}
