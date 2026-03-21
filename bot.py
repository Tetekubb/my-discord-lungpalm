import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import static_ffmpeg
import os

# --- [1. Core Setup & Options] ---
static_ffmpeg.add_paths()
TOKEN = os.getenv('TOKEN')
MY_GUILD_ID = discord.Object(id=1467879682019033088) # ID เซิร์ฟเวอร์ของพี่

# ปรับแก้ให้หาเพลงเจอแน่นอน 100% และไม่โดน YouTube บล็อก
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.6"'
}

# --- [2. UI & Control View] ---
class TeteControlView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        # ปุ่ม Add Friend: beareiei_ (พาไปหน้าโปรไฟล์พี่)
        self.add_item(discord.ui.Button(
            label="Add Friend: beareiei_", 
            emoji="👤", 
            url="https://discord.com/users/778604394982637568",
            row=1
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        return True

    @discord.ui.button(label="หยุด", emoji="🛑", style=discord.ButtonStyle.danger, row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.followup.send("🛑 **หยุดเล่นและล้างคิวเรียบร้อยครับพี่**", ephemeral=True)

    @discord.ui.button(label="ข้าม", emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.followup.send("⏭️ **ข้ามเพลงให้แล้วครับ!**", ephemeral=True)

    @discord.ui.button(label="พัก/เล่นต่อ", emoji="⏯️", style=discord.ButtonStyle.success, row=0)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
                await interaction.followup.send("⏸️ **พักเพลงชั่วคราว**", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                await interaction.followup.send("▶️ **กลับมาเล่นเพลงต่อแล้วครับ**", ephemeral=True)

# --- [3. Bot Engine & Logic] ---
class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)
        self.queue = {}

    async def setup_hook(self):
        # บังคับ Sync คำสั่งให้เข้าเซิร์ฟเวอร์พี่ทันที
        self.tree.copy_global_to(guild=MY_GUILD_ID)
        synced = await self.tree.sync(guild=MY_GUILD_ID)
        print(f"✅ Sync สำเร็จ! พบคำสั่ง: {[cmd.name for cmd in synced]}")
        print(f"✅ Tete Music Online! พร้อมใช้งานแล้วพี่")

bot = MusicBot()

def get_full_embed(song, user, status="Now Playing:"):
    # Embed ตัวเต็มสวยๆ ตามรูป (ไม่ย่อ!)
    embed = discord.Embed(title="🎵 Tete Music System", color=0xff0055)
    # Banner หลัก
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif")
    embed.description = f"**{status}**\n```\n{song['title']}\n```"
    
    # ข้อมูล Field ครบถ้วน (ศิลปิน, ความยาว, คนขอ)
    embed.add_field(name="ศิลปิน:", value=f"╰─ **{song['uploader']}**", inline=True)
    embed.add_field(name="ความยาว:", value=f"╰─ `{song['duration']}`", inline=True)
    embed.add_field(name="คนขอ:", value=f"╰─ {user.mention}", inline=True)
    
    if song.get('thumbnail'):
        embed.set_thumbnail(url=song['thumbnail'])
    return embed

async def play_engine(guild, channel, user, song):
    vc = guild.voice_client
    if not vc: return
    try:
        source = await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS)
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(next_song(guild, channel, user), bot.loop))
        await channel.send(embed=get_full_embed(song, user), view=TeteControlView(bot, guild.id))
    except Exception as e:
        print(f"Play Error: {e}")

async def next_song(guild, channel, user):
    if guild.id in bot.queue and bot.queue[guild.id]:
        song = bot.queue[guild.id].pop(0)
        await play_engine(guild, channel, user, song)

# --- [4. Slash Commands] ---

@bot.tree.command(name="setup", description="สร้างห้องควบคุมเพลงอัตโนมัติ")
async def setup(interaction: discord.Interaction):
    # สร้างห้องแชทใหม่สำหรับควบคุมเพลงโดยเฉพาะ
    channel = await interaction.guild.create_text_channel('🎵-tete-music')
    
    embed = discord.Embed(title="🎵 Tete Music System", color=0x2f3136)
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif")
    embed.description = "```\nพิมพ์ชื่อเพลงที่นี่ได้เลย ไม่ต้องใช้คำสั่ง!\n```"
    
    await channel.send(embed=embed, view=TeteControlView(bot, interaction.guild.id))
    await interaction.response.send_message(f"✅ สร้างห้อง <#{channel.id}> เรียบร้อยครับพี่!", ephemeral=True)

@bot.tree.command(name="play", description="เล่นเพลงจาก YouTube")
async def play(interaction: discord.Interaction, search: str):
    if not interaction.response.is_done():
        await interaction.response.defer()
        
    if not interaction.user.voice:
        return await interaction.followup.send("❌ พี่เข้าห้องเสียงก่อนนะ!")

    vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect(self_deaf=True)

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            # ดึงข้อมูลเพลง (แก้ปัญหาหาไม่เจอ)
            info = ydl.extract_info(f"ytsearch1:{search}", download=False)
            if not info['entries']:
                return await interaction.followup.send("❌ หาเพลงนี้ไม่เจอจริงๆ ครับพี่ ลองชื่ออื่นดู")
                
            data = info['entries'][0]
            song = {
                'url': data['url'], 
                'title': data['title'], 
                'uploader': data.get('uploader', 'Unknown'), 
                'duration': data.get('duration_string', '0:00'), 
                'thumbnail': data.get('thumbnail')
            }

            if vc.is_playing() or vc.is_paused():
                bot.queue.setdefault(interaction.guild_id, []).append(song)
                await interaction.followup.send(f"➕ เพิ่มเข้าคิว: **{song['title']}**")
            else:
                await interaction.followup.send("🎶 กำลังเริ่มโหลดเพลง...", ephemeral=True)
                await play_engine(interaction.guild, interaction.channel, interaction.user, song)
        except Exception as e:
            print(f"Search Error: {e}")
            await interaction.followup.send("❌ เกิดข้อผิดพลาดในการหาเพลง")

# --- [5. Chat Listener] ---
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    # ระบบพิมพ์แล้วเล่นทันทีในห้องเพลง
    if message.channel.name == '🎵-tete-music':
        member = message.guild.get_member(message.author.id)
        if member:
            await bot.tree.get_command('play').callback(member, message.content)
            await message.delete()

bot.run(TOKEN)
