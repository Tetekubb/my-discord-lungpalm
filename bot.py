import discord
from discord.ext import commands
import yt_dlp
import asyncio
import static_ffmpeg
import os

static_ffmpeg.add_paths()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

queue = {}

# 🔥 FIX: กัน YouTube บล็อก + รองรับ cookies
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'extract_flat': False,
    'cookiefile': 'cookies.txt',  # ถ้ามีจะช่วยได้มาก
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web']
        }
    }
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# ---------------- EMBED ----------------
def embed_now(song, user):
    e = discord.Embed(
        title="🎧 Now Playing",
        description=f"```{song['title']}```",
        color=0x0f0f0f
    )
    e.add_field(name="👤 User", value=user.mention)
    e.add_field(name="⏱️ Time", value=song['duration'])
    e.add_field(name="📊 Status", value="🟢 Playing")
    e.set_thumbnail(url=song.get("thumbnail"))
    e.set_footer(text="Tete Music System")
    return e

def embed_queue(song):
    return discord.Embed(
        description=f"➕ Added to queue\n```{song['title']}```",
        color=0x00ffaa
    )

# ---------------- CONTROL ----------------
class Control(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction, button):
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await interaction.response.send_message("⏭️ Skip", ephemeral=True)

    @discord.ui.button(label="⏸️/▶️", style=discord.ButtonStyle.success)
    async def pause(self, interaction, button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Pause", ephemeral=True)
        elif vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Resume", ephemeral=True)

    @discord.ui.button(label="🛑", style=discord.ButtonStyle.danger)
    async def stop(self, interaction, button):
        vc = interaction.guild.voice_client
        if vc:
            queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("🛑 Stop", ephemeral=True)

# ---------------- PLAYER ----------------
async def play_next(guild, channel):
    if queue.get(guild.id):
        song, user = queue[guild.id].pop(0)
        await play_song(guild, channel, song, user)

async def play_song(guild, channel, song, user):
    vc = guild.voice_client
    if not vc:
        return

    try:
        source = await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS)
    except Exception as e:  # 🔥 FIX กันเสียงพัง
        await channel.send(embed=discord.Embed(
            description="❌ เล่นเพลงไม่ได้",
            color=0xff0000
        ))
        return

    vc.play(
        source,
        after=lambda e: asyncio.run_coroutine_threadsafe(
            play_next(guild, channel), bot.loop)
    )

    await channel.send(embed=embed_now(song, user), view=Control(guild.id))

# ---------------- PLAY ----------------
async def handle_play(message, search):
    if not message.author.voice:
        return await message.channel.send(embed=discord.Embed(
            description="❌ เข้าห้องก่อน",
            color=0xff0000
        ))

    vc = message.guild.voice_client
    if not vc:
        vc = await message.author.voice.channel.connect()

    query = search if search.startswith("http") else f"ytsearch1:{search}"

    try:  # 🔥 FIX กัน yt-dlp พัง
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)
            data = info['entries'][0] if 'entries' in info else info
    except Exception as e:
        return await message.channel.send(embed=discord.Embed(
            description="❌ โหลดเพลงไม่ได้ (YouTube บล็อก)",
            color=0xff0000
        ))

    song = {
        'url': data['url'],
        'title': data['title'],
        'duration': data.get('duration_string', '0:00'),
        'thumbnail': data.get('thumbnail')
    }

    if vc.is_playing():
        queue.setdefault(message.guild.id, []).append((song, message.author))
        await message.channel.send(embed=embed_queue(song))
    else:
        await play_song(message.guild, message.channel, song, message.author)

# ---------------- AUTO ----------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.name == "🎵-music":
        try:
            await message.delete()
        except:
            pass

        await handle_play(message, message.content)

    await bot.process_commands(message)

# ---------------- SETUP ----------------
@bot.command()
async def setup(ctx):
    channel = discord.utils.get(ctx.guild.text_channels, name="🎵-music")
    if not channel:
        channel = await ctx.guild.create_text_channel("🎵-music")

    embed = discord.Embed(
        title="🎧 Tete Music",
        description="```พิมพ์ชื่อเพลงได้เลย```",
        color=0x0f0f0f
    )

    embed.add_field(name="📌 Status", value="🟢 พร้อมใช้งาน", inline=False)

    await channel.send(embed=embed, view=Control(ctx.guild.id))
    await ctx.send(f"✅ สร้าง {channel.mention}")

# ---------------- READY ----------------
@bot.event
async def on_ready():
    print(f"🔥 Bot Ready: {bot.user}")

bot.run(TOKEN)
