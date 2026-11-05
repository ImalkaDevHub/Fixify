import type { Metadata } from "next";
import { NewProjectPage } from "@/components/pages/projects";

export const metadata: Metadata = { title: "New project" };

export default function Page() {
  return <NewProjectPage />;
}
