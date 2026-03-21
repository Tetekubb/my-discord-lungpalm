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
# 🚩 สำคัญ: เปลี่ยนเป็น ID เซิร์ฟเวอร์ของพี่เอง
MY_GUILD_ID = discord.Object(id=1467879682019033088) 

# ตั้งค่าการดึงข้อมูลเพลงให้แม่นยำที่สุด
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# --- [หน้าจอควบคุมและปุ่มกด] ---
class TeteControlView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(label="หยุด/ออก", emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("🛑 **หยุดเล่นและล้างคิวแล้ว**", ephemeral=True)
        else:
            await interaction.response.send_message("❌ บอทไม่ได้อยู่ในห้องเสียง", ephemeral=True)

    @discord.ui.button(label="ข้ามเพลง", emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ **ข้ามเพลงให้แล้วครับ**", ephemeral=True)

    @discord.ui.button(label="พัก/เล่นต่อ", emoji="⏯️", style=discord.ButtonStyle.success)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸️ **พักเพลงชั่วคราว**", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                await interaction.response.send_message("▶️ **เล่นเพลงต่อแล้ว**", ephemeral=True)

# --- [ตัวบอทหลัก] ---
class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)
        self.queue = {}

    async def setup_hook(self):
        try:
            self.tree.copy_global_to(guild=MY_GUILD_ID)
            await self.tree.sync(guild=MY_GUILD_ID)
            print("✅ Tete Music System: ออนไลน์และซิงค์คำสั่งเรียบร้อย!")
        except Exception as e:
            print(f"⚠️ การซิงค์มีปัญหา: {e}")

bot = MusicBot()

# --- [ฟังก์ชันช่วยเล่นเพลง] ---
def get_music_embed(song, user, status="กำลังเล่นเพลง"):
    embed = discord.Embed(title="🎵 Tete Music System", color=0xff0055)
    # Banner ตามรูปที่พี่ส่งมา
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif")
    embed.description = f"**{status}:**\n```\n{song['title']}\n```"
    embed.add_field(name="ศิลปิน", value=f"╰─ {song['uploader']}", inline=True)
    embed.add_field(name="ความยาว", value=f"╰─ {song['duration']}", inline=True)
    embed.add_field(name="ผู้ขอเพลง", value=f"╰─ {user.mention}", inline=True)
    if song.get('thumbnail'):
        embed.set_thumbnail(url=song['thumbnail'])
    return embed

async def play_next(guild, channel, user):
    if guild.id in bot.queue and bot.queue[guild.id]:
        song = bot.queue[guild.id].pop(0)
        await start_playing(guild, channel, user, song)

async def start_playing(guild, channel, user, song):
    vc = guild.voice_client
    if not vc: return

    try:
        source = await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS)
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild, channel, user), bot.loop))
        await channel.send(embed=get_music_embed(song, user), view=TeteControlView(bot, guild.id))
    except Exception as e:
        print(f"Play Error: {e}")
        await channel.send(f"❌ เล่นเพลงไม่ได้: {song['title']}")

# --- [คำสั่งบอท] ---
@bot.tree.command(name="play", description="ค้นหาเพลงจาก YouTube")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    
    if not interaction.user.voice:
        return await interaction.followup.send("❌ พี่ต้องเข้าห้องเสียงก่อนนะครับ")

    vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect(self_deaf=True)

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            # ค้นหาเพลง
            info = ydl.extract_info(f"ytsearch1:{search}", download=False)
            if not info['entries']:
                return await interaction.followup.send("❌ หาเพลงนี้ไม่เจอจริงๆ ครับพี่")
            
            entry = info['entries'][0]
            song = {
                'url': entry['url'], 
                'title': entry['title'], 
                'uploader': entry.get('uploader', 'Unknown'),
                'thumbnail': entry.get('thumbnail'),
                'duration': entry.get('duration_string', '0:00')
            }

            if vc.is_playing() or vc.is_paused():
                bot.queue.setdefault(interaction.guild_id, []).append(song)
                await interaction.followup.send(f"➕ เพิ่มเข้าคิว: **{song['title']}**")
            else:
                await interaction.followup.send("🎶 กำลังเริ่มเล่น...")
                await start_playing(interaction.guild, interaction.channel, interaction.user, song)
        except Exception as e:
            print(f"Search Error: {e}")
            await interaction.followup.send("❌ ระบบ YouTube ขัดข้อง ลองใหม่อีกครั้งครับ")

@bot.tree.command(name="setup", description="สร้างห้องควบคุมเพลงพิเศษ")
async def setup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    channel = await interaction.guild.create_text_channel('🎵-tete-music')
    
    embed = discord.Embed(title="🎵 Tete Music System", color=0x2f3136)
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif")
    embed.description = "```\nขณะนี้ยังไม่มีเพลงที่กำลังเล่น\n```"
    embed.set_footer(text="พิมพ์ชื่อเพลงที่อยากฟังลงในแชทนี้ได้เลย!")
    
    await channel.send(embed=embed, view=TeteControlView(bot, interaction.guild.id))
    await interaction.followup.send(f"✅ สร้างห้อง <#{channel.id}> เรียบร้อยแล้วครับพี่!", ephemeral=True)

# --- [ระบบตรวจจับข้อความในห้องเพลง] ---
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if message.channel.name == '🎵-tete-music':
        # เรียกใช้ระบบค้นหาเพลงทันทีที่พิมพ์ชื่อเพลง
        await bot.tree.get_command('play').callback(message.guild.get_member(message.author.id), message.content)
        await message.delete()

bot.run(TOKEN)
