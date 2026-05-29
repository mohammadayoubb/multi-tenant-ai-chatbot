// Owner: Amer
// T102 — Mobile sheet mode: at viewport 360px wide, the panel's computed
// style matches full-viewport behavior (inset:0 via media query in
// styles.css). We assert the CSS rule itself exists in the bundled
// styles.css because jsdom does not honor @media queries in the
// CSSOM by default.

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const STYLES_PATH = path.resolve(
  process.cwd(),
  "src",
  "styles.css"
);

describe("US4: mobile sheet mode (T109)", () => {
  it("styles.css contains a @media (max-width: 639px) block", () => {
    const css = fs.readFileSync(STYLES_PATH, "utf8");
    expect(css).toMatch(/@media\s*\(max-width:\s*639px\)/);
  });

  it("the mobile block sets the panel inset and 100vw/100vh shell sizing", () => {
    const css = fs.readFileSync(STYLES_PATH, "utf8");
    const block = css.match(
      /@media\s*\(max-width:\s*639px\)\s*\{[\s\S]*?\n\}/
    );
    expect(block).not.toBeNull();
    const body = block![0];
    expect(body).toContain("100vw");
    expect(body).toContain("100vh");
    expect(body).toContain("inset: 0");
    expect(body).toContain("safe-area-inset-top");
  });
});
