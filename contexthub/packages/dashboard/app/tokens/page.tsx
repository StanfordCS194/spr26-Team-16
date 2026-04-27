const tokens = [
  {
    label: "claude-main",
    created: "2026-04-18",
    lastUsed: "2026-04-21 14:08",
    status: "Active"
  },
  {
    label: "qa-review",
    created: "2026-04-16",
    lastUsed: "2026-04-20 09:12",
    status: "Active"
  },
  {
    label: "old-laptop",
    created: "2026-04-01",
    lastUsed: "2026-04-07 22:41",
    status: "Revoked"
  }
];

export default function TokensPage() {
  return (
    <div className="grid" style={{ gap: 16 }}>
      <section className="card">
        <div className="row">
          <h1 style={{ margin: 0 }}>Extension tokens</h1>
          <button className="button">Mint token</button>
        </div>
        <p className="muted">
          Long-lived token management mock for extension pairing.
        </p>
      </section>

      <section className="card">
        <ul className="list">
          {tokens.map((token) => (
            <li className="card" key={token.label}>
              <div className="row">
                <strong>{token.label}</strong>
                <span className="pill">{token.status}</span>
              </div>
              <p className="muted">Created: {token.created}</p>
              <p className="muted">Last used: {token.lastUsed}</p>
              <div className="row">
                <code>ctxh_{token.label.replace("-", "_")}_••••••••••</code>
                <button className="button secondary">Revoke</button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
