import type { Metadata } from "next";
import { ProjectDetailPage } from "@/components/pages/projects";

export const metadata: Metadata = { title: "Project" };

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <ProjectDetailPage id={projectId} />;
}
