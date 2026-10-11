"""Reading and writing video frames through ffmpeg, with explicit colour handling.

The recorder writes H.264, yuv420p, BT.709, TV range. Reading frames back for compositing and
writing the finished ad must use the same matrix and range at both ends, or colours shift a
little on every round trip (BT.601 is ffmpeg's guess for untagged input).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

# The colour conversion used everywhere: RGB <-> YUV with the BT.709 matrix, TV range, with
# swscale's accurate rounding and full chroma interpolation. ffmpeg's default YUV->RGB path rounds
# with a bias: a decode and re-encode darkened real frames by about 2 levels (measured 2026-10-11:
# -2.35/-1.86/-1.86 on R/G/B, the same with lossless x264). With these flags the drift is ~0.
_IN = "scale=in_color_matrix=bt709:in_range=tv:flags=bicubic+accurate_rnd+full_chroma_int+bitexact"
_OUT = "scale=out_color_matrix=bt709:out_range=tv:flags=bicubic+accurate_rnd+full_chroma_inp+bitexact"
_TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise ValueError("ffmpeg not found on PATH")
    return path


def read_frames(path: str | Path, size: tuple[int, int], start: int = 0, count: int | None = None):
    """Yield frames start, start+1, ... of a video as HxWx3 uint8 RGB arrays (frame-accurate)."""
    w, h = size
    end = "" if count is None else f":end_frame={start + count}"
    vf = f"trim=start_frame={start}{end},setpts=PTS-STARTPTS,{_IN},format=rgb24"
    cmd = [ffmpeg_bin(), "-v", "error", "-i", str(path), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    n = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(n)
            if len(buf) < n:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        proc.stdout.close()
        err = proc.stderr.read().decode(errors="replace")
        proc.stderr.close()
        if proc.wait() != 0:
            raise ValueError(f"ffmpeg could not read {path}: {err.strip()[-300:]}")


def read_frame(path: str | Path, size: tuple[int, int], index: int) -> np.ndarray:
    for f in read_frames(path, size, index, 1):
        return f.copy()
    raise ValueError(f"{path}: no frame {index}")


class FrameWriter:
    """Encode RGB frames to an H.264 file (video only), tagged BT.709 like the recordings.

    Bit-exact: a fixed thread count and ffmpeg's bitexact flags make the same frames give a
    byte-identical file. draft: fast and smaller, for iterating on an ad."""

    def __init__(self, path: str | Path, size: tuple[int, int], fps: int = 30, crf: int = 16, draft: bool = False):
        self.path = Path(path)
        self.size = size
        w, h = size
        preset, crf = ("ultrafast", max(crf, 23)) if draft else ("medium", crf)
        cmd = [ffmpeg_bin(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
               "-r", str(fps), "-i", "-", "-vf", _OUT, "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
               "-threads", "4", "-flags", "+bitexact", "-fflags", "+bitexact",
               "-pix_fmt", "yuv420p", *_TAGS, "-movflags", "+faststart", str(self.path)]
        # stderr goes to a file: a pipe read only at the end can fill up and stall the encoder.
        self.log = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=self.log)
        self.frames = 0

    def write(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        if (w, h) != tuple(self.size) or frame.dtype != np.uint8 or frame.shape[2] != 3:
            raise ValueError(f"frame must be {self.size[1]}x{self.size[0]}x3 uint8, got {frame.shape} {frame.dtype}")
        self.proc.stdin.write(np.ascontiguousarray(frame).data)
        self.frames += 1

    def close(self) -> None:
        self.proc.stdin.close()
        code = self.proc.wait()
        self.log.seek(0)
        err = self.log.read().decode(errors="replace")
        self.log.close()
        if code != 0:
            raise ValueError(f"ffmpeg could not write {self.path}: {err.strip()[-300:]}")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if exc[0] is None:
            self.close()
        else:
            self.proc.kill()
            self.proc.wait()
            self.log.close()


def mux(video: str | Path, audio_wav: str | Path | None, out: str | Path) -> None:
    """Put a video and a WAV together into an MP4 (video copied, audio AAC 192k)."""
    cmd = [ffmpeg_bin(), "-v", "error", "-y", "-i", str(video)]
    if audio_wav is not None:
        cmd += ["-i", str(audio_wav), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "copy", "-flags", "+bitexact", "-fflags", "+bitexact", "-movflags", "+faststart", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ValueError(f"ffmpeg could not mux {out}: {proc.stderr.strip()[-300:]}")
