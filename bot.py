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
MY_GUILD_ID = discord.Object(id=1470028388335882394)

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'extract_flat': True,
    'default_search': 'ytsearch',
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

    @discord.ui.button(emoji="🛑", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("⏹️ **หยุดเล่นและล้างคิวแล้ว**", ephemeral=True)

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

    @discord.ui.button(label="Donate", emoji="💰", style=discord.ButtonStyle.success)
    async def donate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🙏 ขอบคุณที่สนับสนุน Tete Shop ครับ! [ลิงก์โดเนท]", ephemeral=True)

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
        print(f"✅ Tete Music System Ready!")

bot = MusicBot()

def get_main_embed(song, user, guild):
    embed = discord.Embed(title="🎵 Tete Music System", color=0xff0055)
    embed.description = f"**Now playing:**\n```\n{song['title']}\n```"
    embed.add_field(name="Author:", value=f"╰─ **{song['uploader']}**", inline=True)
    embed.add_field(name="Duration:", value=f"╰─ `{song['duration']}`", inline=True)
    embed.add_field(name="Room:", value=f"╰─ <#{guild.voice_client.channel.id if guild.voice_client else 'undefined'}>", inline=True)
    embed.add_field(name="Requester:", value=f"╰─ {user.mention}", inline=True)
    embed.add_field(name="Web:", value="╰─ [รายละเอียด](https://tetewebshop.com)", inline=True)
    
    if song.get('thumbnail'):
        embed.set_image(url=song['thumbnail'])
    return embed

async def play_music(guild, channel, user, song):
    vc = guild.voice_client
    if not vc: return
    
    bot.last_track[guild.id] = song
    try:
        source = discord.PCMVolumeTransformer(await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS))
        source.volume = 0.8
        
        def after_func(e):
            asyncio.run_coroutine_threadsafe(check_queue(guild, channel, user), bot.loop)
            
        vc.play(source, after=after_func)
        await channel.send(embed=get_main_embed(song, user, guild), view=TeteMusicView(bot, guild.id))
    except Exception as e:
        print(f"Error: {e}")

async def check_queue(guild, channel, user):
    if guild.id in bot.queue and bot.queue[guild.id]:
        song = bot.queue[guild.id].pop(0)
        await play_music(guild, channel, user, song)
    elif bot.autoplay.get(guild.id, False):
        # ระบบ AutoPlay ดึงเพลงแนะนำจริงจาก YouTube
        last = bot.last_track.get(guild.id)
        search_query = f"เพลงแนะนำจาก {last['title']}" if last else "เพลงฮิต"
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(f"ytsearch1:{search_query}", download=False)['entries'][0]
            song_data = {'url': info['url'], 'title': info['title'], 'uploader': info.get('uploader', 'Unknown'), 'thumbnail': info.get('thumbnail'), 'duration': info.get('duration_string', '00:00')}
            await play_music(guild, channel, user, song_data)

@bot.tree.command(name="setup", description="สร้างห้องสำหรับเล่นเพลงโดยเฉพาะ")
async def setup(interaction: discord.Interaction):
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(send_messages=False),
        interaction.guild.me: discord.PermissionOverwrite(send_messages=True)
    }
    channel = await interaction.guild.create_text_channel('🎵-tete-music', overwrites=overwrites)
    
    embed = discord.Embed(title="Tete Music Setup", description="ส่งลิงก์เพลงในห้องนี้เพื่อเริ่มฟังเพลงได้เลย!", color=0x00ff00)
    await channel.send(embed=embed)
    await interaction.response.send_message(f"สร้างห้อง <#{channel.id}> เรียบร้อยแล้ว!", ephemeral=True)

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
        except: return await interaction.followup.send("❌ หาเพลงไม่เจอ")

    if vc.is_playing():
        bot.queue.setdefault(interaction.guild_id, []).append(song)
        await interaction.followup.send(f"➕ เพิ่มเข้าคิว: **{song['title']}**")
    else:
        await interaction.followup.send("🎶 เริ่มการเล่น...", ephemeral=True)
        await play_music(interaction.guild, interaction.channel, interaction.user, song)

bot.run(TOKEN)
