import discord
from discord.ext import commands
import yt_dlp
import asyncio
import static_ffmpeg
import os

# ---------------- SETUP ----------------
static_ffmpeg.add_paths()
TOKEN = os.getenv("TOKEN")

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'nocheckcertificate': True,
    'extractor_args': {'youtube': {'player_client': ['android_vr', 'web']}}
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# ---------------- BOT ----------------
class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

        self.queue = {}
        self.volume = {}

bot = MusicBot()

# ---------------- EMBED ----------------
def music_embed(song, user, status="กำลังเล่น"):
    embed = discord.Embed(
        title=f"🎵 Tete Music • {status}",
        description=f"```{song['title']}```",
        color=0x111111
    )
    embed.add_field(name="👤 ผู้ขอ", value=user.mention)
    embed.add_field(name="⏱️ เวลา", value=song['duration'])
    embed.set_thumbnail(url=song.get("thumbnail"))
    embed.set_footer(text="Tete Music System")
    return embed

def queue_embed(song, user):
    embed = discord.Embed(
        description=f"➕ เพิ่มเข้าคิว\n```{song['title']}```",
        color=0x00ffaa
    )
    embed.set_footer(text=f"โดย {user}")
    return embed

def error_embed(text):
    return discord.Embed(description=text, color=0xff0000)

# ---------------- CONTROL ----------------
class ControlView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, _):
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await interaction.response.send_message(embed=discord.Embed(description="⏭️ ข้ามเพลง"), ephemeral=True)

    @discord.ui.button(label="⏸️/▶️", style=discord.ButtonStyle.success)
    async def pause(self, interaction: discord.Interaction, _):
        vc = interaction.guild.voice_client
        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message(embed=discord.Embed(description="⏸️ พักเพลง"), ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            await interaction.response.send_message(embed=discord.Embed(description="▶️ เล่นต่อ"), ephemeral=True)

    @discord.ui.button(label="🛑", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, _):
        vc = interaction.guild.voice_client
        if vc:
            bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message(embed=discord.Embed(description="🛑 หยุดแล้ว"), ephemeral=True)

    @discord.ui.button(label="🔊+", style=discord.ButtonStyle.primary)
    async def vol_up(self, interaction: discord.Interaction, _):
        bot.volume[self.guild_id] = min(bot.volume.get(self.guild_id, 0.5) + 0.1, 1)
        await interaction.response.send_message(embed=discord.Embed(description=f"🔊 {bot.volume[self.guild_id]:.1f}"), ephemeral=True)

    @discord.ui.button(label="🔉-", style=discord.ButtonStyle.primary)
    async def vol_down(self, interaction: discord.Interaction, _):
        bot.volume[self.guild_id] = max(bot.volume.get(self.guild_id, 0.5) - 0.1, 0)
        await interaction.response.send_message(embed=discord.Embed(description=f"🔉 {bot.volume[self.guild_id]:.1f}"), ephemeral=True)

# ---------------- PLAY SYSTEM ----------------
async def play_next(guild, channel):
    if bot.queue.get(guild.id):
        song, user = bot.queue[guild.id].pop(0)
        await play_song(guild, channel, user, song)

async def play_song(guild, channel, user, song):
    vc = guild.voice_client
    if not vc:
        return

    source = await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS)

    vc.play(
        source,
        after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild, channel), bot.loop)
    )

    await channel.send(embed=music_embed(song, user), view=ControlView(guild.id))

# ---------------- PLAY FUNCTION ----------------
async def handle_play(message, search):
    if not message.author.voice:
        return await message.channel.send(embed=error_embed("❌ เข้าห้องเสียงก่อน"))

    vc = message.guild.voice_client
    if not vc:
        vc = await message.author.voice.channel.connect()

    query = search if search.startswith("http") else f"ytsearch1:{search}"

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(query, download=False)
        data = info['entries'][0] if 'entries' in info else info

    song = {
        'url': data['url'],
        'title': data['title'],
        'duration': data.get('duration_string', '0:00'),
        'thumbnail': data.get('thumbnail')
    }

    if vc.is_playing():
        bot.queue.setdefault(message.guild.id, []).append((song, message.author))
        await message.channel.send(embed=queue_embed(song, message.author))
    else:
        await play_song(message.guild, message.channel, message.author, song)

# ---------------- AUTO MESSAGE ----------------
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

# ---------------- SETUP COMMAND ----------------
@bot.command()
async def setup(ctx):
    channel = discord.utils.get(ctx.guild.text_channels, name="🎵-music")
    if not channel:
        channel = await ctx.guild.create_text_channel("🎵-music")

    embed = discord.Embed(
        title="🎧 Tete Music System",
        description="```พิมพ์ชื่อเพลง หรือวางลิงก์```",
        color=0x111111
    )

    embed.add_field(name="📌 วิธีใช้", value="พิมพ์เพลงในห้องนี้ได้เลย", inline=False)
    embed.set_footer(text="Tete Music")

    await channel.send(embed=embed, view=ControlView(ctx.guild.id))
    await ctx.send(embed=discord.Embed(description=f"✅ สร้าง {channel.mention} แล้ว", color=0x00ff00))

# ---------------- RUN ----------------
bot.run(TOKEN)
