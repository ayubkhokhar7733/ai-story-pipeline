# AI Story Pipeline

Automated cloud AI storytelling video generation pipeline using Groq, Edge-TTS, pure FFmpeg (zero local GPU), and resumable YouTube Data API v3 uploads via GitHub Actions.

## Features
- **Formats:** `9:16` vertical Shorts (`1080x1920`) and `16:9` landscape (`1920x1080`).
- **Script Engine:** Fast-paced scene-by-scene storytelling via Groq API (`core/script_engine.py`).
- **Neural Voiceover:** Free English & Urdu narration via `edge-tts` (`en-US-GuyNeural`, `ur-PK-AsadNeural`, etc.) with exact per-scene timing and SRT subtitle generation (`core/tts_engine.py`).
- **Zero-GPU Rendering:** Pure FFmpeg Ken Burns camera motion (`zoom_in`, `zoom_out`, `pan_left`, `pan_right`), subtle ambient pad audio mix, and burned-in subtitles (`core/video_composer.py`).
- **YouTube Uploader:** Resumable chunked upload with mandatory `status.containsSyntheticMedia: true` and `unlisted` default privacy (`core/youtube_uploader.py`).

## Quick Local Run
```bash
pip install -r requirements.txt
python generate_video.py --topic "The Clockmaker Who Stole Midnight" --aspect 9:16 --voice en-US-GuyNeural
```
