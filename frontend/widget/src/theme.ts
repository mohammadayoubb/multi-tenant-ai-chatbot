// Owner: Amer
// WCAG 4.5:1 contrast checker with built-in fallback. If a tenant's
// primary_color cannot meet the contrast threshold against the panel
// background (--c-bg), the widget uses --c-accent and emits a
// theme_contrast_fallback telemetry event.
//
// Design contract: research R4.

import { emit } from "./telemetry";

const DEFAULT_BG = "#ffffff";
const DEFAULT_ACCENT = "#4f46e5";
const MIN_RATIO = 4.5;

function parseHex(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  let value = m[1];
  if (value.length === 3) {
    value = value
      .split("")
      .map((c) => c + c)
      .join("");
  }
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return [r, g, b];
}

function relativeLuminance([r, g, b]: [number, number, number]): number {
  const channel = (c: number): number => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(fg: string, bg: string): number {
  const fgRgb = parseHex(fg);
  const bgRgb = parseHex(bg);
  if (!fgRgb || !bgRgb) return 0;
  const l1 = relativeLuminance(fgRgb);
  const l2 = relativeLuminance(bgRgb);
  const [lighter, darker] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (lighter + 0.05) / (darker + 0.05);
}

export function resolveAccentColor(
  primaryColor: string | undefined,
  backgroundColor: string = DEFAULT_BG
): string {
  if (!primaryColor) return DEFAULT_ACCENT;
  const ratio = contrastRatio(primaryColor, backgroundColor);
  if (ratio >= MIN_RATIO) return primaryColor;
  emit("theme_contrast_fallback", {
    requested_ratio: Number(ratio.toFixed(2)),
    minimum_ratio: MIN_RATIO,
  });
  return DEFAULT_ACCENT;
}
