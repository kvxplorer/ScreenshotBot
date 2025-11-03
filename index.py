import os
import threading
import asyncio
from io import BytesIO
from zoneinfo import ZoneInfo
from flask import Flask
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import discord
from discord.ext import commands

# ====== Flask Keep-Alive Setup ======
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!", 200

def run_flask():
    app.run(host="0.0.0.0", port=8080)

async def ping_self():
    await asyncio.sleep(5)
    url = "http://localhost:8080"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    await resp.text()
            print("Keep-alive ping sent.")
        except Exception as e:
            print(f"Keep-alive failed: {e}")
        await asyncio.sleep(20)

def keep_alive():
    thread = threading.Thread(target=run_flask)
    thread.start()
    asyncio.get_event_loop().create_task(ping_self())

# ====== Discord Bot Setup ======
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is missing!")

TARGET_CHANNEL_ID = 1432897997896941588  # For screenshots
VOICE_CHANNEL_ID = 1434983870062788618  # Voice channel to auto-join
WORDS_FILE = "words.txt"
FONT_PATH = "fonts/Inter-Regular.ttf"
FONT_BOLD_PATH = "fonts/Inter-Bold.ttf"

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True  # Needed for voice

bot = commands.Bot(command_prefix="!", intents=intents)

# ====== Keyword Monitoring ======
_keywords = set()
sent_messages = set()

def load_keywords():
    global _keywords
    if not os.path.exists(WORDS_FILE):
        open(WORDS_FILE, "a").close()
    with open(WORDS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = [line.strip().lower() for line in f if line.strip()]
        _keywords = set(lines)
    print(f"Loaded {_keywords} keywords from {WORDS_FILE}")

def match_keyword(text: str) -> bool:
    text = text.lower()
    return any(k in text for k in _keywords)

# ====== Screenshot Creation ======
async def create_screenshot(message: discord.Message) -> BytesIO:
    width, padding = 900, 30
    avatar_size = 60
    line_spacing = 10
    async with aiohttp.ClientSession() as session:
        async with session.get(str(message.author.display_avatar.replace(size=128).url)) as r:
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

# ====== Events ======
@bot.event
async def on_ready():
    load_keywords()
    print(f"Logged in as {bot.user} | {len(_keywords)} keywords loaded")
    # Auto-join voice channel
    guild = bot.guilds[0] if bot.guilds else None
    if guild:
        channel = guild.get_channel(VOICE_CHANNEL_ID)
        if channel and isinstance(channel, discord.VoiceChannel):
            if not channel.guild.voice_client:
                await channel.connect()
                print(f"Joined voice channel: {channel.name}")

# ====== Commands ======
@bot.command()
@commands.has_permissions(manage_guild=True)
async def reloadwords(ctx):
    load_keywords()
    await ctx.send(f"Reloaded {len(_keywords)} keywords.")

@bot.command()
async def join(ctx):
    if ctx.author.voice is None:
        await ctx.send("You are not connected to a voice channel.")
        return
    channel = ctx.author.voice.channel
    if ctx.voice_client is not None:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"Joined {channel.name}!")

@bot.command()
async def leave(ctx):
    if ctx.voice_client is None:
        await ctx.send("I’m not in a voice channel.")
        return
    await ctx.voice_client.disconnect()
    await ctx.send("Disconnected from the voice channel.")

# ====== Message Listener ======
@bot.listen("on_message")
async def monitor_message(message: discord.Message):
    if message.author.bot or not message.content:
        return
    if message.id in sent_messages:
        return
    if match_keyword(message.content):
        try:
            screenshot = await create_screenshot(message)
            target_ch = await bot.fetch_channel(TARGET_CHANNEL_ID)
            await target_ch.send(file=discord.File(screenshot, filename=f"{message.id}.png"))
            sent_messages.add(message.id)
        except Exception as e:
            print(f"Failed to create/send screenshot: {e}")

# ====== Run Bot ======
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
