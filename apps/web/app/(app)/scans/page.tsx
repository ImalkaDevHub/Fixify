import type { Metadata } from "next";
import { ScansPage } from "@/components/pages/scans";

export const metadata: Metadata = { title: "Scans" };

export default function Page() {
  return <ScansPage />;
}
