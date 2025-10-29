import os
from io import BytesIO
from zoneinfo import ZoneInfo
import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is missing!")

TARGET_CHANNEL_ID = 1365172206195179600
WORDS_FILE = "words.txt"
FONT_PATH = "fonts/Inter-Regular.ttf"
FONT_BOLD_PATH = "fonts/Inter-Bold.ttf"

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
    width, padding = 850, 25
    avatar_size = 50
    line_spacing = 8
    corner_radius = 25

    async with aiohttp.ClientSession() as session:
        async with session.get(str(message.author.display_avatar.replace(size=128).url)) as r:
            avatar_bytes = await r.read()
    avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
    avatar = avatar.resize((avatar_size, avatar_size))
    avatar = ImageOps.fit(avatar, (avatar_size, avatar_size), centering=(0.5, 0.5))
    mask = Image.new("L", avatar.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
    avatar.putalpha(mask)

    user_text = f"{message.author.display_name}#{message.author.discriminator}"
    pst = message.created_at.astimezone(ZoneInfo("America/Los_Angeles"))
    timestamp = pst.strftime("%b %d, %Y %I:%M %p")
    content_text = message.content

    try:
        font_user = ImageFont.truetype(FONT_BOLD_PATH, 22)
        font_content = ImageFont.truetype(FONT_PATH, 20)
        font_time = ImageFont.truetype(FONT_PATH, 16)
    except OSError:
        font_user = font_content = font_time = ImageFont.load_default()

    temp_img = Image.new("RGB", (width, 100))
    draw = ImageDraw.Draw(temp_img)
    bbox = draw.textbbox((0,0), "Hg", font=font_content)
    line_height = (bbox[3] - bbox[1]) + line_spacing
    lines = content_text.splitlines()
    user_bbox = draw.textbbox((0,0), user_text, font=font_user)
    user_height = user_bbox[3] - user_bbox[1]
    height = padding*2 + max(avatar_size, user_height + 5 + line_height*len(lines))

    img = Image.new("RGB", (width, height), "#36393F")
    draw = ImageDraw.Draw(img)
    img.paste(avatar, (padding, padding), avatar)

    # Username with subtle shadow
    x_user = padding + avatar_size + 15
    y_user = padding
    shadow_offset = 1
    draw.text((x_user+shadow_offset, y_user+shadow_offset), user_text, font=font_user, fill="#000000")
    draw.text((x_user, y_user), user_text, font=font_user, fill="#ffffff")

    # Timestamp
    draw.text((x_user, y_user + user_height + 2), timestamp, font=font_time, fill="#B9BBBE")

    # Message content with shadow
    y_text = padding + avatar_size // 2 + 12
    for line in lines:
        draw.text((x_user+shadow_offset, y_text+shadow_offset), line, font=font_content, fill="#000000")
        draw.text((x_user, y_text), line, font=font_content, fill="#ffffff")
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
