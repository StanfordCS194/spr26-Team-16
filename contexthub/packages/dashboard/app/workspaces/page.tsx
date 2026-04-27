const workspaces = [
  { name: "Product RFCs", owner: "hou@team16.dev", pushes: 5 },
  { name: "Spring Experiments", owner: "sam@team16.dev", pushes: 2 },
  { name: "Claude QA Logs", owner: "alex@team16.dev", pushes: 1 }
];

const pushList = [
  "Claude architecture review - pending classification",
  "Prompt renderer edge-case runbook - awaiting tags",
  "Migration notes for extension schema v0 - queued"
];

export default function WorkspacesPage() {
  return (
    <div className="grid" style={{ gap: 16 }}>
      <section className="card">
        <div className="row">
          <h1 style={{ margin: 0 }}>Workspaces</h1>
          <button className="button">New workspace</button>
        </div>
        <p className="muted">
          Visual mock of workspace creation and push list triage.
        </p>
      </section>

      <section className="grid grid-2">
        {workspaces.map((workspace) => (
          <article className="card" key={workspace.name}>
            <h3 style={{ marginTop: 0 }}>{workspace.name}</h3>
            <p className="muted">{workspace.owner}</p>
            <p>
              <span className="pill">{workspace.pushes} pending pushes</span>
            </p>
          </article>
        ))}
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Push list</h3>
        <ul className="list">
          {pushList.map((item) => (
            <li className="row" key={item}>
              <span>{item}</span>
              <button className="button secondary">Inspect</button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
