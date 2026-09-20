import type { Edit } from "./api";

/** Backend offsets are Unicode CODE POINTS; JS strings are UTF-16. Work on code-point arrays instead. */
export type Seg = { kind: "plain" | "edit"; text: string; edit?: Edit };

export function segments(source: string, edits: Edit[]): Seg[] {
  const cps = Array.from(source);
  const out: Seg[] = [];
  let pos = 0;
  for (const e of [...edits].sort((a, b) => a.start - b.start || a.end - b.end)) {
    if (e.start < pos) continue; // overlapping (should not happen); skip defensively
    if (e.start > pos) out.push({ kind: "plain", text: cps.slice(pos, e.start).join("") });
    out.push({ kind: "edit", text: cps.slice(e.start, e.end).join(""), edit: e });
    pos = Math.max(pos, e.end);
  }
  if (pos < cps.length) out.push({ kind: "plain", text: cps.slice(pos).join("") });
  return out;
}

export const LEVEL_LABEL: Record<string, string> = {
  seq2seq_gec: "Neural GEC model",
  seq2seq_gec_zero_shot: "Zero-shot neural model",
  rules_and_detection: "Rules + detection only",
  none: "Not supported",
};
