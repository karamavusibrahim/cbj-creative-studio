// The plain-English words of the engine's own page (../src/cbj/static/index.html), kept 1:1.

import type { FeedbackArea, FeedbackStep } from "./types";

/** Five full test-case prompts from NEW_EXAMPLES, with a short chip label each. */
export const IDEAS: { label: string; tone: "error" | "secondary" | "outline" | "tertiary" | "primary"; prompt: string }[] = [
  {
    label: "Beat the clock",
    tone: "error",
    prompt:
      "Make a dramatic 30-second portrait Color Block Jam creative: a near-fail where the player makes one wrong move, gets stuck for a moment, then recovers and the last block starts leaving with one second showing on the clock, followed by the win. Hard difficulty; the pace speeds up toward the end as the clock runs down. The game's own look with the clock visible. Concept: 'beat the clock'; hook caption 'Can you beat the clock?', a hurry caption in the last seconds, result caption 'Just in time!'. Sequence: hook, gameplay, slow-motion replay of the last moves, the game's Level Completed screen, end card.",
  },
  {
    label: "One move frees them all",
    tone: "secondary",
    prompt:
      "Build a 30-second Color Block Jam creative whose first half sets up a clever solution on a medium board where one central blocking block holds four other blocks back from their doors. A satisfying solve: a few set-up moves, then the key move frees everything and the four remaining blocks leave through their correct doors one after another in quick succession; no wrong moves. Medium difficulty; the pace speeds up from the set-up to the cascade. Concept: 'one move frees them all'; hook caption 'One move frees them all', a cascade caption on the quick finish. Game assets and sound effects only.",
  },
  {
    label: "One wrong move",
    tone: "outline",
    prompt:
      "Create a 30-second portrait Color Block Jam gameplay advertisement. Start from a board that looks almost completed: three blocks left in two colours, one narrow corridor to the doors. The player makes a wrong move that blocks the remaining path and gets stuck; then the puzzle replays from the same starting position and shows the correct order of drags that clears every block. Concept: 'one wrong move'; caption 'Don't do this...' over the mistake and 'Do this' over the correct run. Sequence: hook, the mistake, the correct run, the game's win screen, then the end card with PLAY NOW. Game assets and sound effects only, no music.",
  },
  {
    label: "Beginner clean solve",
    tone: "tertiary",
    prompt:
      "Create a beginner-friendly Color Block Jam level on a small open board: only 1x1 and 1x2 blocks in red, green and blue, each with a matching exit door on the board edge, and plenty of empty cells so every block has room to move. The player solves it in one clean pass with no wrong moves. Easy difficulty, a calm pace with a generous clock, a 30-second portrait ad. Do not change the game's rules, HUD or block shapes.",
  },
  {
    label: "Which side first?",
    tone: "primary",
    prompt:
      "Generate a visually striking 30-second portrait Color Block Jam creative: a mirror-symmetric narrow-centre (hourglass) board with red blocks on the left half and blue blocks on the right, their matching doors near their own edges, and the shared bottleneck in the middle. All the red blocks leave first, then all the blue ones, so one side is cleared before the other and the symmetry breaks naturally; no wrong moves. The game's own look, blocks in the game's red and blue. Concept: 'which side first?'; hook caption 'Which side goes first?'.",
  },
];

export const EDIT_EXAMPLES = [
  "Keep everything exactly the same, but change the background behind the board to light blue.",
  "Keep the gameplay and timing unchanged, but replace the opening caption with 'Can you solve this?'.",
  "Keep the video unchanged, but replace the background music with the attached track.",
  "Keep everything exactly the same, but apply the attached texture to the blue block.",
  "Keep everything, but replace the coin pile on the end card with the attached picture.",
  "Keep everything exactly the same, but make the hook say 'Beat this in 20 seconds'.",
  "Change the caption that appears when the timer reaches ten seconds to 'Hurry up!'.",
  "Same ad, but add a second mistake before the solve.",
  "Keep everything, but put our logo (attached) in the top left corner.",
  "Same ad without the slow-motion replay.",
  "Keep the gameplay but use yellow captions with a dark outline.",
  "Same ad, but in Turkish.",
];

/** The eight prompt controls (offline fallback for /api/meta.controls). */
export const CONTROL_TITLES: Record<string, string> = {
  level: "Type or structure of the level",
  gameplay: "Gameplay behaviour",
  difficulty_pacing: "Difficulty or pacing",
  visuals: "Visual elements",
  concept: "Creative concept",
  sequence: "Sequence of events",
  assets: "Assets to use",
  unchanged: "Elements that should remain unchanged",
};

export const ROUTE_TYPES: Record<string, string> = {
  new_creative: "a new creative",
  adapt_reference: "a creative adapted from the attached video",
  direct: "a direct edit, made in code",
  known_layers: "an edit of known layers through the planner",
  planner: "an edit through the planner",
  gameplay_edit: "a gameplay edit (a retake in the game)",
  conflict: "a contradiction (refused)",
};

export const ROW_STATUS: Record<string, string> = {
  kept: "kept",
  asked: "changed, as asked",
  side_effect: "changed, because of it",
  not_asked: "CHANGED WITHOUT BEING ASKED",
  changed: "differs",
};

export const CHECKLIST: Record<string, string> = {
  level_unchanged: "level",
  moves_unchanged: "moves",
  move_timing_unchanged: "move timing",
  gameplay_render_reused: "gameplay render reused",
  duration_unchanged: "duration",
  camera_unchanged: "camera",
  hud_unchanged: "HUD",
  captions_unchanged: "captions",
  pictures_unchanged: "pictures",
  audio_unchanged: "audio",
};

export const SCORE_WORDS: Record<string, string> = {
  first_second: "first second",
  dead_time: "dead time",
  pace: "pace",
  readability: "readability",
  clarity: "clarity",
  cta: "call to action",
};

export const ENDINGS: Record<string, string> = {
  win: "clean win",
  near_fail: "near-fail win",
  time_out: "time-out fail",
  cliffhanger: "cliffhanger",
};

/** The prompt helpers: each choice appends one plain sentence to the prompt. */
export const HELPERS = {
  length: {
    label: "Video duration",
    options: [
      { id: "30", text: "30 sec", sentence: "30 seconds." },
      { id: "45", text: "45 sec", sentence: "45 seconds." },
      { id: "60", text: "60 sec", sentence: "60 seconds." },
    ],
  },
  format: {
    label: "Format",
    options: [
      { id: "9:16", text: "9:16", sentence: "Portrait 9:16 format." },
      { id: "1:1", text: "1:1", sentence: "Square 1:1 format." },
      { id: "16:9", text: "16:9", sentence: "Landscape 16:9 format." },
    ],
  },
  difficulty: {
    label: "Puzzle difficulty",
    options: [
      { id: "easy", text: "Easy", sentence: "An easy level." },
      { id: "medium", text: "Balanced", sentence: "A medium-difficulty level." },
      { id: "hard", text: "Hard", sentence: "A hard level." },
    ],
  },
  ending: {
    label: "Hook & ending arc",
    options: [
      { id: "near_fail", text: "Near-fail clutch win", sentence: "The player almost fails and wins with two seconds left." },
      { id: "clean", text: "Calm, clean solve", sentence: "A calm, clean solve with no wrong moves." },
      { id: "cliffhanger", text: "Cliffhanger cut", sentence: "End on a cliffhanger: stop with two blocks left and ask if they can see the move." },
      { id: "time_out", text: "Time-out fail, one block left", sentence: "The player runs out of time with one block left." },
      { id: "mistake", text: "A mistake, then the fix", sentence: "The player makes one wrong move, then fixes it and wins." },
    ],
  },
} as const;

export type HelperKey = keyof typeof HELPERS;
export type HelperChoice = Partial<Record<HelperKey, string>>;

export function helperSentences(choice: HelperChoice): { key: HelperKey; sentence: string }[] {
  const out: { key: HelperKey; sentence: string }[] = [];
  for (const key of Object.keys(HELPERS) as HelperKey[]) {
    const id = choice[key];
    const opt = (HELPERS[key].options as readonly { id: string; sentence: string }[]).find((o) => o.id === id);
    if (opt) out.push({ key, sentence: opt.sentence });
  }
  return out;
}

export function mergePrompt(prompt: string, choice: HelperChoice): string {
  const extra = helperSentences(choice).map((s) => s.sentence);
  const base = prompt.trim();
  if (!extra.length) return base;
  return [base ? (/[.!?]$/.test(base) ? base : `${base}.`) : "", ...extra].filter(Boolean).join(" ");
}

export const PRESERVED = [
  "the level and the board",
  "the moves and their timing",
  "the camera",
  "the HUD and the clock",
  "every other picture",
  "the captions",
  "the sound",
];

export const KIND_WORDS: Record<string, string> = {
  create: "Text",
  image_guided: "Image reference",
  guided: "Video reference",
  edit: "Edits",
  "edit-ladder": "Edits",
};

export const WORKFLOW_WORDS: Record<string, string> = {
  create: "from text",
  image_guided: "image reference",
  guided: "video reference",
  edit: "edit",
};

/** How the engine will read a request (enhance.py WORKFLOW_WORDS), after "Will be read as: ". */
export const READ_AS: Record<string, string> = {
  create: "a new creative from the text (pictures attached, if any, are placed as assets)",
  image_guided: "a new creative guided by the attached picture (it is read as a reference)",
  guided: "a new creative guided by the attached video (it is read whole as a reference)",
  edit: "an edit of this creative: only what the request names changes, and the edit report proves it",
};

/** Append one sentence to a prompt, after a full stop and a space. Returns the new text and exactly what was inserted. */
export function appendSentence(text: string, sentence: string): { text: string; inserted: string } {
  const base = text.replace(/\s+$/, "");
  const inserted = !base ? sentence : /[.!?]["'”’)]?$/.test(base) ? ` ${sentence}` : `. ${sentence}`;
  return { text: base + inserted, inserted };
}

/** Remove exactly what appendSentence inserted (the last occurrence); falls back to the bare sentence. */
export function removeInserted(text: string, inserted: string, sentence: string): string {
  for (const piece of [inserted, ` ${sentence}`, sentence]) {
    const i = text.lastIndexOf(piece);
    if (piece && i >= 0) return text.slice(0, i) + text.slice(i + piece.length);
  }
  return text;
}

export const IMAGE_EXT = /\.(png|jpe?g|webp)$/i;
export const VIDEO_EXT = /\.(mp4|mov|webm|m4v)$/i;
export const AUDIO_EXT = /\.(wav|mp3|m4a|aac|ogg|flac)$/i;

/** Whether the words make an attached picture a reference (imageplan.is_image_reference, ported without the
 * placement exception): the engine decides; this only labels the chip before planning. */
const STRONG_CUES = new RegExp(
  [
    "\\binspired by\\b", "\\binspiration\\b", "\\blike (this|that|these|those|the ones?)\\b", "\\bsimilar to\\b",
    "\\b(this|that|the) (image|picture|photo|screenshot|board)'?s\\b",
    "\\b(of|from|in) (this|that|the attached|the uploaded|the) (image|picture|photo|screenshot|board)\\b",
    "\\bas (crowded|full|packed|busy|dense|cramped|big|large|small|symmetric|many \\w+) as\\b",
    "\\bthis (board|screenshot|grid)\\b",
    "\\bits (\\w+ )?(look|colou?rs|palette|style|board|mood|vibe|theme|background|captions?)\\b",
  ].join("|"),
  "i",
);
const REFERENCE_WORDS = [
  "inspired", "inspiration", "reference", "like this", "similar", "match", "matching", "style", "mood", "palette",
  "colours of", "colors of", "based on", "this concept", "look like", "feel", "vibe", "same look", "this look", "adapt",
  "version of", "recreate", "copy the", "like that", "in the style of", "theme of", "colours from", "colors from",
];

export function isImageReference(prompt: string): boolean {
  const low = prompt.toLowerCase();
  return STRONG_CUES.test(prompt) || REFERENCE_WORDS.some((w) => low.includes(w));
}

export function roleOf(name: string, prompt: string): { word: string; tone: "primary" | "tertiary" | "secondary" } {
  if (VIDEO_EXT.test(name)) return { word: "reference video, read whole, never placed in the ad", tone: "tertiary" };
  if (AUDIO_EXT.test(name)) return { word: "music for the ad", tone: "secondary" };
  return isImageReference(prompt)
    ? { word: "reference image", tone: "primary" }
    : { word: "asset to place", tone: "secondary" };
}

// ── designer feedback (feedback.AREA_WORDS, lessons.WORKFLOW_WORDS), kept 1:1 ─────────────────────────

export const AREA_WORDS: Record<string, string> = {
  level: "the level or the board",
  ending: "the ending",
  captions: "the captions or the hook",
  tempo: "the tempo or the length",
  look: "the look, colours or background",
  sound: "the sound or the music",
  hud: "the HUD (timer, moves, labels)",
  hands: "the hand or the pointer",
  edit: "an edit that changed too much or too little",
  understanding: "how the prompt was understood",
  speed: "waiting time",
  website: "the website itself",
  other: "something else",
};

/** The four kinds of note: the dialog's chip words and the short word on the owner's list. */
export const FEEDBACK_KINDS: { id: "wrong" | "missing" | "good" | "idea"; text: string; short: string; tone: "amber" | "mint" | "grey" }[] = [
  { id: "wrong", text: "Something's wrong", short: "wrong", tone: "amber" },
  { id: "missing", text: "Something's missing", short: "missing", tone: "amber" },
  { id: "good", text: "This was good", short: "good", tone: "mint" },
  { id: "idea", text: "An idea", short: "idea", tone: "grey" },
];

/** feedback.STEP_WORDS (also /api/meta features.feedback_steps): the step of the process a note is about. The keys are
 * the engine's stage names, as the Progress strip uses them, plus "result" (the whole creative) and "other". */
export const STEP_WORDS: Record<FeedbackStep, string> = {
  plan: "how the request was read",
  level: "the level (the board)",
  recording: "the gameplay (the moves and the clock)",
  compose: "the video (captions, pictures, end card, sound)",
  review: "the viewer's review",
  revise: "the automatic revision",
  proof: "the edit report (what changed, what was kept)",
  result: "the whole result",
  other: "something else",
};

/** The order of the inline panel's step chips (proof only when the version is an edit). */
export const STEP_ORDER: FeedbackStep[] = ["result", "plan", "level", "recording", "compose", "review", "revise", "proof", "other"];

/** The area a note gets from its step (the owner's page filters on the area); the designer can change it. */
export const STEP_AREA: Record<FeedbackStep, FeedbackArea> = {
  plan: "understanding",
  level: "level",
  recording: "tempo",
  compose: "captions",
  review: "other",
  revise: "edit",
  proof: "edit",
  result: "other",
  other: "other",
};

/** The step a check is about, from its name's prefix ("Rules: the moves" → the gameplay). */
export function checkStep(name: string): FeedbackStep {
  if (/^Rules:/i.test(name)) return "recording";
  if (/^(Video|Image|Reference):/i.test(name)) return "plan";
  return "result"; // "Asked: …" and the rest: the whole result
}

/** lessons.WORKFLOW_WORDS: the lesson cards' titles, and the workflow word on the feedback dialog's context line. */
export const LESSON_WORKFLOW_WORDS: Record<string, string> = {
  create: "text to creative",
  guided: "video-guided creative",
  image_guided: "image-guided creative",
  edit: "controlled editing",
  website: "the website",
  general: "the whole tool",
};

/** "2026-10-18 13:51:00" → "Oct 18, 13:51" */
export function stampWords(s: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(s || "");
  if (!m) return s || "";
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[Number(m[2]) - 1] || m[2]} ${Number(m[3])}, ${m[4]}:${m[5]}`;
}

/** Magpie's English voices (SPEC-SOUNDTRACK §1): shown short, sent in full. The first is the default. */
export const VOICES: { name: string; text: string }[] = ["Mia", "Aria", "Leo", "Sofia", "Ray", "Jason"].flatMap((who) =>
  ["", ".Calm", ".Neutral"].map((style) => ({
    name: `Magpie-Multilingual.EN-US.${who}${style}`,
    text: style ? `${who}, ${style.slice(1).toLowerCase()}` : who,
  })),
);

export const NO_VOICE_TIP = "The engine has no voice (NVIDIA key or the voice extra)";
export const NARRATE_TIP = "NVIDIA Magpie speaks each caption of this creative as it appears";
export const NARRATIONS: { id: "captions" | "hook"; text: string }[] = [
  { id: "captions", text: "All captions" },
  { id: "hook", text: "Hook only" },
];
