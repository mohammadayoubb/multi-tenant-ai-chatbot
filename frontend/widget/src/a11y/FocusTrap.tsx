// Owner: Amer
// Minimal focus-trap helper for the widget Panel. Two-element wraparound
// (Tab past the last focusable child returns to the first; Shift+Tab past
// the first returns to the last). ESC handler is bound at the trap level
// so the host page's ESC bindings are untouched.
//
// Design contract: research R2. No third-party dep — ~30-line audited code.

import React, { useEffect, useRef } from "react";

interface FocusTrapProps {
  onEscape?: () => void;
  initialFocusRef?: React.RefObject<HTMLElement>;
  children: React.ReactNode;
}

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function focusableChildren(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
  ).filter((el) => !el.hasAttribute("aria-hidden"));
}

export function FocusTrap({
  onEscape,
  initialFocusRef,
  children,
}: FocusTrapProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocused.current = (document.activeElement as HTMLElement) ?? null;
    const target =
      initialFocusRef?.current ??
      focusableChildren(containerRef.current as HTMLElement)[0] ??
      null;
    target?.focus();
    return () => {
      previouslyFocused.current?.focus?.();
    };
  }, [initialFocusRef]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      const root = containerRef.current;
      if (!root) return;
      if (event.key === "Escape") {
        if (onEscape) {
          event.stopPropagation();
          onEscape();
        }
        return;
      }
      if (event.key !== "Tab") return;
      const focusables = focusableChildren(root);
      if (focusables.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (event.shiftKey && (active === first || !root.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }
    const root = containerRef.current;
    root?.addEventListener("keydown", onKeyDown);
    return () => root?.removeEventListener("keydown", onKeyDown);
  }, [onEscape]);

  return (
    <div ref={containerRef} data-testid="focus-trap">
      {children}
    </div>
  );
}
