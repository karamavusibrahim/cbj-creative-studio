"""Gameplay events and the satisfying finish: "first move the yellow block out of the way, then the
blue one escapes", "colour by colour", "the biggest block leaves last", "the red block gets stuck
first", "one move frees everything", as data the engine can play and check.

An event names blocks of the level and what they do, in order (other drags may come between):
- leaves: the block exits; with `all`, every named block has left before the next event;
- moves: a repositioning drag of the block ("moves out of the way");
- stuck: the block is dragged toward its gate until another block stops it (a blocked attempt,
  played as a mistake, see play.py);
- hesitates: the block is picked up and put back (play.py).
`when` "first": the video's first drag is this event; "last": this is the video's last exit.
Blocks are named by colour and `which` (any, biggest, smallest, longest), resolved on the level once
(ties: the first block in the level's order, and the brief says so).

Only leaves and moves go to the solver (solve_events): a stuck attempt depends on another block
being in the way at that moment, which a search over positions cannot promise without trying
every blocker, so play.py inserts it where the board offers one, like any planned mistake.

solve_events is an A* search over (position, events done), as solve_fast: each block still on the
board needs a drag, and each pending `moves` event a non-exit drag of its own, so
h = blocks left + pending moves never overestimates; a drag raises f = drags + h by 0 or 1, so a
0-1 breadth-first search is exact. Exits are NOT pruned to "take any open exit first" (the free
solver's shortcut): with events, an early exit can make another block's later drag exit too soon
and break the order, so the order of exits is part of the search.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .describe import color_name
from .level import MAX_GRID, BlockColor, Level
from .rules import State, initial_state, occupancy
from .solver import Drag, SolverLimitError, _with_full_path, apply_drag, drag_outcomes

ACTIONS = ("leaves", "moves", "stuck", "hesitates", "blocks")
SOLVER_ACTIONS = ("leaves", "moves")
WHEN = ("first", "next", "last")
WHICH = ("any", "biggest", "smallest", "longest")
SLOT = {"Green": BlockColor.GREEN, "Yellow": BlockColor.YELLOW, "Blue": BlockColor.BLUE, "Red": BlockColor.RED,
        "Orange": BlockColor.ORANGE, "Purple": BlockColor.PURPLE, "DarkGreen": BlockColor.DARK_GREEN}
MAX_STATES = 50_000


@dataclass(frozen=True)
class Event:
    action: str
    blocks: frozenset[int]  # the blocks it names
    all: bool = False  # leaves: every named block, before the next event
    when: str = "next"
    text: str = ""  # in words, for notes and checks
    final_only: bool = False  # only says which blocks may make the final exit (a time-out's cut-short block)
    by: frozenset[int] = frozenset()  # stuck: the blocks that may be the one in the way; blocks: the blocks it may get in the way of

    def __post_init__(self):
        if self.action not in ACTIONS:
            raise ValueError(f"event action must be one of {', '.join(ACTIONS)}, got {self.action!r}")
        if self.when not in WHEN:
            raise ValueError(f"event when must be one of {', '.join(WHEN)}, got {self.when!r}")
        if not self.blocks:
            raise ValueError(f"event {self.text or self.action!r} names no block of this level")


def _extent(level: Level, bid: int) -> int:
    offs = level.blocks[bid].offsets
    xs, ys = [o[0] for o in offs], [o[1] for o in offs]
    return max(max(xs) - min(xs), max(ys) - min(ys)) + 1


def describe_block(colour: str | None, which: str, all_: bool = False) -> str:
    c = color_name(SLOT[colour]) if colour else ""
    if all_:
        return f"all the {c} blocks".replace("  ", " ") if c else "all the blocks"
    adj = {"any": "", "biggest": "biggest ", "smallest": "smallest ", "longest": "longest "}[which]
    return f"the {adj}{c + ' ' if c else ''}block"


def describe(raw: dict) -> str:
    b = raw["block"]
    all_ = bool(b.get("all")) and raw["action"] == "leaves"
    who = describe_block(b.get("colour"), b.get("which", "any"), all_)
    verb = {"leaves": "leave" if all_ else "leaves", "moves": "moves out of the way",
            "stuck": "gets stuck", "hesitates": "is picked up and put back",
            "blocks": "is moved into another block's way"}[raw["action"]]
    when = {"first": " first", "last": " last", "next": ""}[raw.get("when", "next")]
    by = ""
    if raw.get("by") in SLOT and raw["action"] == "stuck":
        by = f" (stopped by a {color_name(SLOT[raw['by']])} block)"
    elif raw.get("by") in SLOT and raw["action"] == "blocks":
        verb = f"is moved into the {color_name(SLOT[raw['by']])} block's way"
    return f"{who} {verb}{when}{by}"


def resolve(level: Level, colour: str | None, which: str = "any", all_: bool = False) -> tuple[frozenset[int], str | None]:
    """The blocks a reference names on this level, and an assumption to report when it had to pick
    one of several (empty: nothing on the level matches)."""
    ids = [i for i, b in enumerate(level.blocks) if colour is None or b.color == SLOT[colour]]
    if not ids:
        return frozenset(), None
    if all_ or (which == "any" and len(ids) == 1):
        return frozenset(ids), None
    if which == "any":
        # "the red block" with two red blocks: either one may do it
        return frozenset(ids), None
    key = {"biggest": lambda i: -level.blocks[i].size, "smallest": lambda i: level.blocks[i].size,
           "longest": lambda i: (-_extent(level, i), -level.blocks[i].size)}[which]
    best = min(ids, key=lambda i: (key(i), i))
    ties = [i for i in ids if key(i) == key(best)]
    note = None
    if len(ties) > 1:
        adj = {"biggest": "big", "smallest": "small", "longest": "long"}[which]
        note = (f"{len(ties)} {('blocks' if not colour else color_name(SLOT[colour]) + ' blocks')} are equally "
                f"{adj}; the first of them is used")
    return frozenset({best}), note


def from_brief(level: Level, raw_events: list[dict]) -> tuple[list[Event], list[str]]:
    """The brief's events resolved on a level, and notes for any that could not be (dropped)."""
    out, notes = [], []
    for k, raw in enumerate(raw_events):
        b = raw["block"]
        text = describe(raw)
        when = raw.get("when", "next")
        if when == "first" and k > 0:
            notes.append(f"'{text}': only the first event can be the first drag; it is played in its order")
            when = "next"
        if when == "last" and (raw["action"] != "leaves" or k != len(raw_events) - 1):
            notes.append(f"'{text}': 'last' means the last exit, so only the final 'leaves' event can be last; "
                         f"it is played in its order")
            when = "next"
        if raw["action"] == "leaves" and not b.get("colour") and b.get("which", "any") == "any" and \
                (b.get("all") or when == "next"):
            notes.append(f"'{text}': every block leaves by the end anyway, so this step adds nothing to the order")
            continue
        blocks, assumption = resolve(level, b.get("colour"), b.get("which", "any"), b.get("all", False))
        if not blocks:
            notes.append(f"'{text}': this level has no such block, so the event is left out")
            continue
        if assumption:
            notes.append(f"'{text}': {assumption}")
        by = frozenset()
        if raw["action"] in ("stuck", "blocks") and raw.get("by") in SLOT:
            by, _ = resolve(level, raw["by"], "any", True)
            if not by:
                notes.append(f"'{text}': this level has no {color_name(SLOT[raw['by']])} block "
                             + ("to stop it, so any block may" if raw["action"] == "stuck" else "to get in the way of, so any block may be"))
        out.append(Event(raw["action"], blocks, bool(b.get("all")) and raw["action"] == "leaves", when,
                         describe({**raw, "when": when}), by=by))
    return out, notes


# ---------- the solver ----------

@dataclass
class EventSolution:
    drags: list[Drag]
    done_at: list[int]  # for each event, the index of the drag that did it
    states_explored: int

    @property
    def min_drags(self) -> int:
        return len(self.drags)


def _on_board(state: State, blocks) -> bool:
    return any(state[b] is not None for b in blocks)


def advance(events: list[Event], k: int, state: State, d: Drag, first: bool) -> int | None:
    """Solver events (leaves, moves) done after drag d from (state, k done), or None if d breaks
    the order."""
    after = apply_drag(state, d)
    cur = events[k] if k < len(events) else None
    nk = k
    empty = not any(p is not None for p in after)
    if cur is not None:
        if cur.final_only:
            if d.exits and empty:
                if d.block not in cur.blocks:
                    return None
                nk = k + 1
        elif cur.action == "leaves" and d.exits and d.block in cur.blocks:
            if cur.when == "last" and cur.all:
                if any(p is not None and b not in cur.blocks for b, p in enumerate(after)):
                    return None  # all of them last: only they may still be on the board
                if not _on_board(after, cur.blocks):
                    nk = k + 1
            elif cur.when == "last":
                if empty:
                    nk = k + 1  # the final exit
                elif not _on_board(after, cur.blocks):
                    return None  # the last of the named blocks left before the end
            elif not cur.all or not _on_board(after, cur.blocks):
                nk = k + 1
        elif cur.action == "moves" and not d.exits and d.block in cur.blocks and d.end != d.start:
            nk = k + 1
    if first and events and events[0].when == "first" and nk == 0:
        # the first drag has to be the first event; for "all of them leave first" it has to be
        # the first of those exits (the rest follow, nothing else leaves in between)
        ev0 = events[0]
        if not (ev0.all and ev0.action == "leaves" and d.exits and d.block in ev0.blocks):
            return None
    if d.exits:
        # An exit may not take away a block that a later event still needs.
        for j in range(nk, len(events)):
            ev = events[j]
            if ev.final_only:
                continue  # it only restricts the final exit, checked when it is current
            if j == k and ev.action == "leaves" and d.block in ev.blocks:
                continue  # one of the blocks of a current "all of them leave" event
            if d.block in ev.blocks and (ev.all or not _on_board(after, ev.blocks)):
                return None
    return nk


def impossible(events: list[Event]) -> str | None:
    """An order that cannot happen whatever the board: a block that every block of an earlier
    'leaves' step takes away, named again later."""
    for i, a in enumerate(events):
        if a.action != "leaves" or not (a.all or len(a.blocks) == 1):
            continue
        for b in events[i + 1:]:
            if b.blocks <= a.blocks:
                return f"'{b.text}' comes after '{a.text}', which has already taken that block away"
    return None


def try_solve_events(level: Level, events: list[Event], start: State | None = None, left: int = 0,
                     max_states: int = MAX_STATES) -> EventSolution | None:
    """solve_events, with None for "not found" whether the order is impossible or the search
    reached its limit (the play then goes on without the order, and says so)."""
    if impossible(events):
        return None
    try:
        return solve_events(level, events, start, left, max_states)
    except SolverLimitError:
        return None


def solve_events(level: Level, events: list[Event], start: State | None = None, left: int = 0,
                 max_states: int = MAX_STATES) -> EventSolution | None:
    """The fewest drags from `start` that do every (leaves/moves) event in order and end with
    `left` blocks on the board. None if impossible. Raises SolverLimitError past max_states."""
    if any(e.action not in SOLVER_ACTIONS for e in events):
        raise ValueError("solve_events takes leaves and moves events; stuck and hesitates are played by play.py")
    cell_limit = max(max_states, MAX_GRID * MAX_GRID)
    start = initial_state(level) if start is None else start
    n = len(events)
    moves_left = [0] * (n + 1)
    for k in range(n - 1, -1, -1):
        moves_left[k] = moves_left[k + 1] + (events[k].action == "moves")

    def h(state: State, k: int) -> int:
        return max(0, sum(p is not None for p in state) - left) + moves_left[k]

    root = (start, 0)
    g = {root: 0}
    parent: dict[tuple, tuple | None] = {root: None}
    done: set = set()
    queue: deque = deque([root])
    while queue:
        node = queue.popleft()
        if node in done:
            continue
        done.add(node)
        state, k = node
        on = sum(p is not None for p in state)
        if k == n and on == left:
            drags, cur = [], node
            while parent[cur] is not None:
                prev, d = parent[cur]
                drags.append(_with_full_path(level, prev[0], d))
                cur = prev
            drags.reverse()
            return EventSolution(drags, check_events(level, events, drags, start=start).done_at, len(g))
        if on <= left:
            continue  # blocks never come back
        occ = occupancy(level, state)
        f0 = g[node] + h(state, k)
        for bid, pivot in enumerate(state):
            if pivot is None:
                continue
            for d in drag_outcomes(level, state, bid, occ, paths=False, cell_limit=cell_limit):
                nk = advance(events, k, state, d, g[node] == 0 and state == start)
                if nk is None:
                    continue
                ns = (apply_drag(state, d), nk)
                ng = g[node] + 1
                if ns in done or g.get(ns, ng + 1) <= ng:
                    continue
                g[ns] = ng
                parent[ns] = (node, d)
                if ng + h(*ns) == f0:
                    queue.appendleft(ns)
                else:
                    queue.append(ns)
                if len(g) > max_states:
                    raise SolverLimitError(f"{level.name or 'level'}: more than {max_states} positions with events")
    return None


@dataclass
class Check:
    ok: bool
    done_at: list[int | None] = field(default_factory=list)
    problem: str = ""


def check_events(level: Level, events: list[Event], drags: list[Drag], kinds: list[str] | None = None,
                 start: State | None = None) -> Check:
    """Did these drags do the (leaves/moves) events in order? kinds: each drag's beat kind; a
    hesitation (picked up, put back) or a mistake never counts as an event (a mistake can only move
    a block, which never breaks the order). Used on the recording's drags."""
    events = [e for e in events if e.action in SOLVER_ACTIONS]
    k, state, done = 0, (initial_state(level) if start is None else start), []
    first = True
    for i, d in enumerate(drags):
        if kinds and kinds[i] in ("hesitate", "mistake"):
            if kinds[i] == "mistake" and first and events and events[0].when == "first":
                return Check(False, [None] * len(events), f"drag {i + 1} is a mistake, not '{events[0].text}'")
            state = apply_drag(state, d)
            if kinds[i] == "mistake":
                first = False
            continue
        nk = advance(events, k, state, d, first)
        first = False
        if nk is None:
            what = events[min(k, len(events) - 1)].text if events else ""
            return Check(False, done + [None] * (len(events) - len(done)),
                         f"drag {i + 1} breaks the order (at '{what}')")
        if nk > k:
            done.append(i)
        k, state = nk, apply_drag(state, d)
    if k < len(events):
        return Check(False, done + [None] * (len(events) - len(done)), f"'{events[k].text}' never happened")
    return Check(True, done)


# ---------- a satisfying finish ----------

@dataclass
class Finish:
    drags: list[Drag]
    key: int | None  # the key move: the last repositioning drag before the final run of exits
    streak: int  # exits in a row at the end, with no repositioning between them
    states_explored: int
    method: str = ""


def exit_order(level: Level, state: State) -> list[Drag] | None:
    """Every block leaves, one after another, with no repositioning; None if some block cannot.
    Removing a block never blocks another's way out, so taking any open exit is safe. The
    smallest open block goes first, so the biggest makes the last exit."""
    out = []
    while any(p is not None for p in state):
        occ = occupancy(level, state)
        opened = []
        for bid, p in enumerate(state):
            if p is None:
                continue
            ex = drag_outcomes(level, state, bid, occ, paths=True, first_exit_only=True)
            if ex and ex[0].exits:
                opened.append(ex[0])
        if not opened:
            return None
        pick = min(opened, key=lambda d: (level.blocks[d.block].size, d.block))
        out.append(pick)
        state = apply_drag(state, pick)
    return out


def trailing_exits(drags: list[Drag]) -> int:
    n = 0
    for d in reversed(drags):
        if not d.exits:
            break
        n += 1
    return n


def _path(level: Level, parent: dict, s: State) -> list[Drag]:
    drags, cur = [], s
    while parent[cur] is not None:
        prev, d = parent[cur]
        drags.append(_with_full_path(level, prev, d))
        cur = prev
    drags.reverse()
    return drags


def best_finish(level: Level, start: State | None = None, prefix_cap: int = 20_000, dp_cap: int = 30_000) -> Finish:
    """The shortest solution whose final run of exits is longest: one key move, then the blocks
    leave one after another. Never longer than the minimum.

    1. Moves first: every repositioning drag up front, then all blocks leave in a row. A search
       over repositioning drags only, at most the level's repositioning count deep.
    2. Otherwise all shortest solutions (exits in any order), keeping the longest final run.
    3. Otherwise (search limit) the solver's own solution."""
    from .solver import solve_fast
    start = initial_state(level) if start is None else start
    base = solve_fast(level, start=start)
    if base is None:
        raise ValueError(f"{level.name}: unsolvable")
    n_left = sum(p is not None for p in start)
    extra = base.min_drags - n_left
    cell_limit = max(dp_cap, MAX_GRID * MAX_GRID)
    order = exit_order(level, start)
    if order is not None:  # nothing to move: every block can leave in a row from the start
        return Finish(order, None, len(order), 1, "no repositioning needed")
    # 1. repositioning drags only, breadth first
    parent: dict[State, tuple | None] = {start: None}
    frontier = [start]
    for depth in range(1, extra + 1):
        nxt = []
        for s in frontier:
            occ = occupancy(level, s)
            for bid, p in enumerate(s):
                if p is None:
                    continue
                for d in drag_outcomes(level, s, bid, occ, paths=False, cell_limit=cell_limit):
                    if d.exits:
                        continue
                    ns = apply_drag(s, d)
                    if ns in parent:
                        continue
                    parent[ns] = (s, d)
                    if depth == extra:
                        order = exit_order(level, ns)
                        if order is not None:
                            drags = _path(level, parent, ns)
                            return Finish(drags + order, len(drags) - 1, len(order), len(parent),
                                          "every repositioning drag first")
                    nxt.append(ns)
                    if len(parent) > prefix_cap:
                        break
        frontier = nxt
        if len(parent) > prefix_cap:
            break
    # 2. every shortest solution, exits in any order
    try:
        return _finish_dp(level, start, base.min_drags, dp_cap)
    except SolverLimitError:
        return Finish(list(base.drags), None, trailing_exits(base.drags), dp_cap, "the solver's own (search limit)")


def _finish_dp(level: Level, start: State, bound: int, cap: int) -> Finish:
    cell_limit = max(cap, MAX_GRID * MAX_GRID)
    g = {start: 0}
    parent: dict[State, tuple | None] = {start: None}
    queue = deque([start])
    best = None  # (streak, state)
    while queue:
        s = queue.popleft()
        n_left = sum(p is not None for p in s)
        last = parent[s][1] if parent[s] else None
        if (last is None or not last.exits) and n_left and (best is None or n_left > best[0]):
            if exit_order(level, s) is not None:
                best = (n_left, s)
        occ = occupancy(level, s)
        for bid, pivot in enumerate(s):
            if pivot is None:
                continue
            for d in drag_outcomes(level, s, bid, occ, paths=False, cell_limit=cell_limit):
                ns = apply_drag(s, d)
                ng = g[s] + 1
                if ns in g or ng + sum(p is not None for p in ns) > bound:
                    continue
                g[ns] = ng
                parent[ns] = (s, d)
                queue.append(ns)
                if len(g) > cap:
                    raise SolverLimitError("finish search limit")
    if best is None:
        raise SolverLimitError("no finish found")
    _, s = best
    drags = _path(level, parent, s)
    order = exit_order(level, s)
    return Finish(drags + order, (len(drags) - 1) if drags else None, len(order), len(g), "all shortest solutions")
