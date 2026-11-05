import type { Metadata } from "next";
import { VerifyEmailPage } from "@/components/auth-pages";

export const metadata: Metadata = { title: "Verify email" };

export default function Page() {
  return <VerifyEmailPage />;
}
