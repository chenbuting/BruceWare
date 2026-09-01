import { Card } from "@/components/Card";
import { PageFrame } from "@/components/PageFrame";

const ITEMS = [
  { term: "功能", desc: "侧栏「功能」里是已开启并且固定的模块。" },
  { term: "公共", desc: "「帮助」看说明。「模块」开关功能，并固定或取消固定到侧栏。" },
  { term: "设置", desc: "设置单独放在侧栏底部，只管数据源。" },
];

/** 首页：几块说明卡片 */
export function HomePage() {
  return (
    <PageFrame title="首页" desc="同一窗口里用。功能可开关、可固定，公共入口和设置分开放。">
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
