"use client";

import Header from "./Header";
import BottomNav from "./BottomNav";

export default function DashboardShell({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="w-screen h-screen flex flex-col overflow-hidden">
      <Header />
      <div className="flex-1 min-h-0 overflow-hidden px-5">{children}</div>
      <BottomNav />
    </div>
  );
}
