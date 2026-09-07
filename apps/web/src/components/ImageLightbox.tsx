import { useEffect } from "react";

export type LightboxItem = { src: string; alt?: string };

/** 点图后的放大层，Esc 或点空白关闭，不关掉底下的预览框。 */
export function ImageLightbox({
  items,
  index,
  onClose,
  onIndex,
}: {
  items: LightboxItem[];
  index: number;
  onClose: () => void;
  onIndex?: (next: number) => void;
}) {
  const item = items[index];

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopImmediatePropagation();
        onClose();
        return;
      }
      if (!onIndex || items.length < 2) return;
      if (event.key === "ArrowLeft" && index > 0) onIndex(index - 1);
      if (event.key === "ArrowRight" && index < items.length - 1) onIndex(index + 1);
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [index, items.length, onClose, onIndex]);

  if (!item) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-[rgb(31_30_27_/_0.72)] px-4" onClick={onClose}>
      <div className="relative max-h-[92vh] max-w-[92vw]" onClick={(event) => event.stopPropagation()}>
        <button type="button" className="absolute -top-1 right-0 text-[13px] text-white" onClick={onClose}>
          关闭
        </button>
        <img src={item.src} alt={item.alt || ""} className="max-h-[80vh] max-w-[92vw] object-contain" />
        {item.alt ? <p className="mt-2 text-center text-[13px] text-white">{item.alt}</p> : null}
        {items.length > 1 && onIndex ? (
          <div className="mt-3 flex items-center justify-center gap-3 text-[13px] text-white">
            <button type="button" className="disabled:opacity-40" disabled={index <= 0} onClick={() => onIndex(index - 1)}>
              上一张
            </button>
            <span>
              {index + 1} / {items.length}
            </span>
            <button type="button" className="disabled:opacity-40" disabled={index >= items.length - 1} onClick={() => onIndex(index + 1)}>
              下一张
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
