import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import static_ffmpeg
import os

# --- [Setup ระบบเสียงและ Token] ---
static_ffmpeg.add_paths()
TOKEN = os.getenv('TOKEN')
MY_GUILD_ID = discord.Object(id=1467879682019033088) # ID เซิร์ฟเวอร์ของพี่

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

# --- [UI: ปุ่มควบคุมแบบ Full Option] ---
class TeteControlView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        # ปุ่มลิงก์ร้านค้า Tete WebShop
        self.add_item(discord.ui.Button(label="Tete WebShop", emoji="🛒", url="https://tetewebshop.com", row=1))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # แก้บั๊ก "การโต้ตอบล้มเหลว" โดยการตอบรับล่วงหน้า
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
                await interaction.followup.send("▶️ **กลับมาเล่นเพลงต่อแล้วครับพี่**", ephemeral=True)

# --- [Bot Class & Embed Logic] ---
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
            print(f"✅ Tete Music Online!")
        except Exception as e:
            print(f"⚠️ Sync Error: {e}")

bot = MusicBot()

def get_full_embed(song, user, status="Now Playing:"):
    # คืนค่า Embed แบบจัดเต็มตามรูปอันบน
    embed = discord.Embed(title="🎵 Tete Music System", color=0xff0055)
    # Banner หลัก
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif")
    embed.description = f"**{status}**\n```\n{song['title']}\n```"
    
    # ใส่ Field กลับมาให้ครบ (ศิลปิน, ความยาว, คนขอ)
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

# --- [Commands] ---
@bot.tree.command(name="play", description="เล่นเพลงจาก YouTube")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    if not interaction.user.voice:
        return await interaction.followup.send("❌ พี่เข้าห้องเสียงก่อนนะ!")

    vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect(self_deaf=True)

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch1:{search}", download=False)['entries'][0]
            song = {
                'url': info['url'], 
                'title': info['title'],
                'uploader': info.get('uploader', 'Unknown'),
                'duration': info.get('duration_string', '0:00'),
                'thumbnail': info.get('thumbnail')
            }

            if vc.is_playing() or vc.is_paused():
                bot.queue.setdefault(interaction.guild_id, []).append(song)
                await interaction.followup.send(f"➕ เพิ่มเข้าคิว: **{song['title']}**")
            else:
                await interaction.followup.send("🎶 กำลังโหลดเพลง...")
                await play_engine(interaction.guild, interaction.channel, interaction.user, song)
        except:
            await interaction.followup.send("❌ หาเพลงไม่เจอครับ")

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if message.channel.name == '🎵-tete-music':
        # ดึงคำสั่งมาใช้งานโดยตรงเมื่อพิมพ์ในช่องแชท
        await bot.tree.get_command('play').callback(message.guild.get_member(message.author.id), message.content)
        await message.delete()

bot.run(TOKEN)
