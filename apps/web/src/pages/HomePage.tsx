import { Card } from "@/components/Card";
import { PageFrame } from "@/components/PageFrame";

const ITEMS = [
  { term: "功能", desc: "侧栏「功能」里是已开启并且固定的模块。" },
  { term: "公共", desc: "「帮助」看说明。「模块」开关功能，并固定或取消固定到侧栏。" },
  { term: "设置", desc: "设置单独放在侧栏底部，管数据源和 AI。" },
];

/** 首页：几块说明卡片 */
export function HomePage() {
  return (
    <PageFrame hideHeader>
      <div className="grid gap-4 md:grid-cols-3">
        {ITEMS.map((item) => (
          <Card key={item.term} title={item.term} className="px-5 py-4">
            <p className="text-[13px] leading-6 text-[var(--muted)]">{item.desc}</p>
          </Card>
        ))}
      </div>
    </PageFrame>
  );
}
