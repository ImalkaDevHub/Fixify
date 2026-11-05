import { Compass } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="ambient flex min-h-screen flex-col items-center justify-center px-6 text-center">
      <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl border border-line bg-card text-violet-soft">
        <Compass className="h-5 w-5" />
      </div>
      <h1 className="text-[22px] font-semibold">Page not found</h1>
      <p className="mt-2 max-w-sm text-[13.5px] text-muted">The page does not exist, or it belongs to another account.</p>
      <ButtonLink href="/dashboard" className="mt-6">Back to overview</ButtonLink>
    </main>
  );
}
