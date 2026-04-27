const results = [
  {
    title: "Claude context injection checklist",
    workspace: "Product RFCs",
    snippet:
      "Ensure push list item has summary, source URL, and normalized markdown before promoting to retrieval index."
  },
  {
    title: "Prompt quality rubric for architecture Q&A",
    workspace: "Spring Experiments",
    snippet:
      "Use byte-identical renderer outputs so what users preview is exactly what the extension injects."
  },
  {
    title: "Token revocation fallback behavior",
    workspace: "Claude QA Logs",
    snippet:
      "Background worker should display token status warning and disable push actions until renewed."
  }
];

export default function SearchPage() {
  return (
    <div className="grid" style={{ gap: 16 }}>
      <section className="card">
        <h1 style={{ marginTop: 0 }}>Search and pull</h1>
        <p className="muted">
          Secondary retrieval UI mock that mirrors extension pull experience.
        </p>
        <div className="row">
          <input
            style={{
              width: "100%",
              borderRadius: 8,
              border: "1px solid #355087",
              background: "#0f1830",
              color: "#edf2ff",
              padding: "10px 12px"
            }}
            value="renderer output consistency"
            readOnly
          />
          <button className="button">Search</button>
        </div>
      </section>

      <section className="grid">
        {results.map((result) => (
          <article className="card" key={result.title}>
            <div className="row">
              <h3 style={{ margin: 0 }}>{result.title}</h3>
              <span className="pill">{result.workspace}</span>
            </div>
            <p className="muted">{result.snippet}</p>
            <button className="button secondary">Pull into draft</button>
          </article>
        ))}
      </section>
    </div>
  );
}
