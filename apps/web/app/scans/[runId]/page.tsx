import { ScanDetail } from "@/components/scans/scan-detail";

export default async function ScanPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <ScanDetail runId={runId} />;
}
