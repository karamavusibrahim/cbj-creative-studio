// The engine's data shapes (source of truth: ../src/cbj/app.py and the JSON it stores under studio/).
// Only the fields the UI reads are typed; everything else rides along untouched.

export type ControlStatus = "applied" | "default" | "adjusted" | "not_supported";

export interface Control {
  control: string;
  asked: string | null;
  plan: string;
  status: ControlStatus | string;
  why?: string | null;
  engine?: string[];
}

export interface RouteTarget {
  name: string;
  when?: [number | null, number | null] | null;
  missing?: boolean;
  located?: { note: string } | null;
}

export interface Route {
  intent?: string;
  edit_type?: string;
  level_name?: string;
  targets?: RouteTarget[];
  requires_gameplay_regeneration?: boolean;
  requires_video_analysis?: boolean | "optional";
  preserve?: string[];
  notes?: string[];
  matched?: { creative_id: string; n: number; upload: string } | null;
}

export interface Segment {
  from_s: number;
  to_s: number;
  purpose: string;
  purpose_raw?: string;
  what?: string;
}

export interface ReadingPlan {
  level?: string;
  why?: string;
  source?: string;
  questions?: string[];
  ignore?: string[];
  constraints?: string[];
  checks?: string[];
}

export interface ReferenceRead {
  kind?: string;
  file?: string;
  error?: string;
  skipped?: string;
  parts_dropped?: string;
  focus?: string[];
  level?: string;
  plan?: ReadingPlan;
  confidence?: number | string;
  low_confidence?: boolean;
  analysed_s?: number;
  reader?: string;
  notes?: {
    concept_in_one_line?: string;
    what_it_shows?: string;
    ending?: string;
    pacing?: string;
    hook?: string;
    subject?: string;
    mood?: string;
    structure?: Segment[];
    board?: {
      is_puzzle_board?: boolean;
      grid_cols?: number;
      grid_rows?: number;
      block_count?: number;
      block_colours?: string[];
    };
  };
  palette?: { name: string }[];
  role?: { modify?: boolean; composition?: boolean; asset?: boolean; style?: boolean; taken?: string[] };
}

export interface Provenance {
  kind?: string;
  file?: string;
  focus?: string[];
  level?: string;
  named?: string[];
  filled?: string[];
  analysed_s?: number;
  plan?: ReadingPlan;
  adapted?: string[];
  not_copied?: string[];
  mechanics?: string[];
  not_used?: string[];
  hud?: { took?: string[] };
  board?: { text?: string; fit?: string; took?: string[] };
}

export interface GameEvent {
  block: { all?: boolean; which: string; colour?: string };
  action: string;
  when: string;
}

export interface Brief {
  summary: string;
  controls: Control[];
  assumptions?: string[];
  needs?: string[];
  planner?: {
    model?: string;
    seconds?: number;
    workflow?: string;
    edit?: boolean;
    direct?: boolean;
    route?: Route;
    references?: ReferenceRead[];
    restored?: string[];
  };
  gameplay: { ending: string; clock_left_s?: number | null; events: GameEvent[]; finish: string };
  pacing: { length_s: number; tempo: string; curve: string };
  level: { source: string; shape: string; difficulty: string; pieces: string; style: string[] };
  visuals: { theme: string };
  sequence: { style: string; replay: boolean };
  channel: string;
  language: string;
  format?: string;
  changed?: string[];
  reference?: Provenance | null;
  concept?: { hook?: string | null; angle?: string | null };
}

export interface Check {
  check: string;
  status: string;
  detail: string;
  from: string;
}

export interface ReportRow {
  item: string;
  title: string;
  status: "kept" | "asked" | "side_effect" | "not_asked" | "changed" | string;
  detail: string;
  numbers?: { before?: Numbers; after?: Numbers };
  reasons?: string[];
}

export interface Numbers {
  fps?: number;
  duration_s?: number;
  play_s?: [number, number];
  first_move_s?: number;
  clock_start_s?: number;
  clock_end_s?: number;
  drags?: number;
}

export interface Proof {
  verdict?: string;
  ok?: boolean;
  asked?: string[];
  asked_names?: string[];
  changes?: string[];
  preserves?: string[];
  rows?: ReportRow[];
  checklist?: Record<string, { ok: boolean; evidence?: string }>;
  pixels?: {
    frames?: number;
    frames_changed?: number;
    ranges?: [number, number][];
    contained?: boolean;
    note?: string;
  };
  route?: { ok: boolean; evidence?: string; level?: number; edit_type?: string };
  // a version made before the edit report existed
  changed_controls?: string[];
  gameplay?: string;
  frames?: string;
}

export interface Review {
  overall?: "ship" | "fix" | string;
  would_download?: string;
  why?: string;
  viewer?: Record<string, number>;
  match?: { control: string; verdict: string; seen: string }[];
  fixes?: string[];
  suggested_edit?: string;
  facts?: { first_move_s?: number; static_share?: number; length_s?: number; captions?: { readable: boolean }[] };
  model?: string;
  seconds?: number;
  sheet?: string;
  error?: string;
}

export interface Version {
  id: string;
  n: number;
  from?: number | null;
  edit?: boolean;
  prompt: string;
  length_s: number;
  seconds: number;
  created?: string;
  video: string;
  poster: string;
  board?: string | null;
  ad_dir: string;
  level: { file: string; why: string; sha?: string };
  recording: { dir: string; reused: boolean };
  brief: Brief;
  checks?: Check[];
  qa: { failures: string[]; warnings: string[] };
  stages?: { stage: string; seconds: number }[];
  proof?: Proof;
  review?: Review | null;
  workflow?: string;
  audio_added?: AudioAdded; // a make with `audio` (SPEC-SOUNDTRACK §5): this version is the music edit of `from_version`
}

/** POST /api/make's optional `audio` (SPEC-SOUNDTRACK §5, §6): a soundtrack made and applied as a music edit after the make. */
export interface AudioRequest {
  bed: boolean;
  voice: boolean;
  voice_name?: string;
  line?: string;
  narration?: Narration;
}

/** What the make's `audio` stage added; the version carrying it has no review of its own (it belongs to `from_version`). */
export interface AudioAdded {
  file: string;
  description: string;
  voice: SoundtrackVoice | null;
  voice_skipped: string | null;
  bed: boolean;
  from_version: number;
}

export interface CreativeSummary {
  id: string;
  prompt: string;
  versions: number;
  last: number;
  summary: string;
}

export interface Beat {
  note: string;
  kind: string;
  tag?: string;
  exits?: boolean;
}

export interface Play {
  beats: Beat[];
  notes?: string[];
  measured?: { beat_frames?: [number, number][] };
}

export interface InventoryItem {
  id: string;
  kind: "picture" | "caption" | "sound" | "music";
  name: string;
  file?: string | null;
  shows?: string;
  text?: string;
  when?: [number, number] | null;
  can_remove?: boolean;
  empty?: boolean;
}

export interface Meta {
  controls: Record<string, string>;
  uploads: string[];
  videos: string[];
  sprites: string[];
  backend?: string;
  models?: string[];
  effort?: string;
  busy?: boolean;
  /** engines from 2026-10-19 (evening) on: which of the user's own keys this request would run on (keys.summary) */
  own_keys?: { gemini: boolean; anthropic: boolean; planner: "studio" | "anthropic" };
  groups?: Record<string, string>;
  group_names?: Record<string, string>;
  /** engines from 2026-10-18 on: which optional features this engine has */
  features?: {
    enhance?: boolean;
    trends?: boolean;
    feedback?: boolean;
    lessons?: boolean;
    soundtrack?: { bed: boolean; voice: boolean };
    /** engines from 2026-10-19 on: the steps a feedback note can point at (feedback.STEP_WORDS), and GET /api/report */
    feedback_steps?: Record<string, string>;
    report?: boolean;
    /** engines from 2026-10-19 (evening) on: the X-CBJ-* key headers are taken (SPEC-OWN-KEYS) */
    own_keys?: boolean;
  };
}

export interface Job<R = unknown> {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  stage: string;
  lines: { t: number; stage: string; text: string }[];
  n_lines: number;
  result: R | null;
  error: string | null;
  trace?: string;
  elapsed?: number;
}

export interface Preview {
  controls: Control[];
  board?: string | null;
  level_why: string;
  beats: Beat[];
  notes?: string[];
  frames?: [number, number][];
  checks?: Check[];
}

export interface ShowcaseIndexVersion {
  n: number;
  from: number | null;
  edit: boolean;
  prompt: string;
  length_s: number;
  workflow?: string;
  video: string;
  poster: string;
  summary: string;
  review_overall: string | null;
  would_download: string | null;
  video_mb?: number;
}

export interface ShowcaseIndexEntry {
  id: string;
  title: string;
  kind: string;
  tagline: string;
  prompt: string;
  versions: ShowcaseIndexVersion[];
}

export interface ShowcaseIndex {
  generated: string;
  creatives: ShowcaseIndexEntry[];
}

export interface ShowcaseDetail {
  id: string;
  title: string;
  kind: string;
  tagline: string;
  versions: Version[];
}

// ── prompt enhancement (POST /api/enhance, ../src/cbj/enhance.py) ──────────────────────────────────

export type EnhanceKind = "clarified" | "translated" | "replaced" | "removed" | "reordered";

export interface Enhanced {
  prompt: string; // the text for the textarea (a copy of the original when changed is false)
  original: string;
  changed: boolean;
  mode: "new" | "edit";
  workflow: "create" | "image_guided" | "guided" | "edit" | string;
  changes: { kind: EnhanceKind | string; before: string; after: string; why: string }[];
  questions: { question: string; options: string[] }[]; // an option is one sentence to append
  warnings: string[];
  model: string | null;
  seconds: number;
}

// ── ideas from trends (POST /api/trends, ../src/cbj/trends.py) ────────────────────────────────────

export interface TrendIdea {
  title: string;
  trend: string;
  category: "gaming" | "culture" | "season" | "sport" | "viral" | string;
  source: string; // a URL or a bare search term (the pasted link for a link result)
  why_now: string;
  mapping: string;
  hook: string;
  prompt: string;
}

export interface Trends {
  generated: string;
  region: string | null; // null for a link result
  link?: string; // set when the ideas came from a pasted link (SPEC-ENHANCE §2b)
  theme: string | null;
  cached: boolean;
  model: string | null;
  seconds: number;
  ideas: TrendIdea[];
  skipped: { trend: string; why: string }[];
  signals: { google: number; news: number; link?: number };
  sources: { title: string; url: string; published: string }[];
}

// ── designer feedback and the owner's lessons (../src/cbj/feedback.py, ../src/cbj/lessons.py) ─────────

export type FeedbackArea =
  | "level" | "ending" | "captions" | "tempo" | "look" | "sound" | "hud" | "hands" | "edit" | "understanding" | "speed" | "website" | "other";
export type FeedbackKind = "wrong" | "missing" | "good" | "idea";
export type FeedbackPage = "create" | "edit" | "showcase" | "general";
/** feedback.STEPS: the step of the process a note is about (the engine's stage names, plus result and other) */
export type FeedbackStep = "plan" | "level" | "recording" | "compose" | "review" | "revise" | "proof" | "result" | "other";

/** POST /api/feedback */
export interface FeedbackBody {
  area: FeedbackArea;
  kind: FeedbackKind;
  wrong: string;
  expected?: string;
  rating?: number;
  designer?: string;
  creative_id?: string;
  version?: number;
  page: FeedbackPage;
  step?: FeedbackStep;
  item?: string; // ≤200 chars: the exact thing as the page names it (a control row, a report row, a check, a caption)
}

/** What the designer was looking at, captured by the engine from the studio ({} without a creative). */
export interface FeedbackScene {
  creative_id?: string;
  version?: number;
  workflow?: string;
  prompt?: string;
  summary?: string;
  length_s?: number | null;
  created?: string;
  edit?: boolean;
  history?: { n: number; prompt: string; workflow: string }[];
}

export interface FeedbackRecord {
  id: string;
  created: string; // "2026-10-18 13:51:00"
  designer: string;
  page: FeedbackPage | string;
  area: FeedbackArea | string;
  kind: FeedbackKind | string;
  wrong: string;
  expected: string;
  rating: number | null;
  scene: FeedbackScene;
  step?: FeedbackStep | string | null; // older records have none; with a creative and no step the engine stores "result"
  item?: string | null;
  process?: Record<string, unknown>; // the engine's capture of what it did (feedback.process_of); never sent by the UI
}

/** feedback.step_evidence: the slice of the stored process a note points at. */
export interface FeedbackEvidence {
  step: string;
  words: string;
  item: string | null;
  facts: Record<string, unknown>;
  lines: { stage: string; text: string }[];
}

/** POST /api/feedback/<id>/analyze (feedback.analyze): one model call, kept by the engine. */
export interface FeedbackAnalysis {
  record: string;
  step: string;
  item: string | null;
  what_happened: string;
  why: string;
  verdict: "system" | "taste" | "unclear" | string;
  evidence: string[];
  unbacked: string[];
  suggested_change: string;
  confidence: "strong" | "thin" | string;
  model: string | null;
  seconds: number;
  created: string;
}

/** GET /api/feedback/<id> */
export type FeedbackDetail = FeedbackRecord & { evidence: FeedbackEvidence; analysis: FeedbackAnalysis | null };

/** GET /api/feedback: newest first, with the facets of the whole store. */
export interface FeedbackListing {
  count: number; // after the filters
  total: number; // the whole store
  records: FeedbackRecord[];
  designers: string[];
  areas: string[];
  kinds: string[];
  creatives: string[];
}

export interface Lesson {
  lesson: string;
  evidence: string[]; // feedback ids
  suggested_change: string;
  confidence: "strong" | "thin" | string;
}

export interface LessonsMeta {
  version: number;
  generated: string;
  records: number;
  designers: number;
  record_ids?: string[];
  corrections?: number;
  previous?: number | null;
  model?: string | null;
  seconds?: number;
  dropped?: string[];
  note?: string;
}

export interface LessonsCorrection {
  id: string;
  created: string;
  text: string;
  version_before: number | null;
}

/** GET /api/lessons[?version=N], and the answer of every POST /api/lessons action. */
export interface LessonsPackage {
  summary: string;
  workflows: { workflow: string; lessons: Lesson[] }[];
  designers: { designer: string; asks_for: string[]; phrasing: string[]; evidence: string[] }[];
  open_questions: string[];
  meta: LessonsMeta;
  markdown: string; // LESSONS.md: only for the download, never rendered
  versions: LessonsMeta[]; // oldest first
  current: number | null;
  corrections: LessonsCorrection[];
}

/** Before the first distillation. */
export interface LessonsEmpty {
  empty: true;
  versions: [];
  current: null;
  corrections: LessonsCorrection[];
}

/** "captions": every caption of the creative as it appears (the default); "hook": the hook alone (SPEC-SOUNDTRACK §6). */
export type Narration = "captions" | "hook";

/** The spoken part of a soundtrack: `text` is every line joined with " / "; `lines` say what is said and when. */
export interface SoundtrackVoice {
  text: string;
  voice: string;
  at_s: number;
  seconds: number;
  model: string;
  narration?: Narration;
  lines?: { layer: string; text: string; at_s: number; seconds: number }[];
}

/** POST /api/soundtrack (SPEC-SOUNDTRACK §1): a WAV in studio/uploads/, nothing else changed. */
export interface Soundtrack {
  file: string; // "soundtrack-<slug>-v<N>[-voice].wav": the name the music edit takes
  path: string; // "uploads/<file>", studio-relative
  creative_id: string;
  version: number;
  seconds: number;
  description: string;
  concept: {
    theme: string;
    mood: string;
    mode: string;
    bpm: number;
    bpm_ratio: number;
    curve: string;
    tempo: string;
    ending: string;
    duration_s: number;
    exits: { at_s: number; block?: string | null }[];
    hurry_ticks: number[];
  };
  voice: SoundtrackVoice | null;
  voice_skipped: string | null;
  bed?: boolean; // false: the voice over the version's own music (or silence)
  base_music?: string | null;
  made: string;
  took_s: number;
}
