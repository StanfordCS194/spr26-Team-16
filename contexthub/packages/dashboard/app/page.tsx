const metrics = [
  { label: "Workspaces", value: "4 active" },
  { label: "Captured chats", value: "128 total" },
  { label: "Pending pushes", value: "9 queued" },
  { label: "Extension tokens", value: "2 live" }
];

export default function OverviewPage() {
  return (
    <div className="grid" style={{ gap: 18 }}>
      <section className="card">
        <h1>ContextHub Frontend Demo</h1>
        <p className="muted">
          This dashboard is a visual-only mock for workspace management, token
          lifecycle, and context retrieval.
        </p>
      </section>

      <section className="grid grid-2">
        {metrics.map((metric) => (
          <article className="card" key={metric.label}>
            <p className="muted" style={{ marginBottom: 6 }}>
              {metric.label}
            </p>
            <h3 style={{ margin: 0 }}>{metric.value}</h3>
          </article>
        ))}
      </section>

      <section className="card">
        <div className="row">
          <h3 style={{ margin: 0 }}>Demo notes</h3>
          <span className="pill">No backend wiring</span>
        </div>
        <ul className="list" style={{ marginTop: 12 }}>
          <li>- Use tabs above to walk through the intended user flow.</li>
          <li>- The extension token shown in Tokens is a UI-only artifact.</li>
          <li>- Search results are static examples of pull-ready context.</li>
        </ul>
      </section>
    </div>
  );
}
