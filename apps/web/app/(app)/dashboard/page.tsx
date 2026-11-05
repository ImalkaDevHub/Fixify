import type { Metadata } from "next";
import { DashboardPage } from "@/components/pages/dashboard";

export const metadata: Metadata = { title: "Overview" };

export default function Page() {
  return <DashboardPage />;
}
