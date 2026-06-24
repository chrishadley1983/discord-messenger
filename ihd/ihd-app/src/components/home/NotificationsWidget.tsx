export default function NotificationsWidget() {
  const notifications = [
    { text: "School pick-up in 30 mins", time: "14:50", type: "reminder" },
    { text: "Amazon parcel delivered", time: "11:23", type: "delivery" },
    { text: "Spelling test tomorrow — Max", time: "09:00", type: "school" },
  ];

  return (
    <div className="bg-surface border border-border rounded-2xl p-4 shadow-sm">
      <div className="text-xs font-bold uppercase tracking-widest text-text-mid mb-2.5">
        Peter Notifications
      </div>
      <div className="flex flex-col gap-2">
        {notifications.map((n, i) => (
          <div
            key={i}
            className="flex items-start gap-2.5 p-2 bg-surface-alt rounded-lg"
          >
            <span className="text-sm mt-0.5">
              {n.type === "reminder"
                ? "🔔"
                : n.type === "delivery"
                ? "📦"
                : "📚"}
            </span>
            <div className="flex-1">
              <div className="text-xs font-medium">{n.text}</div>
              <div className="text-xs text-text-dim mt-0.5">{n.time}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
