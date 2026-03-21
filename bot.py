import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import static_ffmpeg
import os
from datetime import datetime

# --- [Settings] ---
TOKEN = os.getenv('TOKEN') or 'YOUR_TOKEN_HERE'
MY_GUILD_ID = discord.Object(id=1470028388335882394)

# --- [YTDL & FFMPEG Optimized] ---
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': 'in_playlist', # ดึงข้อมูลไวขึ้น
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

class MusicView(discord.ui.View):
    """คลาสสำหรับปุ่มควบคุมใต้ Embed เพลง"""
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ ข้ามเพลงแล้ว", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ไม่มีเพลงเล่นอยู่", ephemeral=True)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸️ พักเพลง", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                await interaction.response.send_message("▶️ เล่นต่อ", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("⏹️ ปิดเพลงและออกจากห้อง", ephemeral=True)

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.queue = {}
        self.autoplay = {} # เก็บสถานะ AutoPlay แยกเซิร์ฟเวอร์

    async def setup_hook(self):
        static_ffmpeg.add_paths()
        self.tree.copy_global_to(guild=MY_GUILD_ID)
        await self.tree.sync(guild=MY_GUILD_ID)
        print(f"✅ Kanopi Music System พร้อมทำงาน!")

bot = MusicBot()

def get_embed(info, interaction, status="กำลังเล่น"):
    embed = discord.Embed(title="Kanopi Music System", color=0xff2d55)
    embed.add_field(name="Now playing:", value=f"```\n{info['title']}\n```", inline=False)
    embed.add_field(name="Author:", value=f"└ {info.get('uploader', 'Unknown')}", inline=True)
    embed.add_field(name="Duration:", value=f"└ {info.get('duration_string', '00:00')}", inline=True)
    embed.add_field(name="Requester:", value=f"└ {interaction.user.mention}", inline=True)
    if 'thumbnail' in info:
        embed.set_image(url=info['thumbnail'])
    return embed

async def play_music(interaction, song):
    vc = interaction.guild.voice_client
    if not vc: return

    # ปรับปรุงระบบ Volume เพื่อแก้บัคเสียงเบา/แตก
    source = discord.PCMVolumeTransformer(await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS))
    source.volume = 0.8 # ตั้งค่าเริ่มต้น 80%

    def after_playing(error):
        asyncio.run_coroutine_threadsafe(next_song(interaction), bot.loop)

    vc.play(source, after=after_playing)
    view = MusicView(bot, interaction.guild_id)
    await interaction.channel.send(embed=get_embed(song, interaction), view=view)

async def next_song(interaction):
    guild_id = interaction.guild_id
    vc = interaction.guild.voice_client
    if not vc: return

    if guild_id in bot.queue and bot.queue[guild_id]:
        song = bot.queue[guild_id].pop(0)
        await play_music(interaction, song)
    elif bot.autoplay.get(guild_id, False):
        # ระบบ AutoPlay: ค้นหาเพลงที่คล้ายกัน (ในตัวอย่างนี้คือการสุ่มเพลงแนะนำ)
        await interaction.channel.send("🔄 คิวว่าง.. กำลังเลือกเพลงถัดไปให้อัตโนมัติ", delete_after=5)
        # จำลองการหาเพลงใหม่ (สามารถปรับแต่งให้ดึงจาก Related videos ได้)
        search = "เพลงไทยยอดฮิต" 
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(f"ytsearch1:{search}", download=False)['entries'][0]
            await play_music(interaction, info)

@bot.tree.command(name="play", description="เล่นเพลง (ใส่ชื่อหรือลิงก์)")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    
    if not interaction.user.voice:
        return await interaction.followup.send("❌ เข้าห้องเสียงก่อน!")

    vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect(self_deaf=True)

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(search, download=False)
            if 'entries' in info: info = info['entries'][0]
            song_data = {
                'url': info['url'], 
                'title': info['title'], 
                'thumbnail': info.get('thumbnail'),
                'uploader': info.get('uploader'),
                'duration_string': info.get('duration_string')
            }
        except: return await interaction.followup.send("❌ หาเพลงไม่เจอ")

    if vc.is_playing():
        bot.queue.setdefault(interaction.guild_id, []).append(song_data)
        await interaction.followup.send(f"➕ เพิ่มเข้าคิว: {info['title']}")
    else:
        await interaction.followup.send("🎶 เริ่มการเล่นเพลง...", ephemeral=True)
        await play_music(interaction, song_data)

@bot.tree.command(name="queue", description="ดูรายการคิวเพลงปัจจุบัน")
async def queue(interaction: discord.Interaction):
    q = bot.queue.get(interaction.guild_id, [])
    if not q: return await interaction.response.send_message("ขณะนี้ไม่มีคิวเพลง")
    
    desc = ""
    for i, s in enumerate(q[:10], 1):
        desc += f"{i}. {s['title']}\n"
    
    embed = discord.Embed(title="รายการคิวเพลง", description=f"```\n{desc}\n```", color=0x3498db)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="autoplay", description="เปิด/ปิด การเล่นอัตโนมัติเมื่อคิวว่าง")
async def autoplay(interaction: discord.Interaction):
    current = bot.autoplay.get(interaction.guild_id, False)
    bot.autoplay[interaction.guild_id] = not current
    status = "เปิด ✅" if not current else "ปิด ❌"
    await interaction.response.send_message(f"ระบบ AutoPlay: {status}")

@bot.tree.command(name="volume", description="ปรับระดับเสียง (0-100)")
async def volume(interaction: discord.Interaction, percent: int):
    vc = interaction.guild.voice_client
    if not vc or not vc.source:
        return await interaction.response.send_message("❌ บอทไม่ได้เล่นเพลงอยู่")
    
    if 0 <= percent <= 100:
        vc.source.volume = percent / 100
        await interaction.response.send_message(f"🔊 ปรับเสียงเป็น {percent}%")
    else:
        await interaction.response.send_message("❌ กรุณาใส่ตัวเลข 0-100")

bot.run(TOKEN)
