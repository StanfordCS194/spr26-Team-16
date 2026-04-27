import "./globals.css";
import type { ReactNode } from "react";
import { TopNav } from "@/components/top-nav";

export const metadata = {
  title: "ContextHub Dashboard Demo",
  description: "Visual-only dashboard mock for ContextHub."
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="layout">
          <TopNav />
          <main className="content">{children}</main>
        </div>
      </body>
    </html>
  );
}
