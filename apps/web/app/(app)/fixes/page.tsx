import type { Metadata } from "next";
import { FixesPage } from "@/components/pages/fixes";

export const metadata: Metadata = { title: "AI Fixes" };

export default function Page() {
  return <FixesPage />;
}
