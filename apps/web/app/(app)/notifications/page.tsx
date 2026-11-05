import type { Metadata } from "next";
import { NotificationsPage } from "@/components/pages/notifications";

export const metadata: Metadata = { title: "Notifications" };

export default function Page() {
  return <NotificationsPage />;
}
