import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from "pdfjs-dist/build/pdf.mjs";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState } from "react";

GlobalWorkerOptions.workerSrc = workerUrl;

/** 在页面里翻页看 PDF，不走浏览器下载 */
export function PdfPreview({ path, source = "local" }: { path: string; source?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pdfRef = useRef<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const ctrl = new AbortController();
    setReady(false);
    setError("");
    setPage(1);
    setTotal(0);
    pdfRef.current = null;

    (async () => {
      try {
        const res = await fetch(`/api/v1/files/raw?path=${encodeURIComponent(path)}&source=${encodeURIComponent(source)}`, { signal: ctrl.signal });
        if (!res.ok) throw new Error("读取失败");
        const data = new Uint8Array(await res.arrayBuffer());
        if (cancelled) return;
        const pdf = await getDocument({ data }).promise;
        if (cancelled) {
          void pdf.destroy();
          return;
        }
        pdfRef.current = pdf;
        setTotal(pdf.numPages);
        setReady(true);
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        setError("这个 PDF 预览不了，请用电脑打开");
      }
    })();

    return () => {
      cancelled = true;
      ctrl.abort();
      if (pdfRef.current) {
        void pdfRef.current.destroy();
        pdfRef.current = null;
      }
    };
  }, [path, source]);

  useEffect(() => {
    const pdf = pdfRef.current;
    const canvas = canvasRef.current;
    if (!ready || !pdf || !canvas || page < 1) return;
    let cancelled = false;
    pdf.getPage(page).then(async (pdfPage) => {
      if (cancelled) return;
      const box = canvas.parentElement;
      const width = Math.min(box?.clientWidth || 720, 860);
      const base = pdfPage.getViewport({ scale: 1 });
      const viewport = pdfPage.getViewport({ scale: width / base.width });
      const context = canvas.getContext("2d");
      if (!context) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await pdfPage.render({ canvasContext: context, viewport }).promise;
    });
    return () => {
      cancelled = true;
    };
  }, [page, ready]);

  if (error) {
    return <p className="text-[13px] leading-6 text-[var(--muted)]">{error}</p>;
  }

  return (
    <div>
      {total > 1 ? (
        <div className="mb-2 flex items-center gap-3 text-[13px] text-[var(--muted)]">
          <button type="button" disabled={page <= 1} className="disabled:opacity-50" onClick={() => setPage((n) => n - 1)}>
            上一页
          </button>
          <span>
            {page} / {total}
          </span>
          <button type="button" disabled={page >= total} className="disabled:opacity-50" onClick={() => setPage((n) => n + 1)}>
            下一页
          </button>
        </div>
      ) : null}
      {!ready ? <p className="text-[13px] text-[var(--muted)]">正在打开预览…</p> : null}
      <div className="max-h-[70vh] overflow-auto rounded-md bg-[var(--bg)]">
        <canvas ref={canvasRef} className="mx-auto block max-w-full" />
      </div>
    </div>
  );
}
