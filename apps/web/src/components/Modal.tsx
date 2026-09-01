import { useEffect, type ReactNode } from "react";

/** 居中弹框：点遮罩或关闭可关掉 */
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgb(31_30_27_/_0.28)] px-4" onClick={onClose}>
      <div className="card w-full max-w-[28rem] px-5 py-4" onClick={(event) => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between gap-4">
          <div className="text-[13px] font-medium">{title}</div>
          <button type="button" className="text-[13px] text-[var(--muted)] hover:text-[var(--text)]" onClick={onClose}>
            关闭
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** 删除等需要确认的提示 */
export function ConfirmModal({
  title,
  message,
  confirmLabel = "删除",
  busy,
  onConfirm,
  onClose,
}: {
  title: string;
  message: string;
  confirmLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal title={title} onClose={onClose}>
      <p className="text-[13px] leading-6 text-[var(--muted)]">{message}</p>
      <div className="mt-4 flex gap-3">
        <button
          type="button"
          className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50"
          disabled={busy}
          onClick={onConfirm}
        >
          {confirmLabel}
        </button>
        <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={onClose}>
          取消
        </button>
      </div>
    </Modal>
  );
}
