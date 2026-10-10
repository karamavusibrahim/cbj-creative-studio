using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

// Builds the macOS player that CreativeRunner records with. Run on a copy of the project:
//   Unity -batchmode -quit -projectPath <copy> -executeMethod CreativeRunnerBuild.BuildMac -cbjOut <path/CBJRunner.app>
public static class CreativeRunnerBuild
{
    public static void BuildMac()
    {
        string outPath = ArgValue("-cbjOut") ?? "Builds/CBJRunner.app";

        // Own name, so its saved settings never mix with the game's (level progress, window size).
        PlayerSettings.productName = "CBJ Creative Runner";
        PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
        PlayerSettings.defaultScreenWidth = 270;
        PlayerSettings.defaultScreenHeight = 480;
        PlayerSettings.runInBackground = true;

        var options = new BuildPlayerOptions
        {
            scenes = new[] { "Assets/Scenes/GameScene.unity" },
            locationPathName = outPath,
            target = BuildTarget.StandaloneOSX,
            options = BuildOptions.None,
        };
        BuildReport report = BuildPipeline.BuildPlayer(options);
        var s = report.summary;
        Debug.Log($"[CreativeRunnerBuild] result={s.result} errors={s.totalErrors} warnings={s.totalWarnings} time={s.totalTime}");
        bool ok = s.result == BuildResult.Succeeded;
        if (ok)
        {
            // LevelManager scans Application.dataPath/Levels; ship the levels so it finds them.
            string dst = Path.Combine(outPath, "Contents", "Levels");
            Directory.CreateDirectory(dst);
            foreach (var f in Directory.GetFiles("Assets/Levels", "*.json"))
                File.Copy(f, Path.Combine(dst, Path.GetFileName(f)), true);
        }
        EditorApplication.Exit(ok ? 0 : 1);
    }

    static string ArgValue(string name)
    {
        var args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == name) return args[i + 1];
        return null;
    }
}
