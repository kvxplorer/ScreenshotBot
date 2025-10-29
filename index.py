import os
import re
import unicodedata
from io import BytesIO
from zoneinfo import ZoneInfo
import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is missing!")

TARGET_CHANNEL_ID = 1432897997896941588
WORDS_FILE = "words.txt"
FONT_PATH = "fonts/Inter-Regular.ttf"
FONT_BOLD_PATH = "fonts/Inter-Bold.ttf"

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

_keywords = set()

_HOMOGLYPHS = {
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4", "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "ａ": "a", "ｂ": "b", "ｃ": "c", "ｅ": "e", "ｉ": "i", "ｌ": "l", "ｏ": "o", "ｎ": "n", "ｇ": "g",
    "ɡ": "g", "ι": "i", "ı": "i", "Ꭓ": "t",
}

_HOMO_RE = re.compile("|".join(re.escape(k) for k in _HOMOGLYPHS.keys())) if _HOMOGLYPHS else None

_LEET_MAP = str.maketrans({
    "0": "o",
    "1": "i",
    "2": "z",
    "3": "e",
    "4": "a",
    "5": "s",
    "6": "g",
    "7": "t",
    "8": "b",
    "9": "g",
    "@": "a",
    "!": "i",
    "$": "s",
    "+": "t",
    "|": "i",
    "(": "c",
    ")": "c",
    "-": "",
    "_": "",
    " ": "",
})

def _map_homoglyphs(s: str) -> str:
    if not _HOMO_RE:
        return s
    return _HOMO_RE.sub(lambda m: _HOMOGLYPHS[m.group(0)], s)

def normalize_text_for_matching(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = _map_homoglyphs(s)
    s = s.translate(_LEET_MAP)
    s = re.sub(r"[^A-Za-z0-9]+", "", s)
    s = re.sub(r"(.)\1{2,}", r"\1\1", s)
    s = s.lower()
    return s

def load_keywords():
    global _keywords
    if not os.path.exists(WORDS_FILE):
        open(WORDS_FILE, "a", encoding="utf-8").close()
    normalized_set = set()
    with open(WORDS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            norm = normalize_text_for_matching(raw)
            if norm:
                normalized_set.add(norm)
    _keywords = normalized_set
    print(f"Loaded {len(_keywords)} normalized keywords from {WORDS_FILE}")

def match_keyword(text: str) -> bool:
    if not text:
        return False
    normalized_text = normalize_text_for_matching(text)
    if not normalized_text:
        return False
    for kw in _keywords:
        if kw and kw in normalized_text:
            return True
    return False

async def create_screenshot(message: discord.Message) -> BytesIO:
    width, padding = 900, 30
    avatar_size = 60
    line_spacing = 10
    async with aiohttp.ClientSession() as session:
        avatar_url = str(message.author.display_avatar.replace(size=128).url)
        async with session.get(avatar_url) as r:
            avatar_bytes = await r.read()
    avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
    avatar = avatar.resize((avatar_size, avatar_size))
    mask = Image.new("L", (avatar_size, avatar_size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
    avatar.putalpha(mask)
    user_text = f"{message.author.display_name}#{message.author.discriminator}"
    pst = message.created_at.astimezone(ZoneInfo("America/Los_Angeles"))
    timestamp = pst.strftime("%b %d, %Y %I:%M %p")
    content_text = message.content.strip()
    try:
        font_user = ImageFont.truetype(FONT_BOLD_PATH, 26)
        font_content = ImageFont.truetype(FONT_PATH, 23)
        font_time = ImageFont.truetype(FONT_PATH, 17)
    except OSError:
        font_user = font_content = font_time = ImageFont.load_default()
    temp_img = Image.new("RGB", (width, 200))
    draw = ImageDraw.Draw(temp_img)
    content_height = sum((draw.textbbox((0, 0), line, font=font_content)[3] for line in content_text.splitlines()))
    total_height = padding * 2 + max(avatar_size, 60 + content_height + 20)
    img = Image.new("RGB", (width, total_height), "#2C2F33")
    draw = ImageDraw.Draw(img)
    img.paste(avatar, (padding, padding), avatar)
    x_text = padding + avatar_size + 15
    y_text = padding
    draw.text((x_text + 1, y_text + 1), user_text, font=font_user, fill="#000000")
    draw.text((x_text, y_text), user_text, font=font_user, fill="#FFFFFF")
    draw.text((x_text, y_text + 30), timestamp, font=font_time, fill="#B9BBBE")
    y_text += 65
    for line in content_text.splitlines():
        draw.text((x_text + 1, y_text + 1), line, font=font_content, fill="#000000")
        draw.text((x_text, y_text), line, font=font_content, fill="#FFFFFF")
        y_text += draw.textbbox((0, 0), line, font=font_content)[3] + line_spacing
    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output

@bot.event
async def on_ready():
    load_keywords()
    print(f"Logged in as {bot.user} | {len(_keywords)} normalized keywords loaded")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def reloadwords(ctx):
    load_keywords()
    await ctx.send(f"Reloaded {len(_keywords)} keywords.")

@bot.listen("on_message")
async def monitor_message(message: discord.Message):
    if message.author.bot or not message.content:
        return
    try:
        if match_keyword(message.content):
            print(f"Trigger word detected in message id {message.id}")
            try:
                screenshot = await create_screenshot(message)
                target_ch = await bot.fetch_channel(TARGET_CHANNEL_ID)
                await target_ch.send(file=discord.File(screenshot, filename=f"{message.id}.png"))
                print(f"Screenshot sent for message id {message.id}")
            except Exception as e:
                print(f"Failed to create/send screenshot: {e}")
    except Exception as exc:
        print(f"Error during keyword check for message {message.id}: {exc}")

if __name__ == "__main__":
    bot.run(TOKEN)
