"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { ApiError, projectApi, type Project } from "@/lib/api";
import { ProjectList } from "@/components/projects/project-list";

export function ProjectsContent() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    projectApi.list().then(setProjects).catch((reason: unknown) => {
      setError(reason instanceof ApiError ? reason.message : "Unable to load projects right now.");
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    let active = true;
    projectApi.list().then((items) => {
      if (active) setProjects(items);
    }).catch((reason: unknown) => {
      if (active) {
        setError(reason instanceof ApiError ? reason.message : "Unable to load projects right now.");
      }
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  async function deleteProject(project: Project) {
    if (!window.confirm(`Delete "${project.name}"? This cannot be undone.`)) return;
    try {
      await projectApi.delete(project.id);
      setProjects((current) => current.filter((item) => item.id !== project.id));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Unable to delete this project.");
    }
  }

  return (
    <main className="page-content">
      <div className="page-heading">
        <div><span className="eyebrow">Workspace</span><h1>Projects</h1><p className="page-subtitle">Manage websites added to your Fixify workspace.</p></div>
        <Link href="/projects/new" className="button"><Plus size={16} />New project</Link>
      </div>
      <section className="panel">
        <div className="panel-header"><div><div className="panel-title">All projects</div><div className="panel-caption">{projects.length} {projects.length === 1 ? "website" : "websites"} saved</div></div></div>
        {error && <div className="error-box" role="alert">{error} <button className="inline-retry" onClick={load}>Try again</button></div>}
        {loading ? <div className="loading-state" role="status">Loading your projects…</div>
          : <ProjectList projects={projects} onDelete={deleteProject} />}
      </section>
    </main>
  );
}
