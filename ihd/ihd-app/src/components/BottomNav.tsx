"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", icon: "🏠", label: "Home" },
  { href: "/calendar", icon: "📅", label: "Calendar" },
  { href: "/meals", icon: "🍽", label: "Meals" },
  { href: "/kids", icon: "📚", label: "Kids" },
  { href: "/media", icon: "🎬", label: "Media" },
  { href: "/control", icon: "💡", label: "Control" },
  { href: "/chris", icon: "\u{1F9F1}", label: "HB" },
];

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <div className="flex border-t border-border bg-surface shrink-0">
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex-1 flex flex-col items-center gap-0.5 py-2.5 px-2 border-t-2 text-sm font-medium transition-colors no-underline ${
              active
                ? "border-accent text-accent"
                : "border-transparent text-text-dim hover:text-text-mid"
            }`}
          >
            <span className="text-xl">{item.icon}</span>
            <span>{item.label}</span>
          </Link>
        );
      })}
    </div>
  );
}
