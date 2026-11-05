import type { Metadata } from "next";
import { FindingsPage } from "@/components/pages/findings";

export const metadata: Metadata = { title: "Findings" };

export default function Page() {
  return <FindingsPage />;
}
