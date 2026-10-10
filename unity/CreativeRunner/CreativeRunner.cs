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
    public float pause_before_s = 0.4f;
    public float pickup_s = 0.12f;
    public float cells_per_s = 6f;
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
    public float start_hold_s = 1f;
    public float end_hold_s = 2f;
    public float max_seconds = 120f;
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
    public int start_frame;
    public int exit_frame = -1;
    public int end_frame = -1;
    public float timer_start;
    public float timer_end;
    public List<RenderCell> cells = new List<RenderCell>(); // pivot cells entered, in order
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
    public int win_frame = -1;
    public int fail_frame = -1;
    public float timer_start;
    public float timer_end;
    public string video;
    public List<string> stills = new List<string>();
    public List<DragRecord> drags = new List<DragRecord>();
}

[Serializable]
public class FrameRecord
{
    public int frame;
    public float timer;
    public bool finger;
    public float finger_x; // pixels from the left of the video
    public float finger_y; // pixels from the top of the video
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
    bool scriptDone;
    bool finished;
    bool fingerDown;
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
            if (job.fps < 1 || job.width < 16 || job.height < 16) throw new Exception("bad fps or size");
            Directory.CreateDirectory(job.out_dir);
            var level = JsonUtility.FromJson<LevelData>(File.ReadAllText(job.level_path));
            if (level == null || level.gridWidth < 1 || level.gridHeight < 1)
                throw new Exception("level file has no grid: " + job.level_path);
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
        if (LevelManager.Instance != null)
            LevelManager.Instance.OnLevelCompleted += _ => { if (result.win_frame < 0) result.win_frame = frame; };
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
        for (int i = 1; i < d.path.Count; i++)
        {
            Vector2Int step = ToCell(d.path[i]) - ToCell(d.path[i - 1]);
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

        for (int f = 0; f < Frames(d.pickup_s); f++)
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
            for (int f = 1; f <= framesPerCell; f++)
            {
                finger = Vector3.Lerp(from, to, (float)f / framesPerCell);
                if (Step(b, initialY, rec)) break;
                yield return null;
            }
            bool corner = i == d.path.Count - 1 || Turns(d.path, i);
            int settle = 0;
            while (corner && !exitTriggered && Flat(b.transform.position - to) > SettleEps * grid.CellSpacing
                   && settle++ < job.fps * 2)
            {
                if (Step(b, initialY, rec)) break;
                yield return null;
            }
        }

        fingerDown = false;
        if (exitTriggered)
        {
            rec.exit_frame = frame;
            int wait = 0;
            while (!exitPerformed && wait++ < job.fps) yield return null;
            rec.result = "exit";
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

        // Did the game do what the solver planned?
        var planned = d.path.GetRange(1, d.path.Count - 1);
        if (!SameCells(rec.cells, planned))
            Mismatch(rec, $"block {d.block} entered {CellsText(rec.cells)}, the script planned {CellsText(planned)}");
        else if (d.exits && !exitTriggered)
            Mismatch(rec, $"block {d.block} did not exit at {CellsText(planned)}");
        else if (!d.exits && exitTriggered)
            Mismatch(rec, $"block {d.block} exited, the script did not plan an exit");
        rec.end_frame = frame;
        rec.timer_end = Timer();
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
        if (!exitService.CanBlockExit(b, g)) return false;

        // InputHandler.HandleExitDuringDrag: snap to the cell, then the game's exit animation.
        exitTriggered = true;
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
        // Button colour fades run on real time (Graphic.CrossFadeColor ignores the time scale),
        // so a fade caught mid-way differs between runs. Make them instant.
        foreach (var sel in FindObjectsByType<Selectable>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            var colors = sel.colors;
            colors.fadeDuration = 0f;
            sel.colors = colors;
        }
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
        float boardW = w * s + padding * 2;
        float boardH = h * s + padding * 2;
        Vector3 center = grid.GridOrigin + new Vector3((w - 1) * s * 0.5f, 0, (h - 1) * s * 0.5f);
        float aspect = (float)job.width / job.height;

        if (cam.orthographic)
        {
            float size = Mathf.Max(boardH * 0.5f, boardW * 0.5f / aspect);
            Vector3 c = center + cam.transform.up * (vOffset * size * 2f);
            cam.transform.position = new Vector3(c.x, cam.transform.position.y, c.z);
            cam.orthographicSize = size;
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
        cam.transform.position = pos;
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
    // the hierarchy so two renders of the same job match frame for frame.
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
            SeedParticles();
            Capture();
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
        var prev = RenderTexture.active;
        RenderTexture.active = rt;
        readTex.ReadPixels(new Rect(0, 0, job.width, job.height), 0, 0, false);
        RenderTexture.active = prev;
        readTex.GetRawTextureData<byte>().CopyTo(buffer);
        ffmpegIn.Write(buffer, 0, buffer.Length);

        var rec = new FrameRecord { frame = frame, timer = Timer(), finger = fingerDown };
        if (fingerDown)
        {
            Vector3 p = cam.WorldToScreenPoint(finger);
            rec.finger_x = p.x;
            rec.finger_y = job.height - p.y;
        }
        if (job.frame_hashes) rec.hash = Hex(md5.ComputeHash(buffer));
        frameLog.frames.Add(rec);

        if (stillAt.TryGetValue(frame, out string name))
        {
            File.WriteAllBytes(Path.Combine(job.out_dir, name), readTex.EncodeToPNG());
            result.stills.Add(name);
        }
        Graphics.Blit(rt, (RenderTexture)null); // live preview in the player window
        frame++;
    }

    void Finish()
    {
        if (finished) return;
        finished = true;
        if (frame > 0 && readTex != null)
        {
            File.WriteAllBytes(Path.Combine(job.out_dir, "99_end.png"), readTex.EncodeToPNG());
            result.stills.Add("99_end.png");
        }
        if (ffmpegIn != null)
        {
            try
            {
                ffmpegIn.Flush();
                ffmpeg.StandardInput.Close();
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
