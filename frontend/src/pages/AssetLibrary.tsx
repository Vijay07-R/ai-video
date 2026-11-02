import { useState } from "react";
import { api } from "../api";
import { Empty, ErrorBox, PageHeader, useLoad } from "../ui";
import { AssetGrid } from "./Workspace";

const KINDS = ["", "final", "video", "image", "voice", "music", "sfx", "reference"];

export default function AssetLibrary() {
  const [kind, setKind] = useState("");
  const [assets, error] = useLoad(() => api.assets(undefined, kind || undefined), [kind]);
  return (
    <>
      <PageHeader title="Asset library" subtitle="Every image, clip, voice line, score and render the engine has produced." />
      <div className="mb-4 flex flex-wrap gap-2">
        {KINDS.map((k) => (
          <button key={k} onClick={() => setKind(k)}
                  className={`chip border px-3 py-1 ${kind === k ? "border-mane-500 text-mane-300" : "border-ink-600 text-sand-300"}`}>{k || "all"}</button>
        ))}
      </div>
      <ErrorBox error={error} />
      {assets && (assets.length ? <AssetGrid assets={assets} /> : <Empty>Nothing here yet.</Empty>)}
    </>
  );
}
