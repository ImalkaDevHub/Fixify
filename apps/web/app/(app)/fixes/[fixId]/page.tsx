import type { Metadata } from "next";
import { FixDetailPage } from "@/components/pages/fixes";

export const metadata: Metadata = { title: "Fix review" };

export default async function Page({ params }: { params: Promise<{ fixId: string }> }) {
  const { fixId } = await params;
  return <FixDetailPage id={fixId} />;
}
