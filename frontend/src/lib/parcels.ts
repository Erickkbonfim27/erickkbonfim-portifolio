import type { CSSProperties } from "react";

export interface Cell {
  cls: string;
  style: CSSProperties;
}

/** The deterministic 14×8 parcel map from the handoff (same seed, same pattern). */
export function buildCells(): Cell[] {
  const out: Cell[] = [];
  let seed = 11;
  const rnd = () => {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 14; c++) {
      const v = rnd();
      let cls = "cell";
      if (r === 4 || Math.abs(c - (r * 1.1 + 3)) < 0.55) cls += " road";
      else if (v > 0.86) cls += " hot";
      else if (v > 0.6) cls += " z2";
      else if (v > 0.3) cls += " z1";
      out.push({ cls, style: { animationDelay: `${((r + c) * 0.07).toFixed(2)}s` } });
    }
  }
  return out;
}
