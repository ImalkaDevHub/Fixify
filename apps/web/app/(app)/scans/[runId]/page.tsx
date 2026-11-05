import type { Metadata } from "next";
import { ScanDetailPage } from "@/components/pages/scans";

export const metadata: Metadata = { title: "Scan report" };

export default async function Page({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <ScanDetailPage id={runId} />;
}
