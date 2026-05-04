"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/", label: "Overview" },
  { href: "/workspaces", label: "Workspaces" },
  { href: "/tokens", label: "Tokens" },
  { href: "/search", label: "Search" }
];

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="top-nav">
      <div className="brand">ContextHub Dashboard</div>
      <nav className="links">
        {navItems.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              className={`link ${active ? "link-active" : ""}`}
              key={item.href}
              href={item.href}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
