import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { fetchDriveBuy, testPayDriveBuy } from "@/api/client";
import type { DriveOrder } from "@/api/types";
import { Card } from "@/components/Card";

const btnClass = "border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px] disabled:opacity-50";

/** 买家打开的付款/取货页。现在只能测试付款。 */
export function DriveBuyPage() {
  const location = useLocation();
  const token = location.pathname.split("/buy/")[1] || "";
  const [order, setOrder] = useState<DriveOrder | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    fetchDriveBuy(token)
      .then(setOrder)
      .catch((err: Error) => setError(err.message));
  }, [token]);

  async function pay() {
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      setOrder(await testPayDriveBuy(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "付款失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-start justify-center bg-[var(--bg)] px-4 py-16 text-[var(--text)]">
      <Card className="w-full max-w-lg px-5 py-5">
        {error ? <p className="mb-3 text-[13px] text-[var(--err)]">{error}</p> : null}
        {!order && !error ? <p className="text-[13px] text-[var(--muted)]">正在打开…</p> : null}
        {order ? (
          <>
            <h1 className="text-[18px] font-medium">{order.title}</h1>
            <p className="mt-2 text-[13px] text-[var(--muted)]">价格 ￥{order.price}</p>
            {order.status === "paid" && order.share_url ? (
              <div className="mt-4 text-[13px] leading-6">
                <p>已付款。用百度网盘打开下面链接，可以下载，也可以保存到自己的网盘。</p>
                <p className="mt-3 break-all">
                  链接：
                  <a className="underline" href={order.share_url} target="_blank" rel="noreferrer">
                    {order.share_url}
                  </a>
                </p>
                <p>提取码：{order.share_pwd}</p>
              </div>
            ) : (
              <div className="mt-4">
                <p className="text-[13px] leading-6 text-[var(--muted)]">
                  现在还没接微信支付宝，这是测试付款。点一下等于假装已经收到钱，然后生成分享链接。
                </p>
                <button type="button" className={`${btnClass} mt-3`} disabled={busy} onClick={() => void pay()}>
                  {busy ? "正在生成…" : "测试付款"}
                </button>
              </div>
            )}
          </>
        ) : null}
      </Card>
    </div>
  );
}
