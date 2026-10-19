// Text builders ported from ../src/cbj/static/index.html (routeSummary, refSummary, numText, the facts line).

import type { Brief, GameEvent, Numbers, ReferenceRead, Route } from "./types";
import { ROUTE_TYPES } from "./words";

export function routeSummary(r: Route): string {
  const t = (r.targets || []).map(
    (x) =>
      `${x.name}${x.when && x.when[0] != null ? ` (${x.when[0]}-${x.when[1]} s)` : ""}${x.missing ? " — not in this ad" : ""}${x.located ? `, ${x.located.note}` : ""}`,
  );
  return (
    `${ROUTE_TYPES[r.edit_type || ""] || r.edit_type || "an edit"}; ${r.level_name || ""}${t.length ? `; target: ${t.join("; ")}` : ""}` +
    `; ${r.requires_gameplay_regeneration ? "the game films it again" : "the gameplay render is reused"}` +
    `; video analysis: ${
      r.requires_video_analysis === true
        ? "yes (a video the tool did not make)"
        : r.requires_video_analysis === "optional"
          ? "optional (a moment the metadata could not place)"
          : "none"
    }` +
    `${(r.preserve || []).length ? `; preserved: ${(r.preserve || []).join(", ")}` : ""}`
  );
}

export function refSummary(r: ReferenceRead): string {
  const n = r.notes || {};
  if (r.kind === "video") {
    return `${r.skipped ? "not read: " + r.skipped : n.concept_in_one_line || n.what_it_shows || "a video"}; ending ${n.ending || "?"}, pacing ${n.pacing || "?"}${
      n.hook ? `, hook “${n.hook}”` : ""
    }${
      (n.structure || []).length
        ? `; structure: ${(n.structure || []).map((x) => `${x.from_s}-${x.to_s} s ${(x.purpose || "").replace("_", "-")}`).join(", ")}`
        : ""
    }${r.focus ? `; read for ${r.focus.join(", ") || "nothing"} (${r.level})` : ""}`;
  }
  const pal = (r.palette || [])
    .slice(0, 4)
    .map((p) => p.name)
    .join(", ");
  const roleWords: [keyof NonNullable<ReferenceRead["role"]>, string][] = [
    ["modify", "picture that modifies the creative"],
    ["composition", "board reference"],
    ["asset", "picture to place"],
    ["style", "style reference"],
  ];
  const role = r.role
    ? ` — used as a ${
        roleWords
          .filter(([k]) => r.role?.[k])
          .map(([, w]) => w)
          .join(" and a ") || "reference"
      }${(r.role.taken || []).length ? `: ${(r.role.taken || []).join("; ")}` : ""}`
    : "";
  const b = n.board;
  const board = b && b.is_puzzle_board ? `; a board: ${b.grid_cols || "?"}x${b.grid_rows || "?"}, ${b.block_count || "?"} blocks, ${(b.block_colours || []).join("/")}` : "";
  return `${n.subject || "an image"}; colours ${pal}; mood ${n.mood || "?"}${board}${role}`;
}

export function numText(n?: Numbers): string {
  if (!n) return "";
  const play = n.play_s ? `${n.play_s[0]}-${n.play_s[1]} s` : "?";
  return `${n.fps} fps, ${n.duration_s} s, play ${play}, first move ${n.first_move_s} s, ${n.drags} drags, clock ${n.clock_start_s} → ${n.clock_end_s} s`;
}

const evText = (e: GameEvent) =>
  `${e.block.all ? "all " : ""}${e.block.which !== "any" ? e.block.which + " " : ""}${e.block.colour || "block"} ${e.action}${e.when !== "next" ? " " + e.when : ""}`;

/** The facts line under the summary ("ending: near-fail · 30 s, normal tempo · …"). */
export function briefFacts(b: Brief): string[] {
  const gp = b.gameplay;
  const lv = b.level;
  if (!gp || !b.pacing || !lv) return [];
  return [
    `ending: ${gp.ending.replace("_", "-")}${gp.clock_left_s ? ` (00:0${gp.clock_left_s} left)` : ""}`,
    `${b.pacing.length_s} s, ${b.pacing.tempo} tempo${b.pacing.curve !== "even" ? ", " + b.pacing.curve.replace("_", " ") : ""}`,
    ...(gp.events?.length ? [`order: ${gp.events.map(evText).join(" → ")}`] : []),
    ...(gp.finish && gp.finish !== "auto" ? [`finish: ${gp.finish}`] : []),
    ...(lv.pieces && lv.pieces !== "mixed" ? [`pieces: ${lv.pieces}`] : []),
    ...(lv.style?.length ? [`board: ${lv.style.join(", ")}`] : []),
    `level: ${lv.source}${lv.shape !== "any" ? " / " + lv.shape : ""}${lv.difficulty !== "any" ? " / " + lv.difficulty : ""}`,
    `theme: ${b.visuals?.theme}`,
    `sequence: ${b.sequence?.style.replace("_", " ")}${b.sequence?.replay ? "" : ", no replay"}`,
    `channel: ${b.channel}`,
    `language: ${b.language}`,
  ];
}

export function difficultyWord(d?: string): string {
  if (!d || d === "any") return "";
  return { easy: "Easy", medium: "Medium", hard: "Hard", very_hard: "Very hard" }[d] || d.replace("_", " ");
}

export function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
}
