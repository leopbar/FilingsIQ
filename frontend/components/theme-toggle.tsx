"use client";

import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Flips between the light and dark themes. The class is set pre-paint by the layout script. */
export function ThemeToggle() {
  const toggle = () => {
    const dark = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* storage unavailable — theme still applies for this session */
    }
  };

  return (
    <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle light and dark theme">
      <Sun className="hidden size-4 dark:block" />
      <Moon className="size-4 dark:hidden" />
    </Button>
  );
}
