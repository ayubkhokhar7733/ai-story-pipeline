"""
core/video_composer.py - Pure FFmpeg CPU video composer with Ken Burns motion, ambient pad, and subtitle burn-in.
"""
import math
import os
import re
import struct
import subprocess
import time
import wave
import config


def compose_story_video(
    scenes: list,
    audio_path: str,
    srt_path: str,
    title: str = "story_video",
    aspect: str = "9:16",
    output_filename: str = None,
) -> str:
    """
    Renders scene images into Ken Burns MP4 chunks, concatenates them,
    and burns in subtitles + mixes ducked ambient audio in a single FFmpeg graph.
    """
    preset = config.ASPECT_PRESETS.get(aspect, config.ASPECT_PRESETS["9:16"])
    target_w = preset["width"]
    target_h = preset["height"]
    font_size = preset["subtitle_font_size"]
    margin_v = preset["subtitle_margin_v"]

    print(f"\n[video_composer] Rendering {aspect} ({target_w}x{target_h}) via pure FFmpeg...", flush=True)

    chunk_paths = []
    motions = ["zoom_in", "pan_right", "zoom_out", "pan_left"]
    for idx, scene in enumerate(scenes, 1):
        img_path = scene.get("image_path")
        if not img_path or not os.path.exists(img_path):
            raise FileNotFoundError(f"Missing scene image: {img_path}")

        dur = float(scene.get("duration_sec", 5.5))
        motion = scene.get("camera_motion") or motions[(idx - 1) % len(motions)]
        chunk_file = os.path.join(config.TEMP_DIR, f"chunk_{idx:02d}.mp4")

        print(f"   Scene {idx}/{len(scenes)}: {dur:.2f}s [{motion}]", flush=True)
        _render_ken_burns_chunk(img_path, dur, motion, chunk_file, target_w, target_h)
        chunk_paths.append(chunk_file)

    # Concatenate video chunks
    concat_list = os.path.join(config.TEMP_DIR, "video_concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f_list:
        for cp in chunk_paths:
            esc = os.path.abspath(cp).replace("\\", "/").replace("'", "'\\''")
            f_list.write(f"file '{esc}'\n")

    visual_track = os.path.join(config.TEMP_DIR, "visual_track.mp4")
    res_cat = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", visual_track],
        capture_output=True,
        text=True,
    )
    if res_cat.returncode != 0:
        raise RuntimeError(f"FFmpeg video concat failed: {res_cat.stderr}")

    # Ensure subtle ambient music bed exists
    bgm_path = _ensure_ambient_music()
    has_srt = os.path.exists(srt_path) and os.path.getsize(srt_path) > 5

    clean_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_") or "story_video"
    tag = "shorts_9x16" if aspect == "9:16" else "landscape_16x9"
    final_name = output_filename or f"{clean_title[:28]}_{tag}_{int(time.time())}.mp4"
    final_output = os.path.join(config.OUTPUT_DIR, final_name)

    cmd = ["ffmpeg", "-y", "-i", visual_track, "-i", audio_path]
    filter_parts = []

    if has_srt:
        rel_srt = os.path.relpath(srt_path, start=os.getcwd()).replace("\\", "/")
        rel_srt_esc = rel_srt.replace(":", "\\:")
        sub_style = (
            f"FontName=DejaVu Sans,FontSize={font_size},Bold=1,"
            f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            f"BackColour=&H64000000,BorderStyle=1,Outline=2.5,Shadow=1,"
            f"Alignment=2,MarginV={margin_v}"
        )
        filter_parts.append(f"[0:v]subtitles='{rel_srt_esc}':force_style='{sub_style}'[vout]")
        v_map = "[vout]"
    else:
        v_map = "0:v"

    if bgm_path and os.path.exists(bgm_path):
        cmd.extend(["-stream_loop", "-1", "-i", bgm_path])
        filter_parts.append(f"[2:a]volume={config.MUSIC_VOLUME}[bgm]")
        filter_parts.append("[1:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        a_map = "[aout]"
    else:
        a_map = "1:a"

    if filter_parts:
        cmd.extend(["-filter_complex", ";".join(filter_parts)])

    cmd.extend([
        "-map", v_map,
        "-map", a_map,
        "-c:v", "libx264",
        "-preset", "faster",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-movflags", "+faststart",
        final_output,
    ])

    print("[video_composer] Encoding final MP4 with burned-in subtitles...", flush=True)
    res_final = subprocess.run(cmd, capture_output=True, text=True)
    if res_final.returncode != 0:
        raise RuntimeError(f"FFmpeg final render failed:\n{res_final.stderr}")

    print(f"[video_composer] Exported: {final_output}", flush=True)
    return final_output


def _render_ken_burns_chunk(img_path: str, duration: float, motion: str, out_path: str, w: int, h: int):
    frames = max(30, int(round(duration * config.FPS)))
    up_w, up_h = w * 2, h * 2

    if motion == "zoom_out":
        z_expr = f"max(1.15-0.15*on/{frames},1.0)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion == "pan_left":
        z_expr = "1.12"
        x_expr = f"(iw-iw/zoom)*(1-on/{frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion == "pan_right":
        z_expr = "1.12"
        x_expr = f"(iw-iw/zoom)*(on/{frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        z_expr = f"min(1.0+0.15*on/{frames},1.15)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    vf = (
        f"scale={up_w}:{up_h}:force_original_aspect_ratio=increase,"
        f"crop={up_w}:{up_h},"
        f"zoompan=z='{z_expr}':d={frames}:x='{x_expr}':y='{y_expr}':s={w}x{h}:fps={config.FPS}"
    )

    cmd = [
        "ffmpeg", "-y", "-loop", "1",
        "-i", img_path,
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg Ken Burns failed: {res.stderr}")


def _ensure_ambient_music() -> str:
    """Generates a gentle warm harmonic pad WAV if no custom music file exists."""
    music_dir = os.path.join(config.ASSETS_DIR, "music")
    os.makedirs(music_dir, exist_ok=True)
    custom_wav = os.path.join(music_dir, "background.wav")
    if os.path.exists(custom_wav):
        return custom_wav

    pad_wav = os.path.join(config.TEMP_DIR, "ambient_pad.wav")
    if os.path.exists(pad_wav):
        return pad_wav

    sample_rate = 44100
    duration_sec = 12
    total_samples = sample_rate * duration_sec
    freqs = [130.81, 196.00, 261.63, 329.63]  # C3, G3, C4, E4 soft ambient pad

    with wave.open(pad_wav, "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(total_samples):
            t = i / sample_rate
            # Smooth loopable envelope
            env = 0.5 - 0.5 * math.cos(2 * math.pi * t / duration_sec)
            val = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
            sample = int(max(-1.0, min(1.0, val * (0.25 + 0.15 * env))) * 12000)
            frames.extend(struct.pack("<hh", sample, sample))
        wf.writeframes(bytes(frames))

    return pad_wav
