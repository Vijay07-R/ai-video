import { useState } from "react";
import { api } from "../api";
import { Empty, ErrorBox, PageHeader, useLoad } from "../ui";
import { ProjectCard } from "./Dashboard";

export default function History() {
  const [q, setQ] = useState("");
  const [projects, error] = useLoad(api.projects, [], 10000);
  const list = projects?.filter((p) => `${p.title} ${p.animal} ${p.prompt}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <PageHeader title="Projects" subtitle="All your videos, newest first." actions={<a className="btn-primary" href="#/create">+ New video</a>} />
      <input className="input mb-4 max-w-sm" placeholder="Search by title, animal or idea" value={q} onChange={(e) => setQ(e.target.value)} />
      <ErrorBox error={error} />
      {list && (list.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{list.map((p) => <ProjectCard key={p.id} p={p} />)}</div>
      ) : <Empty>No projects found.</Empty>)}
    </>
  );
}
