import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import static_ffmpeg
import os

# --- [Setup FFmpeg & Token] ---
static_ffmpeg.add_paths()
TOKEN = os.getenv('TOKEN')
# ไอดีกิลด์ของพี่ (ยึดตามที่ส่งมา)
MY_GUILD_ID = discord.Object(id=1470028388335882394)

# --- [YTDL Config - ดึงเพลงไวที่สุด] ---
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'extract_flat': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

class TeteMusicView(discord.ui.View):
    """ระบบปุ่มกดควบคุมเพลงแบบครบวงจร"""
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(emoji="🛑", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("⏹️ **ปิดระบบเพลงและล้างคิวแล้ว**", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ **ข้ามเพลง**", ephemeral=True)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸️ **พักเพลง**", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                await interaction.response.send_message("▶️ **เล่นต่อ**", ephemeral=True)

    @discord.ui.button(label="AutoPlay", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def autoplay(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.bot.autoplay.get(self.guild_id, False)
        self.bot.autoplay[self.guild_id] = not current
        button.style = discord.ButtonStyle.success if not current else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🔄 **AutoPlay: {'เปิด' if not current else 'ปิด'}**", ephemeral=True)

    @discord.ui.button(label="80%", emoji="🔊", style=discord.ButtonStyle.secondary)
    async def volume_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔊 ใช้คำสั่ง `/volume` เพื่อปรับเสียง", ephemeral=True)

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
        print(f"✅ Tete Music System Online!")

bot = MusicBot()

def get_tete_embed(song, user, guild):
    """สร้าง Embed ให้เหมือนในรูปที่ขอมา"""
    embed = discord.Embed(title="🎵 Tete Music System", color=0xff0055)
    embed.description = f"**Now playing:**\n```\n{song['title']}\n```"
    embed.add_field(name="Author:", value=f"╰─ **{song['uploader']}**", inline=True)
    embed.add_field(name="Duration:", value=f"╰─ `{song['duration']}`", inline=True)
    embed.add_field(name="Room:", value=f"╰─ <#{guild.voice_client.channel.id if guild.voice_client else 'undefined'}>", inline=True)
    embed.add_field(name="Requester:", value=f"╰─ {user.mention}", inline=True)
    embed.add_field(name="Web:", value="╰─ [TeteShop](https://tetewebshop.com)", inline=True)
    
    if song.get('thumbnail'):
        embed.set_image(url=song['thumbnail'])
    return embed

async def play_engine(guild, channel, user, song):
    vc = guild.voice_client
    if not vc: return
    
    bot.last_track[guild.id] = song
    try:
        source = discord.PCMVolumeTransformer(await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS))
        source.volume = 0.8
        
        def after_func(e):
            asyncio.run_coroutine_threadsafe(next_logic(guild, channel, user), bot.loop)
            
        vc.play(source, after=after_func)
        await channel.send(embed=get_tete_embed(song, user, guild), view=TeteMusicView(bot, guild.id))
    except Exception as e:
        print(f"Error: {e}")

async def next_logic(guild, channel, user):
    """ระบบคิวเพลงและ AutoPlay"""
    if guild.id in bot.queue and bot.queue[guild.id]:
        song = bot.queue[guild.id].pop(0)
        await play_engine(guild, channel, user, song)
    elif bot.autoplay.get(guild.id, False):
        # ระบบ AutoPlay: สุ่มเพลงที่เกี่ยวข้องจาก YouTube
        last = bot.last_track.get(guild.id)
        search = f"เพลงคล้าย {last['title']}" if last else "เพลงฮิต"
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(f"ytsearch1:{search}", download=False)['entries'][0]
            song_data = {'url': info['url'], 'title': info['title'], 'uploader': info.get('uploader', 'Unknown'), 'thumbnail': info.get('thumbnail'), 'duration': info.get('duration_string', '00:00')}
            await play_engine(guild, channel, user, song_data)

@bot.tree.command(name="setup", description="สร้างห้องเพลงถาวรแบบในรูป")
async def setup(interaction: discord.Interaction):
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(send_messages=False),
        interaction.guild.me: discord.PermissionOverwrite(send_messages=True)
    }
    channel = await interaction.guild.create_text_channel('🎵-tete-music', overwrites=overwrites)
    embed = discord.Embed(title="Tete Music System Setup", description="ส่งชื่อเพลงหรือลิงก์ในห้องนี้เพื่อเริ่มฟังเพลง!", color=0xff0055)
    await channel.send(embed=embed)
    await interaction.response.send_message(f"สร้างห้อง <#{channel.id}> แล้ว!", ephemeral=True)

@bot.tree.command(name="play", description="เล่นเพลง (ใส่ชื่อหรือลิงก์)")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    if not interaction.user.voice: return await interaction.followup.send("❌ เข้าห้องเสียงก่อน!")
    
    vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect(self_deaf=True)
    
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(search, download=False)
            if 'entries' in info: info = info['entries'][0]
            song = {'url': info['url'], 'title': info['title'], 'uploader': info.get('uploader'), 'thumbnail': info.get('thumbnail'), 'duration': info.get('duration_string')}
        except: return await interaction.followup.send("❌ หาเพลงไม่เจอ")

    if vc.is_playing():
        bot.queue.setdefault(interaction.guild_id, []).append(song)
        await interaction.followup.send(f"➕ เพิ่มเข้าคิว: **{song['title']}**")
    else:
        await interaction.followup.send("🎶 กำลังเริ่มเล่น...", ephemeral=True)
        await play_engine(interaction.guild, interaction.channel, interaction.user, song)

@bot.tree.command(name="volume", description="ปรับเสียง 0-100")
async def volume(interaction: discord.Interaction, level: int):
    vc = interaction.guild.voice_client
    if vc and vc.source:
        if 0 <= level <= 100:
            vc.source.volume = level / 100
            await interaction.response.send_message(f"🔊 ปรับเสียงเป็น {level}%")
        else: await interaction.response.send_message("ใส่เลข 0-100 ดิพี่")
    else: await interaction.response.send_message("บอทไม่ได้เล่นเพลงอยู่!")

bot.run(TOKEN)
