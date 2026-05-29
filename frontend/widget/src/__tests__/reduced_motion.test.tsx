// Owner: Amer
// T104 — Reduced motion: when prefers-reduced-motion is set, animations
// and transitions are gated off. We verify that the gating CSS exists in
// styles.css (jsdom doesn't honor @media (prefers-reduced-motion) at the
// computed-style level) and that the bubble-in animation only runs inside
// the no-preference block.

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const STYLES_PATH = path.resolve(process.cwd(), "src", "styles.css");

describe("US4: reduced-motion gating (T110)", () => {
  it("styles.css gates the message-bubble animation behind no-preference", () => {
    const css = fs.readFileSync(STYLES_PATH, "utf8");
    expect(css).toMatch(/@media \(prefers-reduced-motion: no-preference\)/);
    const blocks = css.match(
      /@media \(prefers-reduced-motion: no-preference\)\s*\{[\s\S]*?\n\}/g
    );
    expect(blocks).not.toBeNull();
    const merged = (blocks ?? []).join("\n");
    expect(merged).toContain("animation: bubble-in");
    expect(merged).toContain("animation: typing-bounce");
  });

  it("base message-bubble rule does not declare an animation", () => {
    const css = fs.readFileSync(STYLES_PATH, "utf8");
    const bubble = css.match(/\.message-bubble\s*\{[\s\S]*?\n\}/);
    expect(bubble).not.toBeNull();
    expect(bubble![0]).not.toMatch(/animation:/);
  });

  it("input + send button transitions are 0ms outside the gate", () => {
    const css = fs.readFileSync(STYLES_PATH, "utf8");
    const field = css.match(/\.chat-input__field\s*\{[\s\S]*?\n\}/);
    const send = css.match(/\.chat-input__send\s*\{[\s\S]*?\n\}/);
    expect(field).not.toBeNull();
    expect(send).not.toBeNull();
    expect(field![0]).toContain("transition: border-color 0ms");
    expect(send![0]).toContain("transition: background 0ms");
  });
});
