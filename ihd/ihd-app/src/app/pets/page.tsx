import DashboardShell from "@/components/DashboardShell";

export default function PetsPage() {
  return (
    <DashboardShell>
      <div style={{ margin: "-12px", height: "calc(100vh - 64px)" }}>
        <iframe
          src="/pets-standalone.html"
          style={{ width: "100%", height: "100%", border: "none" }}
          title="Pet Playground"
          allow="autoplay"
        />
      </div>
    </DashboardShell>
  );
}
