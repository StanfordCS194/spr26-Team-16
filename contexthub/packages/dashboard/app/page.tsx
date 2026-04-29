import { ApiConfig } from "@/components/api-config";

export default function OverviewPage() {
  return (
    <div className="grid" style={{ gap: 18 }}>
      <section className="card">
        <h1>ContextHub Frontend (Connected)</h1>
        <p className="muted">
          This dashboard now talks to the backend routes you have after Modules 4–8:
          <code style={{ marginLeft: 8 }}>/v1/me</code>, <code>/v1/tokens</code>, and
          <code style={{ marginLeft: 8 }}>/v1/workspaces/&lt;id&gt;/pushes</code>.
        </p>
      </section>

      <ApiConfig />

      <section className="card">
        <div className="row">
          <h3 style={{ margin: 0 }}>What’s live right now</h3>
          <span className="pill">Modules 4–12 (baseline)</span>
        </div>
        <ul className="list" style={{ marginTop: 12 }}>
          <li>- Token mint/list/revoke flows on the Tokens tab.</li>
          <li>- Push ingestion + push status detail available for extension/dashboard polling.</li>
          <li>- Search tab uses `/v1/search` with pull payload generation via `/v1/pulls`.</li>
        </ul>
      </section>
    </div>
  );
}
