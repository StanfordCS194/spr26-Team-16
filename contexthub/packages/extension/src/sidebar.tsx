import { createRoot } from "react-dom/client";
import { useState } from "react";
import "./sidebar.css";

function SidebarApp() {
  const [tokenState, setTokenState] = useState("demo-active");
  const [lastAction, setLastAction] = useState("none");

  return (
    <div className="shell">
      <header className="header">
        <h1>ContextHub Extension Demo</h1>
        <p>Claude.ai adapter visual mock (no backend calls)</p>
      </header>

      <div className="body">
        <section className="card">
          <div className="row">
            <h2>Token status</h2>
            <span className="pill">{tokenState}</span>
          </div>
          <p className="muted">Linked to workspace: Product RFCs</p>
          <div className="row">
            <button className="btn" onClick={() => setTokenState("demo-active")}>
              Refresh token
            </button>
            <button className="btn secondary" onClick={() => setTokenState("revoked")}>
              Revoke (mock)
            </button>
          </div>
        </section>

        <section className="card">
          <h2>Captured conversation</h2>
          <p className="muted">
            Auto-scroll + scrape state: 42 messages parsed, 3 chunks pending.
          </p>
          <button
            className="btn"
            onClick={() => {
              setLastAction("queued push");
              chrome.runtime.sendMessage({ type: "ctxh:mock:push" });
            }}
          >
            Push to ContextHub
          </button>
        </section>

        <section className="card">
          <h2>Pull context</h2>
          <ul className="list">
            <li>Renderer byte identity checklist</li>
            <li>Claude adapter error-handling notes</li>
            <li>Workspace tagging strategy</li>
          </ul>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn secondary" onClick={() => setLastAction("pulled 3 blocks")}>
              Pull selected
            </button>
            <span className="muted">Last action: {lastAction}</span>
          </div>
        </section>
      </div>
    </div>
  );
}

const mountNode = document.getElementById("root");
if (!mountNode) {
  throw new Error("Sidebar root mount node is missing.");
}

createRoot(mountNode).render(<SidebarApp />);
