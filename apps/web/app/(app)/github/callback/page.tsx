import type { Metadata } from "next";
import { Suspense } from "react";
import { GitHubCallbackPage } from "@/components/pages/github";

export const metadata: Metadata = { title: "Connecting GitHub" };

export default function Page() {
  return (
    <Suspense>
      <GitHubCallbackPage />
    </Suspense>
  );
}
