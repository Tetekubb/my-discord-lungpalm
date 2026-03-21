import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import static_ffmpeg
import os

# --- [Core Setup] ---
static_ffmpeg.add_paths()
TOKEN = os.getenv('TOKEN')
MY_GUILD_ID = discord.Object(id=1467879682019033088) # ID เซิร์ฟเวอร์ของพี่

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',
    'nocheckcertificate': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# --- [UI & Buttons] ---
class TeteMusicView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        # ปุ่มลิงก์เว็บ TeteWebShop
        self.add_item(discord.ui.Button(label="Tete WebShop", emoji="🛒", url="https://tetewebshop.com", row=1))

    @discord.ui.button(label="หยุด", emoji="⏹️", style=discord.ButtonStyle.danger, row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("⏹️ **หยุดเล่นแล้วครับ**", ephemeral=True)

    @discord.ui.button(label="ข้าม", emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ **ข้ามเพลงแล้ว**", ephemeral=True)

    @discord.ui.button(label="พัก/เล่นต่อ", emoji="⏯️", style=discord.ButtonStyle.secondary, row=0)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸️ **พักเพลง**", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                await interaction.response.send_message("▶️ **เล่นต่อ**", ephemeral=True)

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)
        self.queue = {}
        self.last_track = {}

    async def setup_hook(self):
        try:
            self.tree.copy_global_to(guild=MY_GUILD_ID)
            await self.tree.sync(guild=MY_GUILD_ID)
            print(f"✅ Tete Music Online & Synced!")
        except Exception as e:
            print(f"⚠️ Sync Error: {e}")

bot = MusicBot()

# --- [Music Engine] ---
def create_embed(song, user, status="Now Playing"):
    embed = discord.Embed(title="🎵 Tete Music System", color=0xff0055)
    # แบนเนอร์ตามรูปที่พี่ส่งมา
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif") 
    embed.description = f"**{status}:**\n```\n{song['title']}\n```"
    embed.add_field(name="ศิลปิน:", value=f"╰─ **{song['uploader']}**", inline=True)
    embed.add_field(name="ความยาว:", value=f"╰─ `{song['duration']}`", inline=True)
    embed.add_field(name="ขอโดย:", value=f"╰─ {user.mention}", inline=True)
    if song.get('thumbnail'): embed.set_thumbnail(url=song['thumbnail'])
    return embed

async def play_engine(guild, channel, user, song):
    vc = guild.voice_client
    if not vc: return
    try:
        source = discord.PCMVolumeTransformer(await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS))
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(next_logic(guild, channel, user), bot.loop))
        await channel.send(embed=create_embed(song, user), view=TeteMusicView(bot, guild.id))
    except Exception as e: print(f"Play Error: {e}")

async def next_logic(guild, channel, user):
    if guild.id in bot.queue and bot.queue[guild.id]:
        song = bot.queue[guild.id].pop(0)
        await play_engine(guild, channel, user, song)

# --- [Commands] ---
@bot.tree.command(name="play", description="เล่นเพลง")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    if not interaction.user.voice: return await interaction.followup.send("❌ เข้าห้องเสียงก่อนนะพี่!")
    
    vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect(self_deaf=True)
    
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{search}", download=False)['entries'][0]
            song = {'url': info['url'], 'title': info['title'], 'uploader': info.get('uploader'), 'thumbnail': info.get('thumbnail'), 'duration': info.get('duration_string')}
            
            if vc.is_playing():
                bot.queue.setdefault(interaction.guild_id, []).append(song)
                await interaction.followup.send(f"➕ เพิ่มเข้าคิว: **{song['title']}**")
            else:
                await interaction.followup.send("🎶 กำลังโหลด...", ephemeral=True)
                await play_engine(interaction.guild, interaction.channel, interaction.user, song)
        except: await interaction.followup.send("❌ หาเพลงไม่เจอ")

@bot.tree.command(name="setup", description="สร้างห้องเพลง")
async def setup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    channel = await interaction.guild.create_text_channel('🎵-tete-music')
    
    embed = discord.Embed(title="🎵 Tete Music System", color=0x2f3136)
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif")
    embed.description = "```\nไม่มีเพลงที่เล่นอยู่ในขณะนี้\n```"
    embed.set_footer(text="พิมพ์ชื่อเพลงที่อยากฟังในช่องแชทนี้ได้เลย!")
    
    await channel.send(embed=embed, view=TeteMusicView(bot, interaction.guild.id))
    await interaction.followup.send(f"✅ สร้างห้อง <#{channel.id}> แล้ว!", ephemeral=True)

# --- [Chat Trigger] ---
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    # ถ้าพิมพ์ในห้องเพลง ให้สั่งเพลงทันที
    if message.channel.name == '🎵-tete-music':
        search_text = message.content
        # จำลองการเรียกใช้คำสั่ง play
        await message.channel.send(f"🔍 กำลังค้นหา: **{search_text}**", delete_after=5)
        # เรียก function play โดยตรง (ลัดขั้นตอน)
        await bot.tree.get_command('play').callback(message.guild.get_member(message.author.id), search_text)
        await message.delete()

bot.run(TOKEN)
