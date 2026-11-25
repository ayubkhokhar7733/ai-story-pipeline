"""
core/script_engine.py - Fast-paced scene-by-scene storytelling script generator via Groq API.
"""
import json
import re
import requests
import config

SYSTEM_PROMPT = """You are a master short-form & documentary storyteller for an animated YouTube channel.
Write fast-paced, captivating, visually vivid stories split into tight micro-scenes (5-6 seconds each).

RULES:
1. HOOK IMMEDIATELY: Start Scene 1 with intrigue, action, or a striking mystery—never generic openings.
2. FAST PACING: Each scene is 1-2 punchy spoken sentences (~14-18 words per scene).
3. VISUAL-NARRATIVE LOCK: Every scene's `visual_prompt` must literally depict the physical setting, action, emotion, and props mentioned in that scene's `narration`. Always write `visual_prompt` in English even if `narration` is in Urdu.
4. CHARACTER CONSISTENCY: Keep the protagonist's appearance, outfit, and signature props consistent across every scene.
5. STRICT JSON ONLY: Output only valid JSON matching the requested schema. No markdown fences or commentary."""


def resolve_voice(voice_input: str) -> str:
    if not voice_input:
        return config.DEFAULT_VOICE
    key = voice_input.strip().lower()
    return config.VOICE_ALIASES.get(key, voice_input.strip())


def generate_story_script(
    topic: str,
    target_seconds: int = 45,
    character_id: str = None,
    voice: str = None,
) -> dict:
    """Generates a scene-by-scene storytelling script JSON using Groq API."""
    resolved_voice = resolve_voice(voice)
    is_urdu = resolved_voice.lower().startswith("ur-")
    narration_lang = "Urdu (natural conversational Urdu script in Perso-Arabic script)" if is_urdu else "English"

    scene_count = max(4, min(12, round(target_seconds / 5.5)))
    target_words = round(target_seconds * 2.5)

    char_data = config.CHARACTERS.get(character_id) if character_id and character_id != "none" else None

    char_block = ""
    if char_data:
        char_block = (
            f"\nPROTAGONIST:\n"
            f"- Name: {char_data['name']} ({char_data['title']})\n"
            f"- Visual Anchor: {char_data['visual_tokens']}\n"
            f"- Art Style: {char_data['style']}\n"
            f"- Signature theme/quote to echo naturally: \"{char_data['catchphrase']}\"\n"
        )

    user_prompt = f"""Create an engaging animated scene-by-scene story about: "{topic}".

SPECIFICATIONS:
- Narration Language: {narration_lang}
- Target Duration: ~{target_seconds} seconds
- Total Scenes: Exactly {scene_count} scenes
- Total Spoken Word Count: ~{target_words} words across all scenes (~14-18 words per scene)
{char_block}
REQUIRED JSON SCHEMA:
{{
  "title": "Compelling YouTube title (max 75 chars, in {narration_lang})",
  "description": "2-sentence YouTube video description with 3 relevant hashtags",
  "tags": ["AIStory", "Storytelling", "Animation", "ShortStory"],
  "character_anchor": "{char_data['visual_tokens'] if char_data else 'Consistent visual description of the main character in English'}",
  "scenes": [
    {{
      "scene_id": 1,
      "narration": "Spoken line for scene 1 in {narration_lang}.",
      "visual_prompt": "Vivid literal English image prompt showing what happens in scene 1",
      "camera_motion": "zoom_in",
      "mood": "mystery"
    }}
  ]
}}

Allowed `camera_motion` values: "zoom_in", "zoom_out", "pan_left", "pan_right".
Allowed `mood` values: "mystery", "wonder", "tension", "triumph".
Return exactly {scene_count} scenes as valid JSON."""

    if config.GROQ_API_KEY:
        headers = {
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        for model_name in config.GROQ_MODELS:
            if not model_name:
                continue
            try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.75,
                    "max_tokens": 2200,
                    "response_format": {"type": "json_object"},
                }
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=35,
                )
                if resp.status_code == 200:
                    raw = resp.json()["choices"][0]["message"].get("content", "").strip()
                    parsed = _parse_json_safely(raw)
                    if parsed and parsed.get("scenes"):
                        print(f"[script_engine] Generated {len(parsed['scenes'])} scenes via Groq ({model_name}).", flush=True)
                        _enrich_visual_prompts(parsed, char_data)
                        return parsed
                else:
                    print(f"[script_engine] Groq model {model_name} HTTP {resp.status_code}: {resp.text[:200]}", flush=True)
            except Exception as exc:
                print(f"[script_engine] Groq model {model_name} failed: {exc}", flush=True)

    print("[script_engine] Falling back to built-in story generator.", flush=True)
    fallback = _generate_fallback_story(topic, scene_count, is_urdu, char_data)
    _enrich_visual_prompts(fallback, char_data)
    return fallback


def _enrich_visual_prompts(story: dict, char_data: dict = None):
    char_anchor = (char_data["visual_tokens"] if char_data else story.get("character_anchor", "")).strip()
    style = char_data["style"] if char_data else config.STYLE_SUFFIX
    motions = ["zoom_in", "pan_right", "zoom_out", "pan_left"]

    for idx, scene in enumerate(story.get("scenes", []), 1):
        scene.setdefault("scene_id", idx)
        if scene.get("camera_motion") not in motions:
            scene["camera_motion"] = motions[(idx - 1) % len(motions)]
        if not scene.get("mood"):
            scene["mood"] = "wonder"

        base_prompt = scene.get("visual_prompt", "").strip()
        if char_anchor and char_anchor.lower() not in base_prompt.lower():
            scene["full_image_prompt"] = f"{char_anchor}, {base_prompt}, {style}"
        else:
            scene["full_image_prompt"] = f"{base_prompt}, {style}"


def _parse_json_safely(text: str) -> dict:
    if not text:
        return None
    # Remove reasoning blocks if present
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                return None
    return None


def _generate_fallback_story(topic: str, scene_count: int, is_urdu: bool, char_data: dict = None) -> dict:
    clean_topic = topic.strip() or "The Midnight Lantern"
    anchor = char_data["visual_tokens"] if char_data else "young explorer carrying a glowing brass lantern"

    if is_urdu:
        base_scenes = [
            ("رات کے سناٹے میں اچانک ایک پراسرار روشنی نے اس کہانی کا دروازہ کھول دیا۔", "character discovering a glowing golden doorway in a quiet misty alley at night", "zoom_in", "mystery"),
            ("ہر قدم کے ساتھ فضا میں سنہری چنگاریاں بکھرنے لگیں اور پرانا راز جاگ اٹھا۔", "character walking across an ancient stone courtyard lit by floating golden sparks", "pan_right", "wonder"),
            ("دیوار پر بنے قدیم نقش اچانک چمک اٹھے جیسے صدیوں بعد کوئی جواب ملا ہو۔", "close up of glowing carved runes on ancient stone wall illuminating character's face", "zoom_out", "tension"),
            ("آخری موڑ پر وہ حقیقت سامنے آئی جس نے پوری دنیا کو حیران کر دیا۔", "character standing before a radiant sunrise horizon overlooking a magical valley", "pan_left", "triumph"),
        ]
        title = f"{clean_topic[:55]} | دلچسپ کہانی"
    else:
        base_scenes = [
            (f"At midnight, a faint golden pulse beneath the cobblestones revealed the secret of {clean_topic}.", "character kneeling beside a glowing golden crack in misty cobblestones at midnight", "zoom_in", "mystery"),
            ("With every cautious step forward, forgotten lanterns flickered alive along the silent corridor.", "character walking down an ancient stone corridor as warm lanterns ignite one by one", "pan_right", "wonder"),
            ("Then a towering clockwork seal groaned open, unleashing swirling stardust into the chamber.", "dramatic wide shot of a giant ornate brass clockwork door opening with swirling golden dust", "zoom_out", "tension"),
            ("By dawn, one fearless step had turned an impossible myth into an unforgettable legend.", "character smiling on a high overlook as golden sunrise light fills a breathtaking valley", "pan_left", "triumph"),
        ]
        title = f"The Secret of {clean_topic[:55]}"

    scenes = []
    for i in range(scene_count):
        narr, vis, mot, mood = base_scenes[i % len(base_scenes)]
        scenes.append({
            "scene_id": i + 1,
            "narration": narr,
            "visual_prompt": vis,
            "camera_motion": mot,
            "mood": mood,
        })

    return {
        "title": title,
        "description": f"{title}\n\nAutomated AI storytelling video.\n#AIStory #Animation #Storytelling",
        "tags": ["AIStory", "Storytelling", "Animation", "Shorts"],
        "character_anchor": anchor,
        "scenes": scenes,
    }
