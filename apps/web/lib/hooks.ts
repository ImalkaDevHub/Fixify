"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { ApiError, authApi, SIGNED_OUT_EVENT, type User } from "@/lib/api";

export function useMe() {
  return useQuery<User, ApiError>({ queryKey: ["me"], queryFn: authApi.me, staleTime: 60_000, retry: false });
}

/** Sends the visitor to the sign-in page when the session ends (expired or revoked). */
export function useSignedOutRedirect() {
  const router = useRouter();
  const queryClient = useQueryClient();
  useEffect(() => {
    const handler = () => {
      queryClient.clear();
      const next = window.location.pathname + window.location.search;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    };
    window.addEventListener(SIGNED_OUT_EVENT, handler);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, handler);
  }, [queryClient, router]);
}

/** Error text for an unknown thrown value. */
export function errorText(error: unknown, fallback = "Something went wrong."): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
