"""
Shared MP4 video encoding utilities for all dashboard animation pipelines.

Centralises ffmpeg settings so every product (satellite, radar, MRMS, lightning,
surface, alerts) gets identical quality, compression, and social-media-friendly
end-of-loop pause behaviour.
"""

import subprocess
import time

import imageio.v2 as imageio
import numpy as np

# ── Canonical 1080p output constants ──────────────────────────────────────────
# All dashboard modules should use these for consistent frame dimensions.
#   figsize * OUTPUT_DPI  →  pixel resolution
#   (12.8, 7.2) * 150    →  1920 × 1080  (16:9)
OUTPUT_DPI = 150
FIGSIZE_16x9 = (12.8, 7.2)  # inches → 1920×1080 at OUTPUT_DPI


def _find_ffmpeg():
    """Return the path to the ffmpeg binary bundled with imageio-ffmpeg, or
    fall back to a system ``ffmpeg`` on PATH."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _pad_frames_mod16(frames):
    """Pad RGB frames to a common mod-16 size for stable H.264 encoding."""
    if not frames:
        return frames

    max_h = max(f.shape[0] for f in frames)
    max_w = max(f.shape[1] for f in frames)

    # Pad up (not crop down) so content is preserved when frame bounds differ.
    target_h = max_h + ((16 - (max_h % 16)) % 16)
    target_w = max_w + ((16 - (max_w % 16)) % 16)

    padded = []
    for f in frames:
        if getattr(f, "ndim", 0) != 3 or f.shape[2] != 3:
            raise ValueError(f"Expected RGB frame (H, W, 3), got: {f.shape}")
        h, w = f.shape[:2]
        if h == target_h and w == target_w:
            padded.append(f)
            continue
        canvas = np.zeros((target_h, target_w, 3), dtype=f.dtype)
        canvas[:h, :w, :] = f
        padded.append(canvas)
    return padded


def _to_rgb_uint8(frame):
    """Normalize input frame to contiguous uint8 RGB."""
    if frame.ndim == 2:
        frame = np.repeat(frame[:, :, None], 3, axis=2)
    elif frame.ndim == 3:
        ch = frame.shape[2]
        if ch == 1:
            frame = np.repeat(frame, 3, axis=2)
        elif ch >= 3:
            frame = frame[:, :, :3]
        else:
            raise ValueError(f"Unsupported channel count: {ch}")
    else:
        raise ValueError(f"Unsupported frame rank: {frame.ndim}")

    if frame.dtype != np.uint8:
        # Preserve common 0..1 float frames by scaling to 0..255.
        if np.issubdtype(frame.dtype, np.floating):
            finite = frame[np.isfinite(frame)]
            if finite.size and finite.min() >= 0.0 and finite.max() <= 1.0:
                frame = frame * 255.0
        frame = np.clip(frame, 0, 255).astype(np.uint8)

    return np.ascontiguousarray(frame)


def save_animation(
    movie_path,
    frames,
    fps=4,
    pause_frames=3,
    crf=18,
    preset="slow",
    tune="stillimage",
):
    """Encode a list of RGB uint8 numpy arrays into an MP4 file.

    Features over a raw ``imageio.mimsave`` call:

    * **End-of-loop pause** — duplicates the last frame *pause_frames* times so
      social-media autoplay loops don't smash-cut back to frame 1.
    * **faststart** — moves the *moov* atom to the front of the file so the
      video is streamable (plays before fully downloaded).
    * **CRF 18 / preset slow / tune stillimage** — visually lossless quality at
      ~60-70 % smaller file sizes than the previous CRF 5 / quality 9 setting.
    * **1080p-ready** — callers should use ``FIGSIZE_16x9`` and ``OUTPUT_DPI``
      (exported from this module) for consistent 1920×1080 frames.
    * **Automatic mod-16 padding** for H.264 compatibility.
    * **Direct raw-frame piping to ffmpeg** — avoids temp PNG write/read overhead.
    * **Graceful fallback** to ``imageio.mimsave`` if ffmpeg CLI fails.

    Parameters
    ----------
    movie_path : str
        Destination ``.mp4`` path.
    frames : list[np.ndarray]
        RGB uint8 arrays (H, W, 3).
    fps : int
        Playback frame rate.
    pause_frames : int
        Number of duplicate last-frame copies to append (0 to disable).
    crf : int
        Constant Rate Factor (0 = lossless, 51 = worst). 18 ≈ visually lossless.
    preset : str
        x264 preset (ultrafast … veryslow).
    tune : str
        x264 tune profile. ``stillimage`` is ideal for satellite/weather maps.
    """
    if not frames:
        raise ValueError("No frames to encode")

    _t0 = time.perf_counter()

    # Normalize to RGB first so callers with RGBA/grayscale/float frames keep working.
    rgb_frames = [_to_rgb_uint8(frame) for frame in frames]

    # Pad to a common mod-16 canvas so ffmpeg always receives fixed-size frames.
    normalized = _pad_frames_mod16(rgb_frames)
    base_h, base_w = normalized[0].shape[:2]

    # ── Append pause frames ──
    if pause_frames > 0 and len(normalized) > 1:
        last = normalized[-1]
        for _ in range(pause_frames):
            normalized.append(last.copy())

    _t_prepped = time.perf_counter()

    # ── Encode via ffmpeg rawvideo pipe (no temp PNG files) ──
    try:
        ffmpeg_bin = _find_ffmpeg()
        cmd = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostats",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{base_w}x{base_h}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-tune",
            tune,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            movie_path,
        ]

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        try:
            for frame in normalized:
                proc.stdin.write(frame.tobytes())
            proc.stdin.close()
            # Scale timeout to frame count; generous cap for large loops.
            encode_timeout_s = min(600, max(60, len(normalized) * 4))
            proc.wait(timeout=encode_timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError(
                f"ffmpeg encode timed out after {encode_timeout_s}s "
                f"({len(normalized)} frames, preset={preset})"
            )

        if proc.returncode != 0:
            stderr_output = ""
            try:
                stderr_output = (
                    proc.stderr.read().decode("utf-8", errors="replace").strip()
                )
            except Exception:
                pass
            raise RuntimeError(
                f"ffmpeg exited {proc.returncode}"
                + (f": {stderr_output}" if stderr_output else "")
            )

        _t_done = time.perf_counter()
        print(
            f"[Perf] save_animation: prep={_t_prepped - _t0:.2f}s "
            f"encode={_t_done - _t_prepped:.2f}s total={_t_done - _t0:.2f}s "
            f"frames={len(normalized)} size={base_w}x{base_h} fps={fps}"
        )

    except Exception as primary_err:
        # ── Graceful fallback: use imageio (no pause, no faststart) ──
        print(
            f"[WARN] ffmpeg encode failed ({primary_err}), "
            "falling back to imageio.mimsave"
        )
        try:
            imageio.mimsave(
                movie_path, normalized, fps=fps, quality=8, pixelformat="yuv420p"
            )
        except Exception:
            # Last resort — GIF
            gif_path = movie_path.rsplit(".", 1)[0] + ".gif"
            imageio.mimsave(gif_path, normalized, fps=fps, loop=0)
            return gif_path

    return movie_path
