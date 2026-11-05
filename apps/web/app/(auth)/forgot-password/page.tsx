import type { Metadata } from "next";
import { ForgotPasswordPage } from "@/components/auth-pages";

export const metadata: Metadata = { title: "Reset password" };

export default function Page() {
  return <ForgotPasswordPage />;
}
