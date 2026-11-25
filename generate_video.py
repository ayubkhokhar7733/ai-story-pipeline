#!/usr/bin/env python3
"""
generate_video.py - End-to-end AI Storytelling Video Pipeline & YouTube Uploader.
Supports 9:16 Vertical Shorts and 16:9 Landscape with zero local GPU dependency.
"""
import argparse
import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import config
from core.image_engine import generate_scene_images
from core.script_engine import generate_story_script, resolve_voice
from core.tts_engine import generate_story_audio
from core.video_composer import compose_story_video
from core.youtube_uploader import upload_video


def run_pipeline(
    topic: str,
    aspect: str = "9:16",
    voice: str = "en-US-GuyNeural",
    character: str = "leo_fox",
    duration: int = 40,
    upload_youtube: bool = False,
    privacy: str = "unlisted",
) -> dict:
    t0 = time.time()
    resolved_voice = resolve_voice(voice)
    preset = config.ASPECT_PRESETS.get(aspect, config.ASPECT_PRESETS["9:16"])

    print("=" * 64, flush=True)
    print("AI STORYTELLING VIDEO PIPELINE", flush=True)
    print(f"Topic:     {topic}", flush=True)
    print(f"Character: {character}", flush=True)
    print(f"Format:    {aspect} ({preset['width']}x{preset['height']})", flush=True)
    print(f"Voice:     {resolved_voice}", flush=True)
    print(f"Duration:  ~{duration}s", flush=True)
    print(f"Upload YT: {upload_youtube} (privacy={privacy})", flush=True)
    print("=" * 64, flush=True)

    # 1. Script via Groq API
    print("\n[1/4] Generating fast-paced scene-by-scene script via Groq API...", flush=True)
    story = generate_story_script(
        topic=topic,
        target_seconds=duration,
        character_id=character,
        voice=resolved_voice,
    )
    title = story.get("title", topic)
    scenes = story.get("scenes", [])
    print(f"Title: {title} ({len(scenes)} scenes)", flush=True)

    # 2. Scene artwork (zero local GPU)
    print("\n[2/4] Generating scene-by-scene artwork...", flush=True)
    scenes = generate_scene_images(scenes, aspect=aspect)

    # 3. Free neural voiceover + synchronized SRT
    print("\n[3/4] Synthesizing Edge-TTS voiceover & SRT subtitles...", flush=True)
    audio_path, srt_path, actual_dur, scenes = generate_story_audio(scenes, voice_name=resolved_voice)

    # 4. Pure FFmpeg render with Ken Burns motion + subtitle burn-in
    print("\n[4/4] Rendering MP4 via pure FFmpeg...", flush=True)
    video_path = compose_story_video(
        scenes=scenes,
        audio_path=audio_path,
        srt_path=srt_path,
        title=title,
        aspect=aspect,
    )

    elapsed = round(time.time() - t0, 1)
    size_mb = round(os.path.getsize(video_path) / (1024 * 1024), 2)
    print(f"\nRender complete in {elapsed}s -> {video_path} ({actual_dur:.1f}s, {size_mb} MB)", flush=True)

    result = {
        "title": title,
        "topic": topic,
        "aspect": aspect,
        "voice": resolved_voice,
        "character": character,
        "duration_sec": round(actual_dur, 2),
        "video_path": video_path,
        "size_mb": size_mb,
        "elapsed_sec": elapsed,
        "video_id": None,
        "video_url": None,
    }

    # 5. Resumable YouTube upload with containsSyntheticMedia=True
    if upload_youtube:
        print("\n[5/5] Uploading video to YouTube...", flush=True)
        yt_res = upload_video(
            video_path=video_path,
            title=title,
            description=story.get("description", f"{title}\n\nGenerated with AI Story Pipeline."),
            tags=story.get("tags", ["AIStory", "Storytelling", "Animation"]),
            privacy_status=privacy,
            contains_synthetic_media=True,
        )
        result["video_id"] = yt_res["video_id"]
        result["video_url"] = yt_res["video_url"]
        print(f"Live YouTube URL: {yt_res['video_url']}", flush=True)

    result_json = os.path.join(config.OUTPUT_DIR, "result.json")
    with open(result_json, "w", encoding="utf-8") as f_res:
        json.dump(result, f_res, indent=2, ensure_ascii=False)

    return result


def main():
    parser = argparse.ArgumentParser(description="Automated AI Storytelling Video Generator & YouTube Uploader")
    parser.add_argument("--topic", "-t", type=str, default="The Clockmaker Who Stole Five Minutes of Midnight", help="Story topic or prompt")
    parser.add_argument("--aspect", "-a", type=str, default="9:16", choices=["9:16", "16:9"], help="9:16 Shorts or 16:9 Landscape")
    parser.add_argument("--voice", "-v", type=str, default="en-US-GuyNeural", help="Edge-TTS voice name or alias (e.g. en-US-GuyNeural, ur-PK-AsadNeural)")
    parser.add_argument("--character", "-c", type=str, default="leo_fox", choices=list(config.CHARACTERS.keys()) + ["none"], help="Storytelling character concept")
    parser.add_argument("--duration", "-d", type=int, default=40, help="Target video duration in seconds")
    parser.add_argument("--upload-youtube", action="store_true", help="Upload rendered MP4 to YouTube")
    parser.add_argument("--privacy", type=str, default="unlisted", choices=["unlisted", "private", "public"], help="YouTube privacy status")
    args = parser.parse_args()

    try:
        run_pipeline(
            topic=args.topic,
            aspect=args.aspect,
            voice=args.voice,
            character=args.character,
            duration=args.duration,
            upload_youtube=args.upload_youtube,
            privacy=args.privacy,
        )
    except Exception as exc:
        print(f"\n[ERROR] Pipeline failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
