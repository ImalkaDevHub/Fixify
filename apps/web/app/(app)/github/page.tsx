import type { Metadata } from "next";
import { GitHubPage } from "@/components/pages/github";

export const metadata: Metadata = { title: "GitHub" };

export default function Page() {
  return <GitHubPage />;
}
