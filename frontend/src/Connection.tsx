import { Component, useEffect, useState, type ReactNode } from "react";
import { api, config, isHostedUi } from "./api";

/** Shows setup help instead of a broken page when the engine can't be reached. */
export function ConnectionGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"checking" | "ok" | "down" | "auth">("checking");
  const [base, setBase] = useState(config.base);
  const [token, setToken] = useState(config.token);

  const check = async () => {
    setState("checking");
    try {
      await api.system();
      setState("ok");
    } catch (e) {
      setState(e && typeof e === "object" && "status" in e && (e as { status: number }).status === 401 ? "auth" : "down");
    }
  };
  useEffect(() => {
    check();
  }, []);

  if (state === "ok") return <>{children}</>;
  if (state === "checking") return <div className="grid min-h-screen place-items-center text-sand-400">Connecting to the engine…</div>;

  const hosted = isHostedUi();
  return (
    <div className="mx-auto max-w-2xl p-6 py-16">
      <h1 className="font-display text-3xl">{state === "auth" ? "Access token needed" : "Engine not connected"}</h1>
      {state === "down" ? (
        <div className="mt-4 space-y-3 text-sm text-sand-300">
          <p>This page is only the control panel. The video engine itself runs on your computer, because it needs FFmpeg, the AI models and your GPU, which a website host such as Vercel can't provide.</p>
          <ol className="list-decimal space-y-1 pl-5">
            <li>On your PC, run <code className="text-mane-300">scripts\start.bat</code> and leave the window open.</li>
            <li>Make sure <code className="text-mane-300">backend\.env</code> allows this site: <code className="break-all text-mane-300">CORS_ORIGINS={window.location.origin}</code>, then restart.</li>
            {hosted && <li>If Chrome asks to let this site access devices on your local network, choose <b>Allow</b>.</li>}
            <li>Press <b>Try again</b>.</li>
          </ol>
          <p className="text-sand-400">Simplest option: skip the hosted site and open <a className="text-mane-300 underline" href="http://localhost:8000">http://localhost:8000</a> on the PC running the engine.</p>
        </div>
      ) : (
        <p className="mt-4 text-sm text-sand-300">The engine has <code>ENGINE_ACCESS_TOKEN</code> set. Enter the same token below.</p>
      )}
      <div className="card mt-6 space-y-3">
        <div>
          <label className="label">Engine URL</label>
          <input className="input" value={base} onChange={(e) => setBase(e.target.value)} placeholder="http://localhost:8000" />
        </div>
        <div>
          <label className="label">Access token (if set)</label>
          <input className="input" type="password" value={token} onChange={(e) => setToken(e.target.value)} />
        </div>
        <button className="btn-primary" onClick={() => { config.base = base; config.token = token; check(); }}>Try again</button>
      </div>
    </div>
  );
}

/** Never show a blank page: render the error instead. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error?: Error }> {
  state: { error?: Error } = {};
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto max-w-2xl p-6 py-16">
        <h1 className="font-display text-2xl">Something went wrong in the page</h1>
        <pre className="card mt-4 whitespace-pre-wrap text-xs text-red-300">{this.state.error.message}</pre>
        <button className="btn-primary mt-4" onClick={() => location.reload()}>Reload</button>
      </div>
    );
  }
}
