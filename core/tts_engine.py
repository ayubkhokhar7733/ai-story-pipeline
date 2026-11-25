"""
core/tts_engine.py - Per-scene Edge-TTS neural voiceover & exact-sync SRT subtitle builder.
"""
import asyncio
import os
import re
import subprocess
import config
from core.script_engine import resolve_voice


def generate_story_audio(scenes: list, voice_name: str = None) -> tuple:
    """
    Synthesizes each scene with Edge-TTS, measures exact clip duration via FFmpeg,
    generates synchronized phrase-level SRT subtitles, and merges audio into a unified WAV.
    Returns (voiceover_wav_path, srt_path, total_duration, updated_scenes).
    """
    voice = resolve_voice(voice_name)
    print(f"[tts_engine] Synthesizing per-scene voiceover using '{voice}'...", flush=True)

    scene_audio_paths = []
    srt_cues = []
    cue_idx = 1
    cumulative_offset = 0.0

    for idx, scene in enumerate(scenes, 1):
        text = scene.get("narration", "").strip()
        if not text:
            continue

        scene_mp3 = os.path.join(config.TEMP_DIR, f"scene_audio_{idx:02d}.mp3")
        word_events = _run_edge_tts(text, voice, scene_mp3)
        dur = max(1.5, _measure_duration(scene_mp3))

        scene["duration_sec"] = round(dur, 3)
        scene["start_sec"] = round(cumulative_offset, 3)
        scene_audio_paths.append(scene_mp3)

        # Build phrase-level cues inside [cumulative_offset, cumulative_offset + dur]
        cues = _build_scene_cues(text, word_events, cumulative_offset, dur)
        for c_start, c_end, c_text in cues:
            srt_cues.append(
                f"{cue_idx}\n{_format_srt_ts(c_start)} --> {_format_srt_ts(c_end)}\n{c_text}\n"
            )
            cue_idx += 1

        cumulative_offset += dur
        print(f"   Scene {idx}: {dur:.2f}s ({len(cues)} subtitle cues)", flush=True)

    if not scene_audio_paths:
        raise ValueError("No scene narration text was synthesized.")

    srt_path = os.path.join(config.TEMP_DIR, "story_subtitles.srt")
    with open(srt_path, "w", encoding="utf-8") as f_srt:
        f_srt.write("\n".join(srt_cues))

    # Concatenate per-scene audio cleanly into uniform 48kHz stereo WAV
    concat_txt = os.path.join(config.TEMP_DIR, "audio_concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f_cat:
        for p in scene_audio_paths:
            esc = os.path.abspath(p).replace("\\", "/").replace("'", "'\\''")
            f_cat.write(f"file '{esc}'\n")

    voiceover_wav = os.path.join(config.TEMP_DIR, "story_voiceover.wav")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_txt,
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
        voiceover_wav,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg audio concat failed: {res.stderr}")

    total_duration = _measure_duration(voiceover_wav)
    print(f"[tts_engine] Voiceover ready: {total_duration:.2f}s total", flush=True)
    return voiceover_wav, srt_path, total_duration, scenes


def _run_edge_tts(text: str, voice: str, output_mp3: str) -> list:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_async_synthesize(text, voice, output_mp3))
    finally:
        loop.close()


async def _async_synthesize(text: str, voice: str, output_mp3: str) -> list:
    import edge_tts

    try:
        communicate = edge_tts.Communicate(text, voice, rate=config.VOICE_RATE, boundary="WordBoundary")
    except TypeError:
        communicate = edge_tts.Communicate(text, voice, rate=config.VOICE_RATE)

    word_events = []
    with open(output_mp3, "wb") as f_out:
        async for chunk in communicate.stream():
            ctype = chunk.get("type")
            if ctype == "audio":
                f_out.write(chunk.get("data", b""))
            elif ctype == "WordBoundary" and chunk.get("text"):
                offset_s = float(chunk.get("offset", 0)) / 10_000_000.0
                dur_s = float(chunk.get("duration", 0)) / 10_000_000.0
                word_events.append({
                    "text": str(chunk["text"]).strip(),
                    "start": offset_s,
                    "end": offset_s + max(0.08, dur_s),
                })
    return word_events


def _build_scene_cues(text: str, word_events: list, offset: float, dur: float) -> list:
    cues = []
    if word_events:
        phrase = []
        p_start = 0.0
        p_end = 0.0
        for ev in word_events:
            if not phrase:
                p_start = ev["start"]
            phrase.append(ev["text"])
            p_end = ev["end"]
            if len(phrase) >= 4 or any(ev["text"].endswith(p) for p in (".", ",", "!", "?", ";", ":")):
                cues.append((offset + p_start, offset + min(dur, p_end), " ".join(phrase)))
                phrase = []
        if phrase:
            cues.append((offset + p_start, offset + min(dur, max(p_end, p_start + 0.3)), " ".join(phrase)))
        return cues

    # Proportional phrase chunking fallback (handles voices without WordBoundary events)
    words = text.split()
    if not words:
        return [(offset, offset + dur, text)]

    chunks = [" ".join(words[i:i + 4]) for i in range(0, len(words), 4)]
    total_chars = max(1, sum(len(c) for c in chunks))
    cursor = offset
    for i, ch in enumerate(chunks):
        ch_dur = (offset + dur - cursor) if i == len(chunks) - 1 else dur * (len(ch) / total_chars)
        cues.append((cursor, cursor + max(0.2, ch_dur), ch))
        cursor += ch_dur
    return cues


def _measure_duration(path: str) -> float:
    cmd = ["ffmpeg", "-i", path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
    if match:
        h, m, s = match.groups()
        return int(h) * 3600 + int(m) * 60 + float(s)
    return 5.0


def _format_srt_ts(sec: float) -> str:
    sec = max(0.0, sec)
    hrs = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        secs += 1
        ms -= 1000
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"
