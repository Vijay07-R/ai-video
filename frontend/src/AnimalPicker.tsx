import { useMemo, useState } from "react";
import { ALL_ANIMALS, ANIMAL_GROUPS } from "./animals";

export const MAX_CAST = 6;

/** Searchable, categorised multi-select. The first selected animal is the main character. */
export default function AnimalPicker({ cast, onChange }: { cast: string[]; onChange: (c: string[]) => void }) {
  const [group, setGroup] = useState("wild");
  const [q, setQ] = useState("");
  const list = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? ALL_ANIMALS.filter((a) => a.name.toLowerCase().includes(t)) : ALL_ANIMALS.filter((a) => a.group === group);
  }, [group, q]);
  const emoji = (n: string) => ALL_ANIMALS.find((a) => a.name === n)?.emoji ?? "🐾";

  const toggle = (name: string) =>
    onChange(cast.includes(name) ? cast.filter((c) => c !== name) : cast.length >= MAX_CAST ? cast : [...cast, name]);
  const custom = q.trim();
  const canAddCustom = custom.length >= 2 && !ALL_ANIMALS.some((a) => a.name.toLowerCase() === custom.toLowerCase()) && !cast.includes(custom);

  return (
    <div>
      <div className="mb-2 flex min-h-[44px] flex-wrap items-center gap-2 rounded-xl border border-ink-600 bg-ink-850 p-2">
        {cast.length === 0 && <span className="px-1 text-sm text-sand-400">Pick one or more animals below (first = main character)</span>}
        {cast.map((c, i) => (
          <span key={c} className="chip border border-mane-500 bg-mane-500/15 py-1 pl-2 pr-1 text-mane-200">
            {emoji(c)} {c}{i === 0 && <b className="ml-1 text-[10px] uppercase text-mane-300">main</b>}
            {i > 0 && <button type="button" title="Make main character" className="ml-1 text-sand-400 hover:text-mane-300"
                              onClick={() => onChange([c, ...cast.filter((x) => x !== c)])}>★</button>}
            <button type="button" aria-label={`Remove ${c}`} className="ml-1 rounded-full px-1 text-sand-300 hover:bg-ink-700" onClick={() => toggle(c)}>×</button>
          </span>
        ))}
        <span className="ml-auto text-xs text-sand-400">{cast.length}/{MAX_CAST}</span>
      </div>

      <div className="mb-2 flex gap-2">
        <input className="input" placeholder="Search all animals (lion, dog, peacock, dolphin…) or type any animal" value={q}
               onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (canAddCustom) { toggle(custom); setQ(""); } } }} />
        {canAddCustom && <button type="button" className="btn-ghost whitespace-nowrap" onClick={() => { toggle(custom); setQ(""); }}>+ Add “{custom}”</button>}
      </div>

      {!q && (
        <div className="mb-2 flex gap-1 overflow-x-auto pb-1">
          {ANIMAL_GROUPS.map((g) => (
            <button type="button" key={g.id} onClick={() => setGroup(g.id)}
                    className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-xs ${group === g.id ? "bg-ink-700 text-mane-300" : "text-sand-300 hover:bg-ink-850"}`}>
              {g.icon} {g.label} <span className="text-sand-400">{g.animals.length}</span>
            </button>
          ))}
        </div>
      )}

      <div className="flex max-h-56 flex-wrap gap-1.5 overflow-y-auto rounded-xl border border-ink-700 p-2">
        {list.map((a) => {
          const on = cast.includes(a.name);
          return (
            <button type="button" key={a.name} onClick={() => toggle(a.name)} disabled={!on && cast.length >= MAX_CAST}
                    className={`chip border px-2.5 py-1 disabled:opacity-40 ${on ? "border-mane-500 bg-mane-500/15 text-mane-300" : "border-ink-600 text-sand-200 hover:border-sand-400"}`}>
              {a.emoji} {a.name}
            </button>
          );
        })}
        {list.length === 0 && <span className="p-2 text-sm text-sand-400">Not in the list. Press Enter or “Add” to use “{custom}”.</span>}
      </div>
      <p className="mt-1 text-xs text-sand-400">{ALL_ANIMALS.length} animals and birds listed. Any other animal can be typed in.</p>
    </div>
  );
}
