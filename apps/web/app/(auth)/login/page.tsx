import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginPage } from "@/components/auth-pages";

export const metadata: Metadata = { title: "Sign in" };

export default function Page() {
  return (
    <Suspense>
      <LoginPage />
    </Suspense>
  );
}
