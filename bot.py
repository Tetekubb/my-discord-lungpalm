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
MY_GUILD_ID = discord.Object(id=1467879682019033088)

# ปรับ Option ของ yt-dlp ให้ดึงข้อมูลดิบที่สุด ลดโอกาสโดนบล็อก
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'nocheckcertificate': True,
    'ignoreerrors': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

class TeteMusicView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.add_item(discord.ui.Button(label="Tete WebShop", emoji="🛒", url="https://tetewebshop.com", row=1))

    @discord.ui.button(label="หยุด", emoji="⏹️", style=discord.ButtonStyle.danger, row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("⏹️ **หยุดและล้างคิวแล้ว**", ephemeral=True)

    @discord.ui.button(label="ข้าม", emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ **ข้ามเพลง**", ephemeral=True)

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
            print("✅ Tete Music Online: พร้อมลุยแล้วพี่!")
        except Exception as e:
            print(f"⚠️ Sync Error: {e}")

bot = MusicBot()

async def play_engine(guild, channel, user, song):
    vc = guild.voice_client
    if not vc: return
    try:
        # ใช้ FFmpeg แบบเจาะจงเพื่อเลี่ยงบั๊ก Library เสียง
        source = await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS)
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(next_logic(guild, channel, user), bot.loop))
        
        embed = discord.Embed(title="🎵 Tete Music System", color=0xff0055)
        embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif")
        embed.description = f"**กำลังเล่น:**\n```\n{song['title']}\n```"
        await channel.send(embed=embed, view=TeteMusicView(bot, guild.id))
    except Exception as e:
        print(f"Play Error: {e}")

async def next_logic(guild, channel, user):
    if guild.id in bot.queue and bot.queue[guild.id]:
        song = bot.queue[guild.id].pop(0)
        await play_engine(guild, channel, user, song)

@bot.tree.command(name="play", description="เล่นเพลง")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    if not interaction.user.voice: return await interaction.followup.send("❌ เข้าห้องเสียงก่อนพี่!")
    
    # เพิ่มความหน่วงเวลาตอนต่อเข้าห้องเพื่อกันบั๊ก Gateway
    try:
        vc = interaction.guild.voice_client
        if not vc:
            vc = await interaction.user.voice.channel.connect(self_deaf=True)
            await asyncio.sleep(1) 
    except Exception as e:
        return await interaction.followup.send(f"❌ บอทเอ๋อ เข้าห้องไม่ได้: {e}")

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(f"ytsearch1:{search}", download=False)
        if not info or 'entries' not in info:
            return await interaction.followup.send("❌ หาเพลงไม่เจอ")
        
        entry = info['entries'][0]
        song = {'url': entry['url'], 'title': entry['title']}
        
        if vc.is_playing():
            bot.queue.setdefault(interaction.guild_id, []).append(song)
            await interaction.followup.send(f"➕ คิว: **{song['title']}**")
        else:
            await interaction.followup.send("🎶 กำลังโหลด...", ephemeral=True)
            await play_engine(interaction.guild, interaction.channel, interaction.user, song)

@bot.tree.command(name="setup", description="สร้างห้องเพลง")
async def setup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    channel = await interaction.guild.create_text_channel('🎵-tete-music')
    embed = discord.Embed(title="🎵 Tete Music System", color=0x2f3136)
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif")
    embed.description = "```\nรอรับคำสั่งจากพี่อยู่นะครับ...\n```"
    await channel.send(embed=embed, view=TeteMusicView(bot, interaction.guild.id))
    await interaction.followup.send(f"✅ สร้างห้อง <#{channel.id}> แล้ว!", ephemeral=True)

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if message.channel.name == '🎵-tete-music':
        await bot.tree.get_command('play').callback(message.guild.get_member(message.author.id), message.content)
        await message.delete()

bot.run(TOKEN)
