import type { Metadata } from "next";
import { FindingDetailPage } from "@/components/pages/findings";

export const metadata: Metadata = { title: "Finding" };

export default async function Page({ params }: { params: Promise<{ findingId: string }> }) {
  const { findingId } = await params;
  return <FindingDetailPage id={findingId} />;
}
