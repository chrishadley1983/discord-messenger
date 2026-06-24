import DashboardShell from "@/components/DashboardShell";

export default function ControlPage() {
  return (
    <DashboardShell>
      <div className="flex items-center justify-center h-full">
        <div className="bg-surface border border-border rounded-2xl p-8 shadow-sm text-center">
          <span className="text-4xl mb-3 block">💡</span>
          <div className="text-lg font-semibold">Control</div>
          <div className="text-sm text-text-mid mt-1">Coming soon</div>
        </div>
      </div>
    </DashboardShell>
  );
}
