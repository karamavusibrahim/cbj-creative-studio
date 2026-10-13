using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using DG.Tweening;
using UnityEngine;
using UnityEngine.UI;
using Debug = UnityEngine.Debug;

// Plays a solver move script in the real game and records it as a portrait video.
//
// It does nothing unless the player starts with "-cbjJob <job.json>" (or CBJ_JOB is set),
// so normal play is unchanged. Each drag goes through the game's own movement, grid and exit
// services once per frame, the same calls InputHandler makes for a mouse drag. Time runs on a
// fixed step (Time.captureDeltaTime), so the same job gives the same frames on every run.

[Serializable]
public class RenderCell
{
    public int x;
    public int y;
}

[Serializable]
public class RenderDrag
{
    public int block;
    public List<RenderCell> path = new List<RenderCell>();
    public bool exits;
    public int exit_index = -1; // which gate, from the script (for the compositor)
    public float pause_before_s = 0.4f;
    public float pickup_s = 0.12f;
    public float cells_per_s = 6f;
    public float push_cells; // after the last cell, press on this far (0-0.45 cells), e.g. into a blocker
    public int push_dx; // push direction in cells; 0, 0 = the way the path last moved
    public int push_dy;
    public float hold_s; // keep the finger down at the end before letting go
}

[Serializable]
public class CameraKey
{
    public float t; // seconds from the first recorded frame
    public float zoom = 1f; // 1 = the game's own framing, 2 = twice as close
    public float pan_x; // look-at point shift in cells, + is right
    public float pan_y; // look-at point shift in cells, + is up the board
}

[Serializable]
public class RenderCamera
{
    public float zoom = 1f;
    public float pan_x;
    public float pan_y;
    public List<CameraKey> keys = new List<CameraKey>(); // if set, overrides zoom/pan; eased between keys
}

[Serializable]
public class BlockLook
{
    public string slot; // the game's colour, as BlockColor names it: "Red", "DarkGreen", ...
    public string hex; // the colour to show it in, "#RRGGBB"
}

// How the game looks: the recorder repaints the game's own materials at run time, before the
// board is built. The puzzle (colour slots, gates, rules) is unchanged; only the look changes.
[Serializable]
public class RenderVisuals
{
    public List<BlockLook> blocks = new List<BlockLook>(); // block, gate and exit-particle colour per slot
    public string grid = ""; // the cells' colour, "" = the game's
    public string background_top = ""; // the ground gradient, "" = the game's
    public string background_bottom = "";
}

[Serializable]
public class RenderJob
{
    public string level_path;
    public int level_label = 1;
    public string out_dir;
    public string ffmpeg = "ffmpeg";
    public string video_name = "gameplay.mp4";
    public int fps = 30;
    public int width = 1080;
    public int height = 1920;
    public int msaa = 4;
    public int crf = 16;
    public bool frame_hashes = true;
    public bool capture = true; // false: a dry run for timing; the game plays, nothing is filmed
    public float start_hold_s = 1f;
    public float end_hold_s = 2f;
    public float max_seconds = 120f;
    public RenderCamera camera = new RenderCamera();
    public int timer_s = -1; // overrides the level's timerCount when 0 or more
    // The stock game keeps its clock running during the last block's exit slide and counts the
    // win only when the slide ends, so time can run out after the level is solved: it then shows
    // "Out of Time!" followed by "Level Completed". The game patch (unity/game-patch) fixes this in
    // the game. On a game without the patch, this makes the recorder stop the clock itself when
    // the last block starts to leave; false records the stock behaviour.
    public bool stop_clock_on_last_exit = true;
    public List<string> hide = new List<string>(); // GameObjects to hide by name, e.g. "RestartButton"
    public RenderVisuals visuals = new RenderVisuals();
    public string end_mode = "win"; // "win": wait for the win screen; "cut": stop after the last drag;
                                    // "fail": wait for the timer to run out
    public List<RenderDrag> drags = new List<RenderDrag>();
}

[Serializable]
public class DragRecord
{
    public int index;
    public int block;
    public bool planned_exit;
    public int exit_index = -1;
    public int start_frame;
    public int exit_frame = -1;
    public int end_frame = -1;
    public float timer_start;
    public float timer_end;
    public List<RenderCell> cells = new List<RenderCell>(); // pivot cells entered, in order
    public List<int> cell_frames = new List<int>(); // the frame on which each of those cells was entered
    public string result; // "exit", "placed", or what went wrong
}

[Serializable]
public class RenderResult
{
    public string status; // cleared, unresolved, failed, mismatch, timeout, error
    public string message = "";
    public string end_mode;
    public int frames;
    public int fps;
    public int width;
    public int height;
    public float duration_s;
    public int first_touch_frame = -1;
    public int clock_stopped_frame = -1; // the last block started to leave and the clock stopped
    public bool game_patched; // the build includes the game patch (the game stops its own clock)
    public bool captured = true; // false for a dry run (no video, no stills, no hashes)
    public int win_frame = -1;
    public int fail_frame = -1;
    public float timer_start;
    public float timer_end;
    public string video;
    public List<string> stills = new List<string>();
    public List<DragRecord> drags = new List<DragRecord>();
    public List<int> block_gone_frames = new List<int>(); // per block: first frame without it, or -1
    public List<UiRect> ui_rects = new List<UiRect>(); // HUD parts in video pixels, for caption safe zones
}

[Serializable]
public class UiRect
{
    public string name;
    public float x; // left, pixels from the left
    public float y; // top, pixels from the top
    public float w;
    public float h;
}

[Serializable]
public class FrameRecord
{
    public int frame;
    public float timer;
    public bool finger;
    public float finger_x; // pixels from the left of the video
    public float finger_y; // pixels from the top of the video
    public List<float> blocks = new List<float>(); // x, y per block (its pivot) in video pixels; -1, -1 once gone
    public string hash; // MD5 of the raw RGBA frame
}

[Serializable]
public class FrameLog
{
    public List<FrameRecord> frames = new List<FrameRecord>();
}

public class CreativeRunner : MonoBehaviour
{
    const float SettleEps = 0.02f; // fraction of a cell
    const float ExitSnapSeconds = 0.1f; // InputHandler.HandleExitDuringDrag

    static RenderJob job;
    static string bootError;

    readonly RenderResult result = new RenderResult();
    readonly FrameLog frameLog = new FrameLog();

    IGridManager grid;
    MovementSettings ms;
    float outlineWidth;
    IBlockMovementService movement;
    IBlockGridService gridService;
    ExitService exitService;
    FieldInfo remainingTimeField;
    FieldInfo timerRunningField;
    bool gameStopsClock;
    bool lastExitStarted;
    readonly HashSet<Block> leaving = new HashSet<Block>();
    FailMenu failMenu;
    Camera cam;
    readonly List<Block> blocks = new List<Block>();

    RenderTexture rt;
    Texture2D readTex;
    byte[] buffer;
    MD5 md5;
    Process ffmpeg;
    Stream ffmpegIn;

    int frame; // frames written so far
    bool boardReady;
    string visualsError;
    bool scriptDone;
    bool finished;
    bool fingerDown;
    float camSpacing;
    float camBaseDist;
    float camBaseSize;
    Vector3 camBasePos;
    string captureError;
    int doneFrames;
    Vector3 finger;
    bool exitTriggered;
    bool exitPerformed;
    readonly Dictionary<int, string> stillAt = new Dictionary<int, string>();
    readonly HashSet<int> seededParticles = new HashSet<int>();
    Coroutine main;

    // ---------- boot ----------

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
    static void BeforeSceneLoad()
    {
        string path = ArgValue("-cbjJob") ?? Environment.GetEnvironmentVariable("CBJ_JOB");
        if (string.IsNullOrEmpty(path)) return;
        try
        {
            job = JsonUtility.FromJson<RenderJob>(File.ReadAllText(path));
            if (job == null) throw new Exception("job file is empty");
            if (string.IsNullOrEmpty(job.out_dir)) throw new Exception("job has no out_dir");
            Directory.CreateDirectory(job.out_dir);
            CheckJob(job);
            var level = JsonUtility.FromJson<LevelData>(File.ReadAllText(job.level_path));
            if (level == null || level.gridWidth < 1 || level.gridHeight < 1)
                throw new Exception("level file has no grid: " + job.level_path);
            if (job.timer_s >= 0) level.timerCount = job.timer_s;
            LevelManager.EditorTestLevelData = level;
            PlayerPrefs.SetInt("Editor_IsTesting", 0);
        }
        catch (Exception e)
        {
            bootError = "job " + path + ": " + e.Message;
            if (job == null) job = new RenderJob();
        }
        Application.runInBackground = true;
        QualitySettings.vSyncCount = 0;
        Application.targetFrameRate = -1;
        Time.captureDeltaTime = 1f / Mathf.Max(1, job.fps);
        UnityEngine.Random.InitState(1234);
    }

    // cbj's make_job is the main gate; this only stops a hand-written job from being half-played.
    static void CheckJob(RenderJob j)
    {
        if (j.fps < 1 || j.fps > 120) throw new Exception($"fps must be 1-120, got {j.fps}");
        if (j.width < 16 || j.height < 16 || j.width % 2 != 0 || j.height % 2 != 0)
            throw new Exception($"size must be even and at least 16x16, got {j.width}x{j.height}");
        if (j.end_mode != "win" && j.end_mode != "cut" && j.end_mode != "fail")
            throw new Exception($"end_mode must be win, cut or fail, got '{j.end_mode}'");
        if (j.drags == null || j.drags.Count == 0) throw new Exception("the job has no drags");
        if (j.timer_s < -1) throw new Exception($"timer_s must be -1 (use the level's) or 0 and up, got {j.timer_s}");
        if (j.hide == null) j.hide = new List<string>();
        if (j.visuals == null) j.visuals = new RenderVisuals();
        if (j.visuals.blocks == null) j.visuals.blocks = new List<BlockLook>();
        foreach (var b in j.visuals.blocks)
            if (!Enum.TryParse(b.slot, out BlockColor _) || !ColorUtility.TryParseHtmlString(b.hex, out Color _))
                throw new Exception($"visuals: block colour '{b.slot}' = '{b.hex}' needs a BlockColor name and #RRGGBB");
        foreach (var hex in new[] { j.visuals.grid, j.visuals.background_top, j.visuals.background_bottom })
            if (!string.IsNullOrEmpty(hex) && !ColorUtility.TryParseHtmlString(hex, out Color _))
                throw new Exception($"visuals: '{hex}' is not a #RRGGBB colour");
        if (j.camera == null) j.camera = new RenderCamera();
        if (!Positive(j.camera.zoom) || !Finite(j.camera.pan_x) || !Finite(j.camera.pan_y))
            throw new Exception("camera zoom must be positive and pans finite");
        for (int k = 0; k < j.camera.keys.Count; k++)
        {
            var key = j.camera.keys[k];
            if (!NonNegative(key.t) || !Positive(key.zoom) || !Finite(key.pan_x) || !Finite(key.pan_y))
                throw new Exception($"camera key {k + 1}: t must be zero or more, zoom positive, pans finite");
            if (k > 0 && key.t <= j.camera.keys[k - 1].t)
                throw new Exception("camera keys must be in increasing time order");
        }
        if (!NonNegative(j.start_hold_s) || !NonNegative(j.end_hold_s) || !(j.max_seconds > 0f))
            throw new Exception("start_hold_s and end_hold_s must be zero or more, max_seconds positive");
        for (int i = 0; i < j.drags.Count; i++)
        {
            var d = j.drags[i];
            if (d.path == null || d.path.Count == 0) throw new Exception($"drag {i + 1} has an empty path");
            if (!NonNegative(d.pause_before_s) || !NonNegative(d.pickup_s))
                throw new Exception($"drag {i + 1}: pause_before_s and pickup_s must be zero or more");
            if (!(d.cells_per_s > 0f) || d.cells_per_s > j.fps / 2f)
                throw new Exception($"drag {i + 1}: cells_per_s must be above 0 and at most fps/2 ({j.fps / 2f})");
            // Past 0.5 cells the pivot would round into the next cell, which the script did not plan.
            if (!NonNegative(d.hold_s) || !NonNegative(d.push_cells) || d.push_cells > 0.45f)
                throw new Exception($"drag {i + 1}: hold_s must be zero or more and push_cells 0 to 0.45");
            bool dir = Mathf.Abs(d.push_dx) + Mathf.Abs(d.push_dy) == 1;
            if (d.push_dx != 0 || d.push_dy != 0 ? !dir : false)
                throw new Exception($"drag {i + 1}: push_dx, push_dy must be one step along an axis");
            if (d.push_cells > 0f && (d.exits || (d.path.Count < 2 && !dir)))
                throw new Exception($"drag {i + 1}: push_cells needs a drag that does not exit, and a direction "
                                    + "(a path that moves, or push_dx/push_dy)");
        }
    }

    static bool NonNegative(float v) => v >= 0f && !float.IsInfinity(v);
    static bool Positive(float v) => v > 0f && !float.IsInfinity(v);
    static bool Finite(float v) => !float.IsNaN(v) && !float.IsInfinity(v);

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void AfterSceneLoad()
    {
        if (job == null) return;
        var go = new GameObject("CreativeRunner");
        DontDestroyOnLoad(go);
        go.AddComponent<CreativeRunner>();
    }

    void Awake()
    {
        Application.logMessageReceived += OnLog;
        // The script replaces the mouse and owns the camera.
        var input = FindFirstObjectByType<InputHandler>(FindObjectsInactive.Include);
        if (input != null)
        {
            ms = GetField<MovementSettings>(input, "movementSettings");
            outlineWidth = input.outlineWidth;
            input.enabled = false;
        }
        var cc = FindFirstObjectByType<CameraController>(FindObjectsInactive.Include);
        if (cc != null) cc.enabled = false;
        if (GameManager.Instance != null)
            GameManager.Instance.OnBoardGenerated += () => boardReady = true;
        RepaintBeforeBoard();
        if (LevelManager.Instance != null)
            LevelManager.Instance.OnLevelCompleted += _ => { if (result.win_frame < 0) result.win_frame = frame; };
    }

    // Before the board is built (GameManager.Start): the block, gate and particle materials and the
    // grid colours. Blocks and gates copy these shared materials when they spawn, so changing the
    // shared assets here (process-local in a player) repaints every instance.
    void RepaintBeforeBoard()
    {
        var v = job.visuals;
        if (v.blocks.Count > 0)
        {
            var factory = FindFirstObjectByType<ItemFactory>(FindObjectsInactive.Include);
            if (factory == null) { visualsError = "visuals: no ItemFactory, so block colours cannot be set"; return; }
            foreach (var look in v.blocks)
            {
                var slot = (BlockColor)Enum.Parse(typeof(BlockColor), look.slot);
                ColorUtility.TryParseHtmlString(look.hex, out Color c);
                foreach (var bd in factory.blockDataList)
                {
                    if (bd == null || bd.blockColor != slot) continue;
                    var seen = new HashSet<Material>(); // DarkGreen's particles use its gate material
                    foreach (var m in new[] { bd.colorMaterial, bd.exitMaterial, bd.particleMaterial })
                        if (m != null && seen.Add(m) && m.HasProperty("_Color")) m.SetColor("_Color", c);
                }
            }
        }
        if (!string.IsNullOrEmpty(v.grid) && GameManager.Instance != null)
        {
            ColorUtility.TryParseHtmlString(v.grid, out Color g);
            for (int i = 0; i < GameManager.Instance.gridColors.Count; i++) GameManager.Instance.gridColors[i] = g;
        }
    }

    // After the board is built: the cells' second sprite (not driven by code) and the ground.
    void RepaintAfterBoard()
    {
        var v = job.visuals;
        if (!string.IsNullOrEmpty(v.grid))
        {
            ColorUtility.TryParseHtmlString(v.grid, out Color g);
            Color back = Color.Lerp(g, Color.black, 0.18f);
            foreach (var sr in FindObjectsByType<SpriteRenderer>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                if (sr.name == "CellBackground") sr.color = back;
        }
        if (!string.IsNullOrEmpty(v.background_top))
        {
            var ground = GameObject.Find("Ground");
            var mr = ground != null ? ground.GetComponent<MeshRenderer>() : null;
            if (mr == null) { visualsError = "visuals: no Ground object, so the background cannot be set"; return; }
            ColorUtility.TryParseHtmlString(v.background_top, out Color top);
            Color bottom = top;
            if (!string.IsNullOrEmpty(v.background_bottom)) ColorUtility.TryParseHtmlString(v.background_bottom, out bottom);
            // The game's GroundGradient2.png runs white at the top to light blue at the bottom of the
            // texture; a 4x256 texture in the same orientation replaces it.
            var tex = new Texture2D(4, 256, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
            for (int y = 0; y < 256; y++)
            {
                Color c = Color.Lerp(bottom, top, y / 255f);
                for (int x = 0; x < 4; x++) tex.SetPixel(x, y, c);
            }
            tex.Apply();
            var mat = mr.material;
            mat.mainTexture = tex;
            mat.color = Color.white;
        }
    }

    // Safety net: if the capture loop has died, the script still ends with result.json.
    void Update()
    {
        if (!scriptDone || finished) return;
        if (++doneFrames > 10) Finish();
    }

    void OnDestroy()
    {
        Application.logMessageReceived -= OnLog;
    }

    void OnLog(string condition, string stack, LogType type)
    {
        if (type != LogType.Exception || scriptDone) return;
        SetStatus("error", condition);
        scriptDone = true;
    }

    // ---------- main script ----------

    IEnumerator Start()
    {
        main = null;
        if (bootError != null)
        {
            SetStatus("error", bootError);
            Finish();
            yield break;
        }
        int guard = 0;
        while (!boardReady && guard++ < 600) yield return null;
        string setupError;
        try
        {
            setupError = boardReady ? Setup() : "the board was never generated";
        }
        catch (Exception e)
        {
            setupError = "setup failed: " + e;
        }
        if (setupError != null)
        {
            SetStatus("error", setupError);
            Finish();
            yield break;
        }
        StartCoroutine(CaptureLoop());
        main = StartCoroutine(Script());
    }

    IEnumerator Script()
    {
        Still(0, "00_start.png");
        yield return Hold(job.start_hold_s);
        for (int i = 0; i < job.drags.Count && result.status == null; i++)
        {
            yield return Hold(job.drags[i].pause_before_s);
            if (result.status != null) break;
            yield return RunDrag(i, job.drags[i]);
        }
        if (result.status == null)
        {
            if (job.end_mode == "cut")
            {
                yield return Hold(job.end_hold_s);
                SetStatus(result.win_frame >= 0 ? "cleared" : "unresolved", "");
            }
            else
            {
                // "win" waits for the win screen, "fail" for the timer to run out.
                int limit = Mathf.RoundToInt(job.max_seconds * job.fps);
                while (result.win_frame < 0 && result.status == null && frame < limit) yield return null;
                if (result.win_frame >= 0) SetStatus("cleared", "");
                else SetStatus("timeout", job.end_mode == "fail"
                    ? "the timer did not run out" : "no win screen after the last drag");
                yield return HoldPlain(job.end_hold_s);
            }
        }
        else
        {
            // Keep the fail screen (or the state that went wrong) on screen.
            yield return HoldPlain(result.status == "failed" ? job.end_hold_s : 0.5f);
        }
        scriptDone = true;
    }

    IEnumerator RunDrag(int index, RenderDrag d)
    {
        var rec = new DragRecord
        {
            index = index,
            block = d.block,
            planned_exit = d.exits,
            exit_index = d.exit_index,
            start_frame = frame,
            timer_start = Timer(),
        };
        result.drags.Add(rec);
        Still(frame, $"{index + 1:00}_drag.png");

        if (d.path == null || d.path.Count == 0)
        {
            Mismatch(rec, "empty path");
            yield break;
        }
        if (d.block < 0 || d.block >= blocks.Count || blocks[d.block] == null)
        {
            Mismatch(rec, $"block {d.block} is not on the board");
            yield break;
        }
        Block b = blocks[d.block];
        Vector2Int start = ToCell(d.path[0]);
        if (Pivot(b) != start)
        {
            Mismatch(rec, $"block {d.block} is at {Pivot(b)}, the script expects {start}");
            yield break;
        }
        for (int i = 0; i < d.path.Count; i++)
        {
            Vector2Int c = ToCell(d.path[i]);
            if (!grid.IsInBounds(c.x, c.y) || !grid.IsCellActive(c.x, c.y))
            {
                Mismatch(rec, $"path cell ({c.x},{c.y}) is not an active cell on the board");
                yield break;
            }
            Vector2Int step = i > 0 ? c - ToCell(d.path[i - 1]) : Vector2Int.right;
            if (Mathf.Abs(step.x) + Mathf.Abs(step.y) != 1)
            {
                Mismatch(rec, $"path step {i} is not to a neighbouring cell");
                yield break;
            }
        }

        // Pick up (InputHandler.PickupBlock).
        if (result.first_touch_frame < 0)
        {
            result.first_touch_frame = frame;
            result.timer_start = Timer();
        }
        GameManager.Instance.StartTimer();
        float initialY = b.transform.position.y;
        SetOutline(b, true);
        b.transform.DOMoveY(initialY + ms.liftHeight, ms.liftDuration).SetEase(Ease.OutBack);
        finger = CellWorld(start);
        fingerDown = true;
        exitTriggered = false;
        exitPerformed = false;

        for (int f = 0; f < Frames(d.pickup_s) && result.status == null; f++)
        {
            Step(b, initialY, rec);
            yield return null;
        }

        // Drag one cell at a time; stop at corners until the block has caught up, so the pivot
        // walks the same 4-neighbour path the solver planned.
        int framesPerCell = Mathf.Max(1, Mathf.RoundToInt(job.fps / Mathf.Max(0.1f, d.cells_per_s)));
        for (int i = 1; i < d.path.Count && !exitTriggered && result.status == null; i++)
        {
            Vector3 from = CellWorld(ToCell(d.path[i - 1]));
            Vector3 to = CellWorld(ToCell(d.path[i]));
            // Every loop stops at the fail screen, so a block cannot move on (or exit) after it.
            for (int f = 1; f <= framesPerCell && result.status == null; f++)
            {
                finger = Vector3.Lerp(from, to, (float)f / framesPerCell);
                if (Step(b, initialY, rec)) break;
                yield return null;
            }
            bool corner = i == d.path.Count - 1 || Turns(d.path, i);
            int settle = 0;
            while (corner && !exitTriggered && result.status == null
                   && Flat(b.transform.position - to) > SettleEps * grid.CellSpacing && settle++ < job.fps * 2)
            {
                if (Step(b, initialY, rec)) break;
                yield return null;
            }
        }

        // Press on past the last cell, as a player pushes a block against the one in its way. The
        // game stops the block at the blocker (BlockMovementService), so its cell does not change.
        if (d.push_cells > 0f && !exitTriggered && result.status == null)
        {
            Vector2Int endCell = ToCell(d.path[d.path.Count - 1]);
            Vector2Int step = d.push_dx != 0 || d.push_dy != 0 ? new Vector2Int(d.push_dx, d.push_dy)
                : endCell - ToCell(d.path[d.path.Count - 2]);
            // Grid x is world +X and grid y world +Z (BlockMovementService.IsPositionValid).
            Vector3 last = CellWorld(endCell);
            Vector3 pushed = last + new Vector3(step.x, 0f, step.y) * (d.push_cells * grid.CellSpacing);
            int n = Mathf.Max(1, Mathf.RoundToInt(d.push_cells * framesPerCell));
            for (int f = 1; f <= n && result.status == null; f++)
            {
                finger = Vector3.Lerp(last, pushed, (float)f / n);
                if (Step(b, initialY, rec)) break;
                yield return null;
            }
        }
        for (int f = 0; f < Frames(d.hold_s) && !exitTriggered && result.status == null; f++)
        {
            if (Step(b, initialY, rec)) break;
            yield return null;
        }

        fingerDown = false;
        if (exitTriggered)
        {
            rec.exit_frame = frame;
            int wait = 0;
            while (!exitPerformed && wait++ < job.fps) yield return null;
            rec.result = "exit";
            if (lastExitStarted && gameStopsClock && ClockRunning() && result.status == null)
                Mismatch(rec, "the game did not stop the clock when the last block started to leave");
        }
        else
        {
            // Release (InputHandler.ReleaseBlock).
            Vector2Int g = Pivot(b);
            gridService.UpdateBlockPosition(b, g);
            SetOutline(b, false);
            b.transform.DOMove(grid.GetCell(g.x, g.y).transform.position, ms.snapDuration).SetEase(Ease.OutQuad);
            for (int f = 0; f < Frames(ms.snapDuration); f++) yield return null;
            rec.result = "placed";
        }

        rec.end_frame = frame;
        rec.timer_end = Timer();
        if (result.status != null)
        {
            // The fail screen (or a stop) cut the drag short; there is nothing to compare.
            if (!exitTriggered) rec.result = "interrupted";
            yield break;
        }

        // Did the game do what the solver planned?
        var planned = d.path.GetRange(1, d.path.Count - 1);
        if (!SameCells(rec.cells, planned))
            Mismatch(rec, $"block {d.block} entered {CellsText(rec.cells)}, the script planned {CellsText(planned)}");
        else if (d.exits && !exitTriggered)
            Mismatch(rec, $"block {d.block} did not exit at {CellsText(planned)}");
        else if (!d.exits && exitTriggered)
            Mismatch(rec, $"block {d.block} exited, the script did not plan an exit");
    }

    // One frame of InputHandler.DragBlock with the finger in place of the mouse.
    bool Step(Block b, float initialY, DragRecord rec)
    {
        if (exitTriggered) return true;
        Vector3 current = b.transform.position;
        Vector3 target = new Vector3(finger.x, initialY, finger.z);
        Vector3 next = movement.CalculateMovement(b, current, target);
        next.y = initialY + ms.liftHeight;
        b.transform.position = Vector3.Lerp(current, next, Time.deltaTime * ms.dragSpeed);

        Vector2Int g = gridService.WorldToGridPosition(b.transform.position);
        if (g == Pivot(b)) return false;
        gridService.UpdateBlockPosition(b, g);
        rec.cells.Add(new RenderCell { x = g.x, y = g.y });
        rec.cell_frames.Add(frame);
        if (!exitService.CanBlockExit(b, g)) return false;

        // InputHandler.HandleExitDuringDrag: snap to the cell, then the game's exit animation.
        exitTriggered = true;
        leaving.Add(b);
        if (result.status == null)
        {
            bool last = true;
            foreach (var other in blocks)
                if (other != null && !leaving.Contains(other)) last = false;
            if (last)
            {
                lastExitStarted = true;
                // The patched game stops its own clock in ExitService.PerformExit after the snap.
                if (job.stop_clock_on_last_exit && !gameStopsClock)
                    timerRunningField.SetValue(GameManager.Instance, false);
            }
        }
        Vector3 snap = grid.GetCell(g.x, g.y).transform.position;
        snap.y = initialY;
        SetOutline(b, false);
        b.transform.DOMove(snap, ExitSnapSeconds).SetEase(Ease.OutQuad).OnComplete(() =>
        {
            exitService.PerformExit(b);
            exitPerformed = true;
        });
        return true;
    }

    IEnumerator Hold(float seconds)
    {
        int n = Frames(seconds);
        for (int f = 0; f < n && result.status == null; f++) yield return null;
    }

    IEnumerator HoldPlain(float seconds)
    {
        int n = Frames(seconds);
        for (int f = 0; f < n; f++) yield return null;
    }

    // ---------- setup ----------

    string Setup()
    {
        if (LevelManager.Instance == null || LevelManager.Instance.CurrentLevelData != LevelManager.EditorTestLevelData)
            return "the game did not load the job's level";
        if (ms == null) return "InputHandler or its MovementSettings not found";
        grid = GameManager.Instance.GridManager;
        movement = new BlockMovementService(grid, ms);
        gridService = new BlockGridService(grid);
        exitService = new ExitService(grid, GameManager.Instance);
        remainingTimeField = typeof(GameManager).GetField("remainingTime", BindingFlags.Instance | BindingFlags.NonPublic);
        timerRunningField = typeof(GameManager).GetField("isTimerRunning", BindingFlags.Instance | BindingFlags.NonPublic);
        gameStopsClock = typeof(GameManager).GetMethod("OnBlockExitStarted") != null;
        result.game_patched = gameStopsClock;
        if (timerRunningField == null) return "GameManager.isTimerRunning not found";
        failMenu = FindFirstObjectByType<FailMenu>(FindObjectsInactive.Include);
        cam = Camera.main;
        if (cam == null) return "no main camera";

        // Solver block i = GridBlockDatas[i]; find it by its starting pivot.
        var level = LevelManager.EditorTestLevelData;
        var onBoard = FindObjectsByType<Block>(FindObjectsSortMode.None);
        foreach (var data in level.GridBlockDatas)
        {
            Block match = null;
            foreach (var b in onBoard)
                if (b.parentCell != null && Pivot(b) == data.gridPosition) match = b;
            if (match == null) return $"no block spawned at {data.gridPosition}";
            blocks.Add(match);
        }

        if (UIManager.Instance != null) UIManager.Instance.UpdateLevel(job.level_label);
        foreach (string entry in job.hide)
        {
            // "Name" hides the object and its children; "Name:image" hides only the object's own
            // graphic (its children stay), e.g. the HUD bar's panel without the Level badge on it.
            bool graphicOnly = entry.EndsWith(":image");
            string name = graphicOnly ? entry.Substring(0, entry.Length - 6) : entry;
            bool found = false;
            foreach (var t in FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (t.name != name) continue;
                if (graphicOnly)
                {
                    foreach (var g in t.GetComponents<UnityEngine.UI.Graphic>()) g.enabled = false;
                }
                else t.gameObject.SetActive(false);
                found = true;
            }
            if (!found) return $"hide: no object named '{name}'";
        }
        for (int i = 0; i < blocks.Count; i++) result.block_gone_frames.Add(-1);
        // Button colour fades run on real time (Graphic.CrossFadeColor ignores the time scale),
        // so a fade caught mid-way differs between runs. Make them instant.
        foreach (var sel in FindObjectsByType<Selectable>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            var colors = sel.colors;
            colors.fadeDuration = 0f;
            sel.colors = colors;
        }
        RepaintAfterBoard();
        if (visualsError != null) return visualsError;
        FitCamera();
        AttachCanvases();
        SeedParticles();

        rt = new RenderTexture(job.width, job.height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB)
        {
            antiAliasing = Mathf.Max(1, job.msaa),
        };
        rt.Create();
        cam.allowMSAA = true;
        cam.targetTexture = rt;
        result.captured = job.capture;
        if (!job.capture) return null; // dry run: the camera still renders, nothing is read back

        readTex = new Texture2D(job.width, job.height, TextureFormat.RGBA32, false, false);
        buffer = new byte[job.width * job.height * 4];
        md5 = MD5.Create();

        string video = Path.Combine(job.out_dir, job.video_name);
        result.video = video;
        var psi = new ProcessStartInfo
        {
            FileName = job.ffmpeg,
            Arguments = "-hide_banner -loglevel error -y " +
                        $"-f rawvideo -pix_fmt rgba -s {job.width}x{job.height} -r {job.fps} -i - " +
                        "-vf vflip,scale=out_color_matrix=bt709 -c:v libx264 -preset medium " +
                        $"-crf {job.crf} -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 " +
                        $"-color_trc bt709 -movflags +faststart \"{video}\"",
            UseShellExecute = false,
            RedirectStandardInput = true,
        };
        try
        {
            ffmpeg = Process.Start(psi);
            ffmpegIn = ffmpeg.StandardInput.BaseStream;
        }
        catch (Exception e)
        {
            return $"could not start ffmpeg ({job.ffmpeg}): {e.Message}";
        }
        return null;
    }

    // CameraController.FitBoardToScreen with the video's aspect instead of the window's.
    void FitCamera()
    {
        var cc = FindFirstObjectByType<CameraController>(FindObjectsInactive.Include);
        float padding = cc != null ? GetField<float>(cc, "padding") : 1f;
        float vOffset = cc != null ? GetField<float>(cc, "verticalScreenOffset") : 0f;
        float minD = cc != null ? GetField<float>(cc, "minCameraDistance") : 5f;
        float maxD = cc != null ? GetField<float>(cc, "maxCameraDistance") : 50f;

        float s = grid.CellSpacing;
        int w = grid.GridWidth, h = grid.GridHeight;
        camSpacing = s;
        float boardW = w * s + padding * 2;
        float boardH = h * s + padding * 2;
        Vector3 center = grid.GridOrigin + new Vector3((w - 1) * s * 0.5f, 0, (h - 1) * s * 0.5f);
        float aspect = (float)job.width / job.height;

        if (cam.orthographic)
        {
            float size = Mathf.Max(boardH * 0.5f, boardW * 0.5f / aspect);
            Vector3 c = center + cam.transform.up * (vOffset * size * 2f);
            camBasePos = new Vector3(c.x, cam.transform.position.y, c.z);
            camBaseSize = size;
            ApplyCamera();
            return;
        }
        float fovRad = cam.fieldOfView * Mathf.Deg2Rad;
        float lookAngle = Vector3.Angle(cam.transform.forward, Vector3.down);
        float effH = boardH;
        if (lookAngle < 90f && lookAngle > 0f) effH = boardH / Mathf.Cos(lookAngle * Mathf.Deg2Rad);
        float dH = effH / (2f * Mathf.Tan(fovRad * 0.5f));
        float hFov = 2f * Mathf.Atan(Mathf.Tan(fovRad * 0.5f) * aspect);
        float dW = boardW / (2f * Mathf.Tan(hFov * 0.5f));
        float dist = Mathf.Clamp(Mathf.Max(dH, dW), minD, maxD);
        Vector3 pos = center - cam.transform.forward * dist;
        if (Mathf.Abs(vOffset) > 0.001f)
            pos += cam.transform.up * (vOffset * 2f * dist * Mathf.Tan(fovRad * 0.5f));
        camBasePos = pos;
        camBaseDist = dist;
        ApplyCamera();
    }

    // Zoom moves the camera along its view direction toward the fitted framing's look-at point;
    // pan slides it over the board in cells. Runs every frame before rendering.
    void ApplyCamera()
    {
        if (cam == null || camSpacing <= 0f) return;
        float t = (float)frame / job.fps;
        float zoom = job.camera.zoom, px = job.camera.pan_x, py = job.camera.pan_y;
        var keys = job.camera.keys;
        if (keys.Count > 0)
        {
            // Hold the first key before it, the last key after it, and ease in between.
            CameraKey a = keys[0], b = keys[0];
            float u = 0f;
            if (t >= keys[keys.Count - 1].t)
            {
                a = b = keys[keys.Count - 1];
            }
            else if (t > keys[0].t)
            {
                int i = 0;
                while (t >= keys[i + 1].t) i++;
                a = keys[i];
                b = keys[i + 1];
                u = Mathf.SmoothStep(0f, 1f, (t - a.t) / (b.t - a.t));
            }
            zoom = Mathf.Lerp(a.zoom, b.zoom, u);
            px = Mathf.Lerp(a.pan_x, b.pan_x, u);
            py = Mathf.Lerp(a.pan_y, b.pan_y, u);
        }
        Vector3 pan = new Vector3(px * camSpacing, 0f, py * camSpacing);
        if (cam.orthographic)
        {
            cam.transform.position = camBasePos + pan;
            cam.orthographicSize = camBaseSize / zoom;
        }
        else
        {
            Vector3 lookAt = camBasePos + cam.transform.forward * camBaseDist;
            cam.transform.position = lookAt - cam.transform.forward * (camBaseDist / zoom) + pan;
        }
    }

    void LateUpdate()
    {
        if (rt != null && !finished) ApplyCamera();
    }

    // Overlay canvases do not reach a render texture, so draw them through the camera, scaled as
    // a phone of the video's size would scale them.
    void AttachCanvases()
    {
        foreach (var canvas in FindObjectsByType<Canvas>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (!canvas.isRootCanvas || canvas.renderMode != RenderMode.ScreenSpaceOverlay) continue;
            float scale = 1f;
            var scaler = canvas.GetComponent<CanvasScaler>();
            if (scaler != null)
            {
                if (scaler.uiScaleMode == CanvasScaler.ScaleMode.ScaleWithScreenSize)
                {
                    float rw = job.width / scaler.referenceResolution.x;
                    float rh = job.height / scaler.referenceResolution.y;
                    if (scaler.screenMatchMode == CanvasScaler.ScreenMatchMode.Expand) scale = Mathf.Min(rw, rh);
                    else if (scaler.screenMatchMode == CanvasScaler.ScreenMatchMode.Shrink) scale = Mathf.Max(rw, rh);
                    else scale = Mathf.Pow(2f, Mathf.Lerp(Mathf.Log(rw, 2f), Mathf.Log(rh, 2f), scaler.matchWidthOrHeight));
                }
                else if (scaler.uiScaleMode == CanvasScaler.ScaleMode.ConstantPixelSize)
                {
                    scale = scaler.scaleFactor;
                }
                scaler.enabled = false;
            }
            canvas.renderMode = RenderMode.ScreenSpaceCamera;
            canvas.worldCamera = cam;
            canvas.planeDistance = cam.nearClipPlane + 0.01f;
            canvas.scaleFactor = scale;
        }
    }

    // Particle systems pick a new random seed on every run; fix each one's seed by its place in
    // the hierarchy so every particle follows the same path in every render of the same job.
    void SeedParticles()
    {
        foreach (var ps in FindObjectsByType<ParticleSystem>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (!seededParticles.Add(ps.GetInstanceID())) continue;
            bool playing = ps.isPlaying;
            if (playing) ps.Stop(false, ParticleSystemStopBehavior.StopEmittingAndClear);
            ps.useAutoRandomSeed = false;
            ps.randomSeed = StableSeed(ps.transform);
            if (playing) ps.Play(false);
        }
    }

    static uint StableSeed(Transform t)
    {
        uint h = 2166136261;
        for (; t != null; t = t.parent)
        {
            foreach (char c in t.name + "/" + t.GetSiblingIndex())
                h = (h ^ c) * 16777619;
        }
        return h;
    }

    // ---------- capture ----------

    IEnumerator CaptureLoop()
    {
        var endOfFrame = new WaitForEndOfFrame();
        int limit = Mathf.RoundToInt(job.max_seconds * job.fps);
        while (true)
        {
            yield return endOfFrame;
            try
            {
                SeedParticles();
                Capture();
            }
            catch (Exception e)
            {
                captureError = "capture failed: " + e.Message;
            }
            if (captureError != null)
            {
                if (main != null) StopCoroutine(main);
                SetStatus("error", captureError);
                break;
            }
            if (result.fail_frame < 0 && failMenu != null && failMenu.gameObject.activeInHierarchy)
            {
                // The game shows its fail screen; play stops here, as it does for a player.
                result.fail_frame = frame - 1;
                SetStatus("failed", "the timer ran out");
            }
            if (scriptDone) break;
            if (frame >= limit)
            {
                if (main != null) StopCoroutine(main);
                SetStatus("timeout", $"stopped at max_seconds={job.max_seconds}");
                break;
            }
        }
        Finish();
    }

    void Capture()
    {
        if (!job.capture)
        {
            LogFrame(); // timing, finger and block positions only
            frame++;
            return;
        }
        var prev = RenderTexture.active;
        RenderTexture.active = rt;
        readTex.ReadPixels(new Rect(0, 0, job.width, job.height), 0, 0, false);
        RenderTexture.active = prev;
        readTex.GetRawTextureData<byte>().CopyTo(buffer);
        if (ffmpeg.HasExited)
        {
            captureError = $"ffmpeg exited with {ffmpeg.ExitCode} while recording";
            return;
        }
        try
        {
            ffmpegIn.Write(buffer, 0, buffer.Length);
        }
        catch (Exception e)
        {
            captureError = "ffmpeg stopped taking frames: " + e.Message;
            return;
        }

        FrameRecord rec = LogFrame();
        if (job.frame_hashes) rec.hash = Hex(md5.ComputeHash(buffer));

        if (stillAt.TryGetValue(frame, out string name))
        {
            File.WriteAllBytes(Path.Combine(job.out_dir, name), readTex.EncodeToPNG());
            result.stills.Add(name);
        }
        Graphics.Blit(rt, (RenderTexture)null); // live preview in the player window
        frame++;
    }

    FrameRecord LogFrame()
    {
        var rec = new FrameRecord { frame = frame, timer = Timer(), finger = fingerDown };
        if (fingerDown)
        {
            Vector3 p = cam.WorldToScreenPoint(finger);
            rec.finger_x = p.x;
            rec.finger_y = job.height - p.y;
        }
        for (int i = 0; i < blocks.Count; i++)
        {
            if (blocks[i] == null)
            {
                if (result.block_gone_frames[i] < 0) result.block_gone_frames[i] = frame;
                rec.blocks.Add(-1f);
                rec.blocks.Add(-1f);
                continue;
            }
            Vector3 bp = cam.WorldToScreenPoint(blocks[i].transform.position);
            rec.blocks.Add(bp.x);
            rec.blocks.Add(job.height - bp.y);
        }
        if (frame == 0) LogUiRects();
        bool failShowing = failMenu != null && failMenu.gameObject.activeInHierarchy;
        if (lastExitStarted && result.clock_stopped_frame < 0 && !failShowing && !ClockRunning())
            result.clock_stopped_frame = frame;
        frameLog.frames.Add(rec);
        return rec;
    }

    void LogUiRects()
    {
        var corners = new Vector3[4];
        foreach (string name in new[] { "MainBar", "LevelCircle", "TimerBackground", "RestartButton" })
        {
            var go = GameObject.Find(name);
            if (go == null || !(go.transform is RectTransform rtf)) continue;
            rtf.GetWorldCorners(corners);
            float x0 = float.MaxValue, y0 = float.MaxValue, x1 = float.MinValue, y1 = float.MinValue;
            foreach (var c in corners)
            {
                Vector3 sp = cam.WorldToScreenPoint(c);
                float sy = job.height - sp.y;
                x0 = Mathf.Min(x0, sp.x); x1 = Mathf.Max(x1, sp.x);
                y0 = Mathf.Min(y0, sy); y1 = Mathf.Max(y1, sy);
            }
            result.ui_rects.Add(new UiRect { name = name, x = x0, y = y0, w = x1 - x0, h = y1 - y0 });
        }
    }

    void Finish()
    {
        if (finished) return;
        finished = true;
        if (job.capture && frame > 0 && readTex != null)
        {
            File.WriteAllBytes(Path.Combine(job.out_dir, "99_end.png"), readTex.EncodeToPNG());
            result.stills.Add("99_end.png");
        }
        if (ffmpegIn != null)
        {
            try
            {
                if (!ffmpeg.HasExited)
                {
                    ffmpegIn.Flush();
                    ffmpeg.StandardInput.Close();
                }
                if (!ffmpeg.WaitForExit(300000)) SetStatus("error", "ffmpeg did not finish");
                else if (ffmpeg.ExitCode != 0) SetStatus("error", $"ffmpeg exited with {ffmpeg.ExitCode}");
            }
            catch (Exception e)
            {
                SetStatus("error", "ffmpeg: " + e.Message);
            }
        }
        if (cam != null) cam.targetTexture = null;

        result.end_mode = job.end_mode;
        result.frames = frame;
        result.fps = job.fps;
        result.width = job.width;
        result.height = job.height;
        result.duration_s = (float)frame / Mathf.Max(1, job.fps);
        result.timer_end = Timer();
        if (result.status == null) SetStatus("error", "the script stopped early");
        if (result.status == "failed" && result.win_frame > result.fail_frame && result.fail_frame >= 0)
            result.message += "; it ran out during the last block's exit slide, and the game then showed the win screen too";
        if (!string.IsNullOrEmpty(job.out_dir) && Directory.Exists(job.out_dir))
        {
            File.WriteAllText(Path.Combine(job.out_dir, "result.json"), JsonUtility.ToJson(result, true));
            File.WriteAllText(Path.Combine(job.out_dir, "frames.json"), JsonUtility.ToJson(frameLog));
        }
        Debug.Log($"[CreativeRunner] {result.status} frames={frame} {result.message}");

        bool expected = (job.end_mode == "win" && result.status == "cleared")
                        || (job.end_mode == "cut" && result.status == "unresolved")
                        || (job.end_mode == "fail" && result.status == "failed");
        Application.Quit(expected ? 0 : result.status == "error" ? 1 : 2);
    }

    // ---------- helpers ----------

    void SetStatus(string status, string message)
    {
        if (result.status != null) return;
        result.status = status;
        result.message = message ?? "";
    }

    void Mismatch(DragRecord rec, string message)
    {
        rec.result = "mismatch: " + message;
        SetStatus("mismatch", $"drag {rec.index + 1}: {message}");
    }

    void Still(int atFrame, string name)
    {
        stillAt[atFrame] = name;
    }

    float Timer()
    {
        if (remainingTimeField == null || GameManager.Instance == null) return -1f;
        return (float)remainingTimeField.GetValue(GameManager.Instance);
    }

    int Frames(float seconds) => Mathf.Max(0, Mathf.RoundToInt(seconds * job.fps));

    bool ClockRunning() => timerRunningField != null && GameManager.Instance != null
                           && (bool)timerRunningField.GetValue(GameManager.Instance);

    void SetOutline(Block b, bool on)
    {
        var outline = b.GetComponent<Outline>();
        if (outline == null) return;
        outline.enabled = on;
        if (on) outline.OutlineWidth = outlineWidth;
    }

    Vector3 CellWorld(Vector2Int c) => grid.GetCell(c.x, c.y).transform.position;

    static Vector2Int Pivot(Block b) => new Vector2Int(b.parentCell.column, b.parentCell.row);

    static Vector2Int ToCell(RenderCell c) => new Vector2Int(c.x, c.y);

    static float Flat(Vector3 v) => new Vector2(v.x, v.z).magnitude;

    static bool Turns(List<RenderCell> path, int i)
    {
        if (i + 1 >= path.Count) return true;
        return ToCell(path[i]) - ToCell(path[i - 1]) != ToCell(path[i + 1]) - ToCell(path[i]);
    }

    static bool SameCells(List<RenderCell> a, List<RenderCell> b)
    {
        if (a.Count != b.Count) return false;
        for (int i = 0; i < a.Count; i++)
            if (a[i].x != b[i].x || a[i].y != b[i].y) return false;
        return true;
    }

    static string CellsText(List<RenderCell> cells)
    {
        if (cells.Count == 0) return "no new cell";
        var parts = new List<string>();
        foreach (var c in cells) parts.Add($"({c.x},{c.y})");
        return string.Join(" ", parts);
    }

    static string Hex(byte[] bytes) => BitConverter.ToString(bytes).Replace("-", "").ToLowerInvariant();

    static T GetField<T>(object target, string name)
    {
        var f = target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        return f != null ? (T)f.GetValue(target) : default;
    }

    static string ArgValue(string name)
    {
        var args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == name) return args[i + 1];
        return null;
    }
}
