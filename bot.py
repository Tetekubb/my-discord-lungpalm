import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import static_ffmpeg
import os

# --- [ตั้งค่าพื้นฐาน] ---
static_ffmpeg.add_paths()
TOKEN = os.getenv('TOKEN')
# 🚩 สำคัญ: เปลี่ยนตัวเลขนี้เป็น ID เซิร์ฟเวอร์ของพี่ (คลิกขวาที่ชื่อเซิร์ฟ -> Copy Server ID)
MY_GUILD_ID = discord.Object(id=1467879682019033088) 

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'nocheckcertificate': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# --- [ระบบปุ่มกดและหน้าจอควบคุม] ---
class TeteMusicView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        # ปุ่มลิงก์เว็บ TeteWebShop ของพี่
        self.add_item(discord.ui.Button(label="Tete WebShop", emoji="🛒", url="https://tetewebshop.com", row=1))

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("⏹️ หยุดเล่นและออกจากห้องแล้ว", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ ข้ามเพลงให้แล้วครับ", ephemeral=True)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.secondary, row=0)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸️ พักเพลง", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                await interaction.response.send_message("▶️ เล่นต่อ", ephemeral=True)

    @discord.ui.button(label="AutoPlay", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def autoplay(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.bot.autoplay.get(self.guild_id, False)
        self.bot.autoplay[self.guild_id] = not current
        button.style = discord.ButtonStyle.success if not current else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🔄 AutoPlay: {'เปิด ✅' if not current else 'ปิด ❌'}", ephemeral=True)

# --- [ตัวบอทหลัก] ---
class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)
        self.queue = {}
        self.autoplay = {}
        self.last_track = {}

    async def setup_hook(self):
        # แก้ปัญหา Error 50001 โดยการตรวจสอบสิทธิ์ก่อน Sync
        try:
            self.tree.copy_global_to(guild=MY_GUILD_ID)
            await self.tree.sync(guild=MY_GUILD_ID)
            print(f"✅ Tete Music System Online! Sync ไปที่เซิร์ฟเวอร์เรียบร้อย")
        except Exception as e:
            print(f"⚠️ คำเตือน Sync: {e} (ถ้าบอทออนไลน์แล้วก็รันต่อได้เลย)")

bot = MusicBot()

# --- [ระบบแสดงผล Embed] ---
def create_embed(song, user, guild, status="Now Playing"):
    embed = discord.Embed(title="🎵 Tete Music System", color=0xff0055)
    # ใส่ Banner ตามที่พี่ต้องการ
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif") 
    
    embed.description = f"**{status}:**\n```\n{song['title']}\n```"
    embed.add_field(name="ช่อง:", value=f"╰─ **{song['uploader']}**", inline=True)
    embed.add_field(name="เวลา:", value=f"╰─ `{song['duration']}`", inline=True)
    embed.add_field(name="ผู้ขอเพลง:", value=f"╰─ {user.mention}", inline=True)
    
    if song.get('thumbnail'):
        embed.set_thumbnail(url=song['thumbnail'])
    return embed

async def play_engine(guild, channel, user, song):
    vc = guild.voice_client
    if not vc: return
    bot.last_track[guild.id] = song
    
    try:
        source = discord.PCMVolumeTransformer(await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS))
        source.volume = 0.8
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(next_logic(guild, channel, user), bot.loop))
        await channel.send(embed=create_embed(song, user, guild), view=TeteMusicView(bot, guild.id))
    except Exception as e:
        print(f"Play Error: {e}")

async def next_logic(guild, channel, user):
    if guild.id in bot.queue and bot.queue[guild.id]:
        song = bot.queue[guild.id].pop(0)
        await play_engine(guild, channel, user, song)
    elif bot.autoplay.get(guild.id, False):
        last = bot.last_track.get(guild.id)
        search_query = f"ytsearch1:เพลงคล้าย {last['title']}" if last else "ytsearch1:เพลงไทยใหม่ล่าสุด"
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                info = ydl.extract_info(search_query, download=False)['entries'][0]
                song_data = {'url': info['url'], 'title': info['title'], 'uploader': info.get('uploader', 'Unknown'), 'thumbnail': info.get('thumbnail'), 'duration': info.get('duration_string', '0:00')}
                await play_engine(guild, channel, user, song_data)
            except: pass

# --- [คำสั่ง Slash Commands] ---
@bot.tree.command(name="play", description="เล่นเพลงจากชื่อหรือลิงก์")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    
    if not interaction.user.voice:
        return await interaction.followup.send("❌ พี่ต้องเข้าห้องเสียงก่อน!")

    vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect(self_deaf=True)

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{search}", download=False)
            entry = info['entries'][0]
            song = {'url': entry['url'], 'title': entry['title'], 'uploader': entry.get('uploader'), 'thumbnail': entry.get('thumbnail'), 'duration': entry.get('duration_string')}

            if vc.is_playing():
                bot.queue.setdefault(interaction.guild_id, []).append(song)
                await interaction.followup.send(f"➕ เพิ่มเข้าคิว: **{song['title']}**")
            else:
                await interaction.followup.send("🎶 เริ่มเล่นเพลง...", ephemeral=True)
                await play_engine(interaction.guild, interaction.channel, interaction.user, song)
        except:
            await interaction.followup.send("❌ หาเพลงไม่เจอครับ")

@bot.tree.command(name="setup", description="สร้างห้องเพลงพิเศษ")
async def setup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    channel = await interaction.guild.create_text_channel('🎵-tete-music')
    
    embed = discord.Embed(title="🎵 Tete Music System", color=0x2f3136)
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif")
    embed.description = "```\nไม่มีเพลงที่เล่นอยู่ในขณะนี้\n```"
    embed.set_footer(text="พิมพ์ชื่อเพลงที่อยากฟังในช่องแชทนี้ได้เลย!")
    
    await channel.send(embed=embed, view=TeteMusicView(bot, interaction.guild.id))
    await interaction.followup.send(f"✅ สร้างห้อง <#{channel.id}> แล้วครับ!", ephemeral=True)

# --- [ระบบสั่งเพลงผ่านช่องแชทโดยตรง] ---
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if message.channel.name == '🎵-tete-music':
        # ถ้าพิมพ์ในห้องเพลง ให้ถือว่าเป็นการสั่งเพลงทันที
        ctx = await bot.get_context(message)
        search = message.content
        await bot.tree.get_command('play').callback(message.guild.get_member(message.author.id), search)
        await message.delete() # ลบข้อความที่พิมพ์เพื่อความสะอาด

bot.run(TOKEN)
