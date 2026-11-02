import { useState } from "react";
import { api, config } from "../api";
import { PageHeader } from "../ui";

export default function Settings() {
  const [token, setToken] = useState(config.token);
  const [base, setBase] = useState(config.base);
  const [status, setStatus] = useState<string>();

  async function save() {
    config.token = token;
    config.base = base;
    try {
      await api.system();
      setStatus("Saved. Connected to the engine.");
    } catch (e) {
      setStatus(`Saved, but the engine did not accept the connection: ${e instanceof Error ? e.message : e}`);
    }
  }

  return (
    <div className="max-w-2xl">
      <PageHeader title="Settings" subtitle="Connection settings are stored in this browser only." />
      <div className="card space-y-4">
        <div>
          <label className="label">Engine URL</label>
          <input className="input" value={base} onChange={(e) => setBase(e.target.value)} placeholder="Leave empty when the UI is served by the engine" />
        </div>
        <div>
          <label className="label">Access token</label>
          <input className="input" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Only needed if ENGINE_ACCESS_TOKEN is set" />
        </div>
        <button className="btn-primary" onClick={save}>Save</button>
        {status && <p className="text-sm text-sand-300">{status}</p>}
      </div>
      <div className="card mt-6 space-y-2 text-sm text-sand-300">
        <div className="font-display text-lg text-sand-100">API keys</div>
        <p>API keys are never stored in the browser. Put them in <code className="text-mane-300">backend/.env</code> on the computer running the engine:</p>
        <pre className="overflow-x-auto rounded-xl bg-ink-850 p-3 text-xs text-sand-200">GEMINI_API_KEY=your-free-key-from-aistudio.google.com</pre>
        <p>Then restart the engine. The Free providers page shows whether each provider is ready.</p>
      </div>
    </div>
  );
}
