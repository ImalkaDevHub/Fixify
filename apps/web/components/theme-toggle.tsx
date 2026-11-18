"use client";

import { Check, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import { DropdownContent, DropdownItem, DropdownMenu, DropdownTrigger } from "@/components/ui/overlays";
import type { Theme } from "@/lib/theme";

const OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const CurrentIcon = resolvedTheme === "dark" ? Moon : Sun;

  return (
    <DropdownMenu>
      <DropdownTrigger asChild>
        <button
          type="button"
          aria-label={`Theme: ${theme}. Change theme`}
          className={
            className ??
            "flex h-9 w-9 items-center justify-center rounded-lg text-muted transition hover:bg-elevated hover:text-ink"
          }
        >
          <CurrentIcon className="h-[18px] w-[18px]" />
        </button>
      </DropdownTrigger>
      <DropdownContent className="min-w-40">
        {OPTIONS.map(({ value, label, icon: Icon }) => (
          <DropdownItem key={value} onSelect={() => setTheme(value)}>
            <Icon className="h-4 w-4" aria-hidden />
            <span className="flex-1">{label}</span>
            {theme === value && <Check className="h-3.5 w-3.5 text-violet-soft" aria-hidden />}
          </DropdownItem>
        ))}
      </DropdownContent>
    </DropdownMenu>
  );
}
