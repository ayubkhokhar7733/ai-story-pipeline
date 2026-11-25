"""
config.py - Configuration for AI Story Pipeline (9:16 Shorts & 16:9 Landscape).
"""
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

for folder in [ASSETS_DIR, TEMP_DIR, OUTPUT_DIR]:
    os.makedirs(folder, exist_ok=True)

# API Keys & Settings
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODELS = [
    os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip(),
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

AI_HORDE_API_KEY = os.getenv("AI_HORDE_API_KEY", "0000000000").strip()
AI_HORDE_BASE_URL = os.getenv("AI_HORDE_BASE_URL", "https://aihorde.net/api/v2").strip()
AI_HORDE_CLIENT_AGENT = os.getenv("AI_HORDE_CLIENT_AGENT", "AIStoryPipeline:1.0.0:github-actions").strip()

# Video Aspect Presets
ASPECT_PRESETS = {
    "9:16": {
        "width": 1080,
        "height": 1920,
        "image_width": 768,
        "image_height": 1344,
        "subtitle_font_size": 16,
        "subtitle_margin_v": 35,
    },
    "16:9": {
        "width": 1920,
        "height": 1080,
        "image_width": 1344,
        "image_height": 768,
        "subtitle_font_size": 18,
        "subtitle_margin_v": 25,
    },
}
DEFAULT_ASPECT = "9:16"
FPS = 30

# Free Neural Edge-TTS Voices (aliases + direct voice IDs)
VOICE_ALIASES = {
    "guy": "en-US-GuyNeural",
    "christopher": "en-US-ChristopherNeural",
    "jenny": "en-US-JennyNeural",
    "aria": "en-US-AriaNeural",
    "ryan": "en-GB-RyanNeural",
    "sonia": "en-GB-SoniaNeural",
    "asad": "ur-PK-AsadNeural",
    "uzma": "ur-PK-UzmaNeural",
    "salman": "ur-IN-SalmanNeural",
    "gul": "ur-IN-GulNeural",
}
DEFAULT_VOICE = "en-US-GuyNeural"

# Consistent Storytelling Character Concepts
CHARACTERS = {
    "leo_fox": {
        "name": "Leo the Lantern Fox",
        "title": "Curiosity-Driven Midnight Explorer",
        "visual_tokens": (
            "stylized 3D animated storybook character, clever young orange fox named Leo "
            "wearing a starry indigo scarf and carrying a glowing brass lantern, expressive amber eyes"
        ),
        "style": "cinematic Pixar-inspired 3D animation, warm volumetric lighting, rich color palette",
        "catchphrase": "Every shadow hides a doorway if you know where to shine the light.",
    },
    "chacha_bashir": {
        "name": "Chacha Bashir",
        "title": "Legendary Lahore Rickshaw Storyteller",
        "visual_tokens": (
            "stylized 3D animated character, cheerful Pakistani elder named Chacha Bashir "
            "with a twirled handlebar mustache, aviator glasses, emerald embroidered waistcoat over crisp white kurta"
        ),
        "style": "vibrant stylized 3D animation, warm golden-hour street lighting, rich cultural detail",
        "catchphrase": "Hold tight, friend—this story moves faster than Lahore traffic!",
    },
    "zainab_explorer": {
        "name": "Zainab the Explorer",
        "title": "Ancient Mysteries & Lost Cities Investigator",
        "visual_tokens": (
            "stylized 3D adventure character, resourceful young archaeologist named Zainab "
            "with brass goggles on her forehead, deep blue tunic, khaki field vest, and leather satchel"
        ),
        "style": "stylized 3D adventure animation, dramatic torchlight and atmospheric dust motes",
        "catchphrase": "History never truly sleeps—it waits for someone brave enough to listen.",
    },
    "captain_orion": {
        "name": "Captain Orion",
        "title": "Deep-Ocean & Starlight Chronicler",
        "visual_tokens": (
            "stylized 3D animated explorer, Captain Orion wearing a weathered bronze diving coat "
            "with glowing cyan compass badge and silver-streaked hair"
        ),
        "style": "bioluminescent stylized 3D storybook animation, deep teal and amber contrast",
        "catchphrase": "Beyond the map's edge is where the real story begins.",
    },
}

CARTOON_IMAGE_MODELS = [
    "Deliberate",
    "Dreamshaper",
    "Rev Animated",
    "Anything v5",
    "stable_diffusion",
]

STYLE_SUFFIX = (
    "stylized animated film still, expressive storytelling composition, cinematic lighting, "
    "rich colors, clean detail, no text, no watermark"
)

NEGATIVE_PROMPT = (
    "text, watermark, signature, logo, blurry, deformed, mutated hands, extra limbs, "
    "low quality, jpeg artifacts, ugly, monochrome"
)

# Audio Mixing
MUSIC_VOLUME = 0.10
VOICE_RATE = "+0%"
