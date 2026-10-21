"""The three agentic workflows of the tool, kept apart so a change to one cannot touch the others
(2026-10-16):

- create.py: creative generation from the text alone. A prompt (with, at most, pictures to place)
  becomes a new creative: plan, level, play, ad, the viewer's review, then the loop (evaluate against
  the request, feed the misses back, make a revised take, up to create.MAX_REVISIONS rounds). Its
  evaluation is the text-to-creative profile (audit.workflow: the board, the play, the rules, every
  fact the prompt asks for, the brief's rows).
- guided.py: guided creative generation: a prompt plus media (a reference video, or a reference
  image) becomes a new creative (core requirements 3 and 4). The prompt drives the reading and wins
  over the reference wherever it states a value; the media is what gets read: for a video, the
  reading plan from the planner's model, the format step, the whole clip read by NVIDIA's
  multimodal model with the composed prompt, the checks in code, the parts snapped to cuts when
  needed (reference.read_video); for an image, its palette and description. Then the planner plans
  and code applies what each reference gives (imageref.apply, videoref.apply). make and the loop run
  the shared engine as create.py does; its evaluation adds the reference rows (audit.reference_rows)
  to the text-to-creative profile, and their misses are fed back too.
- edit.py: controlled editing of an existing creative. A request and a version become a new version
  of that creative: the route (route.py, from the version's parts manifest), a direct edit in code or
  the planner with the route, the edit report (what changed, what was kept), the viewer's review, and
  its own loop (the edit report's broken keeps and the facts the edit asked for, fed back). Its
  evaluation is the edit profile.

app.py only dispatches, on the uploads and the prompt's words together (app.workflow_of): a request
that names a creative, or attaches one of the tool's own videos with words that ask to change it,
is an edit; a new creative with a video attached, or with an image the words make a reference
(reference.is_reference_prompt), is guided; a prompt alone is a creation. One of the tool's own
videos with words that ask for a new creative from it ("a version of this concept":
route.upload_intent) is guided. The shared engine underneath (planner, studio, audit, review) is
the same; the orchestration, the feedback and the revision policy are not.

A fourth workflow (2026-10-17, core requirement 3, rules I1-I16 in REQ3-IMAGE-GUIDED-RULES-2026-10-17.md):
- image_guided.py: image-guided creative generation. A prompt plus a reference picture (no video) becomes a new
  creative: the picture is read once whole and its board on its own (imageread: the video path's reader and board
  read, the picture as the still, the palette and the caption colours measured in code), the role is decided from
  the words and the reading (imageplan.decide: style, board, asset, modify), the planner plans from the words, and
  code applies exactly what the roles allow (imageplan.apply: the board part by part with every clamp said, the
  colours to the game's seven rendered slots, the measured look, never the picture's pixels, cells or caption words).
  make and the loop run the shared engine as guided.py does (its helpers imported, not copied); its evaluation adds
  the image rows (imageaudit.rows) to the text-to-creative profile, their misses fed back, the best version kept.
  app.workflow_of sends a new request here when a picture and no video is attached and the words make it a
  reference (image_guided.applies: "inspired by this image", "take the board from this screenshot", "as crowded as
  this one"); a video still goes to guided.py, a picture only to place to create.py, an edit to edit.py.

Common to all four (2026-10-19, after the four test sets of the day; each lesson was learnt in one workflow and holds in
every one, so each workflow now does it, importing the helper rather than copying it):
- the request is translated once (image_guided.english_prompt) because the route, the asked-facts parsers and the rows
  read English; the original and the translation are kept in the brief (planner.prompt_original / prompt_english);
- the game's rules are measured on every version (audit.rows: doors and colours, colours that tell apart, the level, the
  moves, the clock, the result) and the shared case rows (blocks left at the cut, the end card is a card, a real choice);
- the loop keeps the best version, not the last (guided.best_version), keeps every value the request states
  (guided.keep_stated, create.keep_asked), never plans a longer play for a take that ran over (guided.length_guard),
  makes no version when a viewer-only remark changes nothing the viewer pointed at (guided.viewer_points), and stops when
  the same row misses twice with the same measure (image_guided.repeated_miss: the board's limit, said);
- a fixed board (copied from a picture or a video) has the play it has: the plan says at plan time when the stated length
  cannot hold it or leaves a long card (videoref.copied_board_pace), and the loop does not try to shorten it;
- a time-out ends with one block, said in the plan when more are asked (create.time_out_limit);
- every version keeps the engine's lines (app._keep_log), so feedback can be analysed step by step and a report written.
"""