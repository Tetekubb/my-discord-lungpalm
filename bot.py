import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import static_ffmpeg
import os

# --- [ระบบพื้นฐาน] ---
static_ffmpeg.add_paths()
TOKEN = os.getenv('TOKEN')
MY_GUILD_ID = discord.Object(id=1470028388335882394)

# --- [YTDL & FFMPEG Optimized] ---
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',
    'extract_flat': True, # ช่วยให้ดึงข้อมูลไวขึ้นมาก
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

class MusicView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(emoji="🛑", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("⏹️ หยุดเล่นและออกจากห้อง", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ ข้ามเพลงเรียบร้อย", ephemeral=True)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary)
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸️ พักเพลง", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                await interaction.response.send_message("▶️ เล่นต่อ", ephemeral=True)

    @discord.ui.button(label="AutoPlay", emoji="🔄", style=discord.ButtonStyle.success)
    async def autoplay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.bot.autoplay.get(self.guild_id, False)
        self.bot.autoplay[self.guild_id] = not current
        status = "เปิด ✅" if not current else "ปิด ❌"
        await interaction.response.send_message(f"ระบบ AutoPlay: {status}", ephemeral=True)

    @discord.ui.button(label="Queue", emoji="📋", style=discord.ButtonStyle.primary)
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = self.bot.queue.get(self.guild_id, [])
        if not q:
            return await interaction.response.send_message("ขณะนี้ไม่มีคิวเพลง", ephemeral=True)
        desc = "\n".join([f"{i+1}. {s['title']}" for i, s in enumerate(q[:10])])
        embed = discord.Embed(title="รายการคิวเพลง (10 เพลงแรก)", description=f"```\n{desc}\n```", color=0x3498db)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.queue = {}
        self.autoplay = {}
        self.last_track = {}

    async def setup_hook(self):
        self.tree.copy_global_to(guild=MY_GUILD_ID)
        await self.tree.sync(guild=MY_GUILD_ID)
        print(f"✅ บอทระบบเพลงออนไลน์แล้ว!")

bot = MusicBot()

async def play_next(guild, channel, user):
    guild_id = guild.id
    if guild_id in bot.queue and bot.queue[guild_id]:
        song = bot.queue[guild_id].pop(0)
        await start_playing(guild, channel, user, song)
    elif bot.autoplay.get(guild_id, False):
        # AutoPlay สุ่มเพลงที่เกี่ยวข้องจากชื่อเพลงล่าสุด
        last = bot.last_track.get(guild_id)
        if last:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(f"ytsearch1:เพลงที่คล้ายกับ {last['title']}", download=False)['entries'][0]
                song_data = {'url': info['url'], 'title': info['title'], 'thumbnail': info.get('thumbnail'), 'duration': info.get('duration_string', '00:00')}
                await start_playing(guild, channel, user, song_data)

async def start_playing(guild, channel, user, song):
    vc = guild.voice_client
    if not vc: return
    
    bot.last_track[guild.id] = song
    source = discord.PCMVolumeTransformer(await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS))
    source.volume = 0.8 # ป้องกันเสียงแตก

    def after_func(e):
        asyncio.run_coroutine_threadsafe(play_next(guild, channel, user), bot.loop)

    vc.play(source, after=after_func)
    
    embed = discord.Embed(title="Kanopi Music System", color=0xff2d55)
    embed.add_field(name="Now playing:", value=f"```\n{song['title']}\n```", inline=False)
    embed.add_field(name="Duration:", value=f"└ {song['duration']}", inline=True)
    embed.add_field(name="Requester:", value=f"└ {user.mention}", inline=True)
    if song['thumbnail']: embed.set_image(url=song['thumbnail'])
    
    await channel.send(embed=embed, view=MusicView(bot, guild.id))

@bot.tree.command(name="play", description="สั่งเล่นเพลงจาก YouTube")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    if not interaction.user.voice: return await interaction.followup.send("❌ คุณต้องเข้าห้องเสียงก่อน!")
    
    vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect(self_deaf=True)
    
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(search, download=False)
            if 'entries' in info: info = info['entries'][0]
            song = {'url': info['url'], 'title': info['title'], 'thumbnail': info.get('thumbnail'), 'duration': info.get('duration_string', '00:00')}
        except: return await interaction.followup.send("❌ หาเพลงไม่เจอครับ")

    if vc.is_playing():
        bot.queue.setdefault(interaction.guild_id, []).append(song)
        await interaction.followup.send(f"➕ เพิ่มเข้าคิว: **{song['title']}**")
    else:
        await interaction.followup.send("🎶 เริ่มการเล่น...", ephemeral=True)
        await start_playing(interaction.guild, interaction.channel, interaction.user, song)

bot.run(TOKEN)
