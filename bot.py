import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import static_ffmpeg
import os

# --- [Core Setup] ---
static_ffmpeg.add_paths()
TOKEN = os.getenv('TOKEN') # ดึงจาก Variable ใน Railway
MY_GUILD_ID = discord.Object(id=1470028388335882394)

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
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        # แก้ไข: สร้างปุ่ม URL ที่นี่แทนการใช้ Decorator
        self.add_item(discord.ui.Button(label="เว็บของเรา", emoji="🌐", url="https://tetewebshop.com", row=1))

    @discord.ui.button(emoji="🛑", style=discord.ButtonStyle.danger, row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("⏹️ **หยุดเล่นแล้ว**", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ **ข้ามเพลง**", ephemeral=True)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary, row=0)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸️ **พักเพลง**", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                await interaction.response.send_message("▶️ **เล่นต่อ**", ephemeral=True)

    @discord.ui.button(label="AutoPlay", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def autoplay(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.bot.autoplay.get(self.guild_id, False)
        self.bot.autoplay[self.guild_id] = not current
        button.style = discord.ButtonStyle.success if not current else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🔄 **AutoPlay: {'เปิด ✅' if not current else 'ปิด ❌'}**", ephemeral=True)

    @discord.ui.button(label="Donate", emoji="💰", style=discord.ButtonStyle.success, row=1)
    async def donate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🙏 ขอบคุณที่สนับสนุน Tete Shop ครับ!", ephemeral=True)

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

def create_embed(song, user, guild):
    embed = discord.Embed(title="🎵 Tete Music System", color=0xff0055)
    embed.description = f"**Now playing:**\n```\n{song['title']}\n```"
    embed.add_field(name="Author:", value=f"╰─ **{song['uploader']}**", inline=True)
    embed.add_field(name="Duration:", value=f"╰─ `{song['duration']}`", inline=True)
    embed.add_field(name="Room:", value=f"╰─ <#{guild.voice_client.channel.id if guild.voice_client else 'undefined'}>", inline=True)
    embed.add_field(name="Requester:", value=f"╰─ {user.mention}", inline=True)
    embed.add_field(name="Web:", value="╰─ [ดูรายละเอียด](https://tetewebshop.com)", inline=True)
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
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(next_logic(guild, channel, user), bot.loop))
        await channel.send(embed=create_embed(song, user, guild), view=TeteMusicView(bot, guild.id))
    except Exception as e: print(f"Error: {e}")

async def next_logic(guild, channel, user):
    if guild.id in bot.queue and bot.queue[guild.id]:
        song = bot.queue[guild.id].pop(0)
        await play_engine(guild, channel, user, song)
    elif bot.autoplay.get(guild.id, False):
        last = bot.last_track.get(guild.id)
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                info = ydl.extract_info(f"ytsearch1:เพลงคล้าย {last['title'] if last else 'เพลงไทย'}", download=False)['entries'][0]
                song_data = {'url': info['url'], 'title': info['title'], 'uploader': info.get('uploader', 'Unknown'), 'thumbnail': info.get('thumbnail'), 'duration': info.get('duration_string', '0:00')}
                await play_engine(guild, channel, user, song_data)
            except: pass

@bot.tree.command(name="play", description="เล่นเพลง")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    if not interaction.user.voice: return await interaction.followup.send("❌ เข้าห้องเสียงก่อนนะ!")
    vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect(self_deaf=True)
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(search, download=False)
            if 'entries' in info: info = info['entries'][0]
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
    channel = await interaction.guild.create_text_channel('🎵-tete-music')
    await interaction.response.send_message(f"สร้างห้อง <#{channel.id}> แล้ว!", ephemeral=True)

bot.run(TOKEN)
