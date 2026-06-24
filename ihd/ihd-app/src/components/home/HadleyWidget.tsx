export default function HadleyWidget() {
  const stats = [
    { label: "Orders", value: "7", color: "var(--green)" },
    { label: "Revenue", value: "£142.50", color: "var(--accent)" },
  ];

  const platforms = [
    { name: "eBay", count: 4 },
    { name: "Amazon", count: 2 },
    { name: "BrickLink", count: 1 },
  ];

  return (
    <div className="bg-surface border border-border rounded-2xl p-4 shadow-sm">
      <div className="text-xs font-bold uppercase tracking-widest text-text-mid mb-2.5">
        Hadley Bricks — Today
      </div>
      <div className="grid grid-cols-2 gap-2.5 mb-2.5">
        {stats.map((s) => (
          <div
            key={s.label}
            className="text-center py-2.5 px-2 bg-surface-alt rounded-xl"
          >
            <div className="text-xl font-bold" style={{ color: s.color }}>
              {s.value}
            </div>
            <div className="text-xs text-text-mid mt-0.5 uppercase tracking-wide">
              {s.label}
            </div>
          </div>
        ))}
      </div>
      <div className="flex gap-1.5 flex-wrap">
        {platforms.map((p) => (
          <span
            key={p.name}
            className="text-sm text-text-mid bg-surface-alt px-2 py-0.5 rounded-lg"
          >
            {p.name} {p.count}
          </span>
        ))}
        <span className="text-sm text-rose bg-rose/10 px-2 py-0.5 rounded-lg">
          2 offers pending
        </span>
      </div>
    </div>
  );
}
