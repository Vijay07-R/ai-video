import { useRoute } from "./ui";
import Dashboard from "./pages/Dashboard";
import CreateVideo from "./pages/CreateVideo";
import Workspace from "./pages/Workspace";
import AssetLibrary from "./pages/AssetLibrary";
import History from "./pages/History";
import Providers from "./pages/Providers";
import UsagePage from "./pages/Usage";
import Settings from "./pages/Settings";

const NAV = [
  { path: "", label: "Dashboard" },
  { path: "create", label: "Create video" },
  { path: "history", label: "Projects" },
  { path: "assets", label: "Asset library" },
  { path: "providers", label: "Free providers & hardware" },
  { path: "usage", label: "Usage & cost" },
  { path: "settings", label: "Settings" },
];

export default function App() {
  const route = useRoute();
  const [page, id, tab] = route;
  let body;
  switch (page) {
    case "create": body = <CreateVideo />; break;
    case "project": body = <Workspace id={id} tab={tab ?? "overview"} />; break;
    case "history": body = <History />; break;
    case "assets": body = <AssetLibrary />; break;
    case "providers": body = <Providers />; break;
    case "usage": body = <UsagePage />; break;
    case "settings": body = <Settings />; break;
    default: body = <Dashboard />;
  }
  const active = page ?? "";
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 flex-none flex-col border-r border-ink-800 bg-ink-900/60 p-5 md:flex">
        <a href="#/" className="mb-8 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-2xl bg-gradient-to-br from-mane-300 to-mane-600 font-display text-xl font-bold text-ink-950">A</span>
          <span>
            <span className="block font-display text-lg leading-tight">Animal Video</span>
            <span className="block text-xs text-sand-400">Engine · zero-cost</span>
          </span>
        </a>
        <nav className="flex flex-col gap-1">
          {NAV.map((n) => (
            <a key={n.path} href={`#/${n.path}`}
               className={`rounded-xl px-3 py-2 text-sm transition ${active === n.path || (n.path === "history" && active === "project") ? "bg-ink-800 text-mane-300" : "text-sand-300 hover:bg-ink-850 hover:text-sand-100"}`}>
              {n.label}
            </a>
          ))}
        </nav>
        <div className="mt-auto rounded-xl border border-emerald-900/60 bg-emerald-950/30 p-3 text-xs text-emerald-200">
          Spending limit <b>$0</b>. Only free and local providers run.
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex items-center justify-between border-b border-ink-800 px-4 py-3 md:hidden">
          <a href="#/" className="font-display text-lg">Animal Video Engine</a>
          <select className="input w-auto" value={active} onChange={(e) => (window.location.hash = `#/${e.target.value}`)}>
            {NAV.map((n) => <option key={n.path} value={n.path}>{n.label}</option>)}
          </select>
        </header>
        <main className="mx-auto max-w-7xl p-4 md:p-8">{body}</main>
      </div>
    </div>
  );
}
