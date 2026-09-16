const inputClass = "border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 text-[13px]";

const OPTIONS = [
  { value: 1, label: "1 天" },
  { value: 7, label: "7 天" },
  { value: 30, label: "30 天" },
  { value: 0, label: "永久" },
];

/** 只保留百度分享认的档：1 / 7 / 30 / 永久。旧的自定义天数会靠到最近一档。 */
export function normalizeDrivePeriod(days: number): number {
  if (days === 0 || days === 1 || days === 7 || days === 30) return days;
  if (days <= 1) return 1;
  if (days <= 7) return 7;
  return 30;
}

/** 设货品、改货品共用的有效期选择。 */
export function DrivePeriodField({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="mb-3 flex items-center gap-2 text-[13px] text-[var(--muted)]">
      分享有效期
      <select className={inputClass} value={normalizeDrivePeriod(value)} onChange={(e) => onChange(Number(e.target.value))}>
        {OPTIONS.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    </label>
  );
}
