import { useEffect, useState } from "react";

import {
  createDriveOrder,
  deleteDriveProduct,
  fetchDriveOrders,
  fetchDriveProducts,
  testPayDriveOrder,
  updateDriveProduct,
} from "@/api/client";
import type { DriveOrder, DriveProduct } from "@/api/types";
import { Card } from "@/components/Card";
import { ConfirmModal } from "@/components/Modal";

const inputClass = "border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 text-[13px]";
const btnClass = "border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px] disabled:opacity-50";

function buyerUrl(path: string) {
  return `${window.location.origin}${path}`;
}

async function copyText(text: string) {
  await navigator.clipboard.writeText(text);
}

/** 货品和订单：先测试付款，付完再给百度分享链接。 */
export function DriveShopPanel({
  busy,
  onBusy,
  onHint,
  onError,
}: {
  busy: boolean;
  onBusy: (work: () => Promise<void>, hint?: string) => void;
  onHint: (text: string) => void;
  onError: (text: string) => void;
}) {
  const [products, setProducts] = useState<DriveProduct[]>([]);
  const [orders, setOrders] = useState<DriveOrder[]>([]);
  const [askId, setAskId] = useState<number | null>(null);
  const [edit, setEdit] = useState<DriveProduct | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editPrice, setEditPrice] = useState("");

  async function reload() {
    const [nextProducts, nextOrders] = await Promise.all([fetchDriveProducts(), fetchDriveOrders()]);
    setProducts(nextProducts.items);
    setOrders(nextOrders.items);
  }

  useEffect(() => {
    reload().catch((err: Error) => onError(err.message));
  }, []);

  return (
    <>
      <Card className="mb-4 px-5 py-4" title="货品">
        <p className="mb-3 text-[13px] leading-6 text-[var(--muted)]">
          在文件列表里点文件夹的「设为货品」。先私下把付款链接发给对方，点「测试付款」后会出现分享链接。微信支付宝以后再接。
        </p>
        {!products.length ? (
          <p className="text-[13px] text-[var(--muted)]">还没有货品。</p>
        ) : (
          <div className="divide-y divide-[var(--line)] border border-[var(--line)]">
            {products.map((item) => (
              <div key={item.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="break-all text-[13px]">{item.title}</div>
                  <div className="text-[12px] text-[var(--muted)]">
                    ￥{item.price} · {item.path}
                  </div>
                </div>
                <button
                  type="button"
                  className={btnClass}
                  disabled={busy}
                  onClick={() =>
                    onBusy(async () => {
                      const order = await createDriveOrder(item.id);
                      await copyText(buyerUrl(order.buyer_path));
                      await reload();
                    }, "已生成链接并复制")
                  }
                >
                  生成付款链接
                </button>
                <button
                  type="button"
                  className="text-[12px] text-[var(--muted)]"
                  disabled={busy}
                  onClick={() => {
                    setEdit(item);
                    setEditTitle(item.title);
                    setEditPrice(item.price);
                  }}
                >
                  改价格
                </button>
                <button type="button" className="text-[12px] text-[var(--muted)]" disabled={busy} onClick={() => setAskId(item.id)}>
                  删除
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="px-5 py-4" title="订单">
        {!orders.length ? (
          <p className="text-[13px] text-[var(--muted)]">还没有订单。</p>
        ) : (
          <div className="divide-y divide-[var(--line)] border border-[var(--line)]">
            {orders.map((item) => (
              <div key={item.id} className="px-3 py-2">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="break-all text-[13px]">{item.title}</div>
                    <div className="text-[12px] text-[var(--muted)]">
                      ￥{item.price} · {item.status === "paid" ? "已付款（测试）" : "待付款"}
                    </div>
                  </div>
                  <button
                    type="button"
                    className={btnClass}
                    disabled={busy}
                    onClick={() =>
                      onBusy(async () => {
                        await copyText(buyerUrl(item.buyer_path));
                      }, "已复制付款链接")
                    }
                  >
                    复制链接
                  </button>
                  {item.status !== "paid" ? (
                    <button
                      type="button"
                      className={btnClass}
                      disabled={busy}
                      onClick={() =>
                        onBusy(async () => {
                          await testPayDriveOrder(item.id);
                          await reload();
                        }, "已测试付款")
                      }
                    >
                      测试付款
                    </button>
                  ) : null}
                </div>
                {item.status === "paid" && item.share_url ? (
                  <p className="mt-1 break-all text-[12px] leading-5 text-[var(--muted)]">
                    分享：{item.share_url}　提取码：{item.share_pwd}
                    <button
                      type="button"
                      className="ml-2 text-[var(--text)]"
                      onClick={() =>
                        void copyText(`链接：${item.share_url}\n提取码：${item.share_pwd}`).then(() => onHint("已复制分享信息"))
                      }
                    >
                      复制
                    </button>
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </Card>

      {edit ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgb(31_30_27_/_0.28)] px-4" onClick={() => setEdit(null)}>
          <div className="card w-full max-w-[28rem] px-5 py-4" onClick={(event) => event.stopPropagation()}>
            <div className="mb-3 text-[13px] font-medium">改货品</div>
            <input className={`${inputClass} mb-2 w-full`} value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
            <input className={`${inputClass} mb-3 w-full`} value={editPrice} onChange={(e) => setEditPrice(e.target.value)} placeholder="价格，比如 9.9" />
            <button
              type="button"
              className={btnClass}
              disabled={busy}
              onClick={() =>
                onBusy(async () => {
                  await updateDriveProduct(edit.id, { title: editTitle, price: editPrice });
                  setEdit(null);
                  await reload();
                }, "已保存")
              }
            >
              保存
            </button>
          </div>
        </div>
      ) : null}

      {askId !== null ? (
        <ConfirmModal
          title="删除这个货品？"
          message="对应的测试订单也会删掉。网盘里的文件夹不会动。"
          onClose={() => setAskId(null)}
          onConfirm={() => {
            if (askId === null) return;
            onBusy(async () => {
              await deleteDriveProduct(askId);
              setAskId(null);
              await reload();
            }, "已删除货品");
          }}
        />
      ) : null}
    </>
  );
}
