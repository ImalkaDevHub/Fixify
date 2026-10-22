"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { ApiError, projectApi } from "@/lib/api";
import { projectFormSchema, type ProjectCreateInput, type ProjectFormValues } from "@/lib/schemas";

export function ProjectForm() {
  const router = useRouter();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<ProjectFormValues, unknown, ProjectCreateInput>({
    resolver: zodResolver(projectFormSchema),
    defaultValues: { name: "", website_url: "", repo_full_name: "", default_branch: "" },
  });

  async function onSubmit(values: ProjectCreateInput) {
    setSubmitError(null);
    try {
      const project = await projectApi.create(values);
      router.push(`/projects/${project.id}`);
      router.refresh();
    } catch (reason) {
      setSubmitError(reason instanceof ApiError ? reason.message : "Unable to create the project. Please try again.");
    }
  }

  return (
    <>
      <Link href="/projects" className="back-link"><ArrowLeft size={14} />Back to projects</Link>
      <div className="page-heading">
        <div><span className="eyebrow">Workspace setup</span><h1>New project</h1><p className="page-subtitle">Add the website you want to keep track of.</p></div>
      </div>
      <form className="form-card" onSubmit={handleSubmit(onSubmit)} noValidate>
        {submitError && <div className="error-box" role="alert">{submitError}</div>}
        <div className="form-field">
          <label htmlFor="project-name">Project name</label>
          <input id="project-name" className="form-input" placeholder="e.g. Marketing website" autoComplete="organization" aria-invalid={Boolean(errors.name)} aria-describedby={errors.name ? "name-error" : undefined} {...register("name")} />
          {errors.name && <p id="name-error" className="field-error">{errors.name.message}</p>}
        </div>
        <div className="form-field">
          <label htmlFor="website-url">Website URL</label>
          <input id="website-url" className="form-input" placeholder="https://example.com" type="url" inputMode="url" aria-invalid={Boolean(errors.website_url)} aria-describedby={errors.website_url ? "url-error" : "url-hint"} {...register("website_url")} />
          {errors.website_url ? <p id="url-error" className="field-error">{errors.website_url.message}</p> : <p id="url-hint" className="field-hint">Use a complete URL beginning with https:// or http://.</p>}
        </div>
        <div className="form-field">
          <label htmlFor="repo-name">GitHub repository <span className="field-optional">Optional</span></label>
          <input id="repo-name" className="form-input" placeholder="owner/repository" aria-invalid={Boolean(errors.repo_full_name)} aria-describedby={errors.repo_full_name ? "repo-error" : "repo-hint"} {...register("repo_full_name")} />
          {errors.repo_full_name ? <p id="repo-error" className="field-error">{errors.repo_full_name.message}</p> : <p id="repo-hint" className="field-hint">Repository is recorded as a reference only; GitHub is not connected yet.</p>}
        </div>
        <div className="form-field">
          <label htmlFor="default-branch">Default branch <span className="field-optional">Optional</span></label>
          <input id="default-branch" className="form-input" placeholder="main" {...register("default_branch")} />
        </div>
        <div className="form-actions">
          <Link href="/projects" className="button button-secondary">Cancel</Link>
          <button type="submit" className="button" disabled={isSubmitting}>{isSubmitting ? "Creating…" : "Create project"}</button>
        </div>
      </form>
    </>
  );
}
