"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { ApiError, projectApi, type Project } from "@/lib/api";
import { ProjectList } from "@/components/projects/project-list";

export function ProjectsContent() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const retry = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    setReloadKey((key) => key + 1);
  }, []);

  useEffect(() => {
    let active = true;
    projectApi.list().then((items) => {
      if (active) setProjects(items);
    }).catch((reason: unknown) => {
      if (active) {
        setLoadError(reason instanceof ApiError ? reason.message : "Unable to load projects right now.");
      }
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [reloadKey]);

  async function deleteProject(project: Project) {
    if (deletingId) return;
    if (!window.confirm(`Delete "${project.name}"? This cannot be undone.`)) return;
    setDeletingId(project.id);
    setActionError(null);
    try {
      await projectApi.delete(project.id);
      setProjects((current) => current.filter((item) => item.id !== project.id));
    } catch (reason) {
      setActionError(reason instanceof ApiError ? reason.message : "Unable to delete this project.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <main className="page-content">
      <div className="page-heading">
        <div><span className="eyebrow">Workspace</span><h1>Projects</h1><p className="page-subtitle">Manage websites added to your Fixify workspace.</p></div>
        <Link href="/projects/new" className="button"><Plus size={16} />New project</Link>
      </div>
      <section className="panel">
        <div className="panel-header"><div><div className="panel-title">All projects</div>{!loading && !loadError && <div className="panel-caption">{projects.length} {projects.length === 1 ? "website" : "websites"} saved</div>}</div></div>
        {actionError && <div className="error-box" role="alert">{actionError}</div>}
        {loadError ? <div className="error-box" role="alert">{loadError} <button className="inline-retry" onClick={retry}>Try again</button></div>
          : loading ? <div className="loading-state" role="status">Loading your projects…</div>
            : <ProjectList projects={projects} onDelete={deleteProject} deletingId={deletingId} />}
      </section>
    </main>
  );
}
