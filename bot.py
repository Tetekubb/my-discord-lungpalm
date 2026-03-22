import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import static_ffmpeg
import os

static_ffmpeg.add_paths()
TOKEN = os.getenv('TOKEN')
MY_GUILD_ID = discord.Object(id=1467879682019033088)

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

    async def setup_hook(self):
        self.tree.copy_global_to(guild=MY_GUILD_ID)
        await self.tree.sync(guild=MY_GUILD_ID)
        print("🔥 Tete Music Ultra Ready!")

bot = MusicBot()

# ---------------- EMBED ----------------
def now_playing_embed(song, user):
    embed = discord.Embed(
        title="🎶 กำลังเล่นเพลง",
        description=f"```{song['title']}```",
        color=0xff0044
    )
    embed.add_field(name="👤 ขอโดย", value=user.mention)
    embed.add_field(name="⏱️ เวลา", value=song['duration'])
    embed.set_thumbnail(url=song.get("thumbnail"))
    return embed

# ---------------- VIEW ----------------
class ControlView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, _):
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await interaction.response.send_message("⏭️ ข้ามแล้ว", ephemeral=True)

    @discord.ui.button(label="⏸️/▶️", style=discord.ButtonStyle.success)
    async def pause(self, interaction: discord.Interaction, _):
        vc = interaction.guild.voice_client
        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ พัก", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ เล่นต่อ", ephemeral=True)

    @discord.ui.button(label="🛑", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, _):
        vc = interaction.guild.voice_client
        if vc:
            bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("🛑 หยุดแล้ว", ephemeral=True)

    @discord.ui.button(label="🔊+", style=discord.ButtonStyle.primary)
    async def vol_up(self, interaction: discord.Interaction, _):
        bot.volume[self.guild_id] = min(bot.volume.get(self.guild_id, 0.5) + 0.1, 1)
        await interaction.response.send_message(f"🔊 Volume: {bot.volume[self.guild_id]:.1f}", ephemeral=True)

    @discord.ui.button(label="🔉-", style=discord.ButtonStyle.primary)
    async def vol_down(self, interaction: discord.Interaction, _):
        bot.volume[self.guild_id] = max(bot.volume.get(self.guild_id, 0.5) - 0.1, 0)
        await interaction.response.send_message(f"🔉 Volume: {bot.volume[self.guild_id]:.1f}", ephemeral=True)

# ---------------- PLAY ENGINE ----------------
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

    await channel.send(embed=now_playing_embed(song, user), view=ControlView(guild.id))

# ---------------- COMMAND ----------------
@bot.tree.command(name="play")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        return await interaction.followup.send("❌ เข้าห้องก่อน")

    vc = interaction.guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect()

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
        bot.queue.setdefault(interaction.guild_id, []).append((song, interaction.user))
        await interaction.followup.send(f"➕ เพิ่มคิว: {song['title']}")
    else:
        await play_song(interaction.guild, interaction.channel, interaction.user, song)

# ---------------- QUEUE ----------------
@bot.tree.command(name="queue")
async def queue(interaction: discord.Interaction):
    q = bot.queue.get(interaction.guild_id, [])
    if not q:
        return await interaction.response.send_message("❌ ไม่มีคิว")

    text = "\n".join([f"{i+1}. {s[0]['title']}" for i, s in enumerate(q[:10])])
    await interaction.response.send_message(f"📜 คิวเพลง:\n{text}")

# ---------------- RUN ----------------
bot.run(TOKEN)
