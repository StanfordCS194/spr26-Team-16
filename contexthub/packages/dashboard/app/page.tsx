import { ApiConfig } from "@/components/api-config";

export default function OverviewPage() {
  return (
    <div className="grid" style={{ gap: 18 }}>
      <section className="card">
        <h1>ContextHub Control Center</h1>
        <p className="muted">
          Manage authentication, token lifecycle, push ingestion, and context retrieval from a single workspace-aware dashboard.
          Key APIs:
          <code style={{ marginLeft: 8 }}>/v1/me</code>, <code>/v1/tokens</code>, and
          <code style={{ marginLeft: 8 }}>/v1/workspaces/&lt;id&gt;/pushes</code>.
        </p>
      </section>

      <ApiConfig />

      <section className="card">
        <div className="row">
          <h3 style={{ margin: 0 }}>Platform capabilities</h3>
          <span className="pill">Online</span>
        </div>
        <ul className="list" style={{ marginTop: 12 }}>
          <li>- Token management with mint, list, and revoke operations.</li>
          <li>- Push ingestion plus status visibility for dashboard and extension flows.</li>
          <li>- Hybrid search and pull payload assembly for context reuse.</li>
        </ul>
      </section>
    </div>
  );
}
