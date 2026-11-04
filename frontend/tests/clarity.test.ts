import { describe, expect, it } from "vitest";
import { startClarity, wantsClarity } from "../src/lib/clarity";

const nav = (extra: Record<string, unknown> = {}) => ({ doNotTrack: null, ...extra }) as unknown as Navigator;

describe("clarity", () => {
  it("runs only on the live site, and not for visitors who opt out", () => {
    expect(wantsClarity({ hostname: "www.erickkbonfim.com.br" }, nav())).toBe(true);
    expect(wantsClarity({ hostname: "erickkbonfim.com.br" }, nav())).toBe(true);
    expect(wantsClarity({ hostname: "localhost" }, nav())).toBe(false);
    expect(wantsClarity({ hostname: "erickkbonfim.com.br" }, nav({ doNotTrack: "1" }))).toBe(false);
    expect(wantsClarity({ hostname: "erickkbonfim.com.br" }, nav({ globalPrivacyControl: true }))).toBe(false);
  });

  it("queues calls until the tag loads, and loads it once", () => {
    startClarity("abc");
    startClarity("abc");
    const scripts = [...document.querySelectorAll<HTMLScriptElement>('script[src*="clarity.ms"]')];
    expect(scripts.map((s) => s.src)).toEqual(["https://www.clarity.ms/tag/abc"]);
    const clarity = (window as unknown as { clarity: ((...a: unknown[]) => void) & { q: unknown[][] } }).clarity;
    clarity("set", "lang", "pt");
    expect(clarity.q).toEqual([["set", "lang", "pt"]]);
  });
});
