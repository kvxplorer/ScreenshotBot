import os
from io import BytesIO
from zoneinfo import ZoneInfo
import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

TOKEN = "MTQzMjg4MzU1MDYxMjM1NzE0MQ.G8KQ04.5OoQhVLAcadZCe3vVBJWo6vt8_fG-NYp2YnesQ"
TARGET_CHANNEL_ID = 1365172206195179600
WORDS_FILE = "words.txt"
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

_keywords = set()

def load_keywords():
    global _keywords
    if not os.path.exists(WORDS_FILE):
        open(WORDS_FILE, "a").close()
    with open(WORDS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        cleaned = []
        for line in lines:
            line = line.strip().lower().replace("\r", "")
            if line:
                cleaned.append(line)
        _keywords = set(cleaned)
    print(f"Raw lines from words.txt: {cleaned}")
    print(f"Loaded {len(_keywords)} keywords from {WORDS_FILE}")

def match_keyword(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in _keywords)

async def create_screenshot(message: discord.Message) -> BytesIO:
    width, padding = 800, 20
    avatar_size = 48
    line_spacing = 6

    async with aiohttp.ClientSession() as session:
        async with session.get(str(message.author.display_avatar.replace(size=128).url)) as r:
            avatar_bytes = await r.read()
    avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
    avatar = avatar.resize((avatar_size, avatar_size))

    user_text = f"{message.author.display_name}#{message.author.discriminator}"
    pst = message.created_at.astimezone(ZoneInfo("America/Los_Angeles"))
    timestamp = pst.strftime("%b %d, %Y %I:%M %p")
    content_text = message.content

    try:
        font_user = ImageFont.truetype(FONT_PATH, 20)
        font_content = ImageFont.truetype(FONT_PATH, 18)
        font_time = ImageFont.truetype(FONT_PATH, 14)
    except OSError:
        font_user = font_content = font_time = ImageFont.load_default()

    temp_img = Image.new("RGB", (width, 100))
    draw = ImageDraw.Draw(temp_img)
    bbox = draw.textbbox((0, 0), "Hg", font=font_content)
    line_height = (bbox[3] - bbox[1]) + line_spacing

    lines = content_text.splitlines()
    user_bbox = draw.textbbox((0, 0), user_text, font=font_user)
    user_height = user_bbox[3] - user_bbox[1]
    height = padding * 2 + max(avatar_size, user_height + 5 + line_height * len(lines))

    img = Image.new("RGB", (width, height), "#36393F")
    draw = ImageDraw.Draw(img)
    img.paste(avatar, (padding, padding), avatar)
    draw.text((padding + avatar_size + 10, padding), user_text, font=font_user, fill="white")
    draw.text((padding + avatar_size + 10, padding + user_height + 2), timestamp, font=font_time, fill="#B9BBBE")

    y_text = padding + avatar_size // 2 + 10
    for line in lines:
        draw.text((padding + avatar_size + 10, y_text), line, font=font_content, fill="white")
        y_text += line_height

    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output

@bot.event
async def on_ready():
    load_keywords()
    print(f"Logged in as {bot.user} | {len(_keywords)} keywords loaded")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def reloadwords(ctx):
    load_keywords()
    await ctx.send(f"Reloaded {len(_keywords)} keywords.")

@bot.event
async def on_message(message):
    if message.author.bot or not message.content:
        await bot.process_commands(message)
        return

    if match_keyword(message.content):
        print(f"Trigger word detected in message id {message.id}")
        try:
            screenshot = await create_screenshot(message)
            target_ch = await bot.fetch_channel(TARGET_CHANNEL_ID)
            await target_ch.send(file=discord.File(screenshot, filename=f"{message.id}.png"))
            print(f"Screenshot sent for message id {message.id}")
        except Exception as e:
            print(f"Failed to create/send screenshot: {e}")

    await bot.process_commands(message)

if __name__ == "__main__":
    bot.run(TOKEN)
