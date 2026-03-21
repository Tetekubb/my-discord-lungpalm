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
MY_GUILD_ID = discord.Object(id=1467879682019033088) # เช็ค ID เซิร์ฟให้ชัวร์นะพี่

# ตั้งค่าการค้นหาให้เข้มข้นขึ้น (แก้ปัญหาหาเพลงไม่เจอ)
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0', # แก้เรื่อง Network บางตัว
    'extract_flat': False,
    'nocheckcertificate': True,
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
        self.add_item(discord.ui.Button(label="เว็บของเรา", emoji="🌐", url="https://tetewebshop.com", row=1))

    @discord.ui.button(emoji="🛑", style=discord.ButtonStyle.danger, row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.bot.queue[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("⏹️ **หยุดเล่นและล้างคิวแล้ว**", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ **ข้ามเพลงให้แล้วครับ**", ephemeral=True)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary, row=0)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸️ **พักเพลงไว้ก่อน**", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                await interaction.response.send_message("▶️ **เล่นต่อแล้วครับ**", ephemeral=True)

    @discord.ui.button(label="AutoPlay", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def autoplay(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.bot.autoplay.get(self.guild_id, False)
        self.bot.autoplay[self.guild_id] = not current
        button.style = discord.ButtonStyle.success if not current else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🔄 **AutoPlay: {'เปิด ✅' if not current else 'ปิด ❌'}**", ephemeral=True)

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)
        self.queue = {}
        self.autoplay = {}
        self.last_track = {}

    async def setup_hook(self):
        try:
            self.tree.copy_global_to(guild=MY_GUILD_ID)
            await self.tree.sync(guild=MY_GUILD_ID)
            print(f"✅ Tete Music System Online! (Synced to {MY_GUILD_ID.id})")
        except Exception as e:
            print(f"⚠️ Sync Warning: {e}")

bot = MusicBot()

def create_embed(song, user, guild, status="กำลังเล่นเพลง"):
    embed = discord.Embed(title="🎵 Tete Music System", color=0xff0055)
    # ใส่รูป Banner ของพี่ตรงนี้
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif") 
    
    embed.description = f"**{status}:**\n```\n{song['title']}\n```"
    embed.add_field(name="Author:", value=f"╰─ **{song['uploader']}**", inline=True)
    embed.add_field(name="Duration:", value=f"╰─ `{song['duration']}`", inline=True)
    embed.add_field(name="Requester:", value=f"╰─ {user.mention}", inline=True)
    embed.set_footer(text="พิมพ์ชื่อเพลงที่อยากฟังในช่องแชท หรือใช้ /play ได้เลย")
    if song.get('thumbnail'):
        embed.set_thumbnail(url=song['thumbnail'])
    return embed

async def play_engine(guild, channel, user, song):
    vc = guild.voice_client
    if not vc: return
    
    bot.last_track[guild.id] = song
    
    def after_playing(error):
        coro = next_logic(guild, channel, user)
        fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
        try: fut.result()
        except: pass

    try:
        source = discord.PCMVolumeTransformer(await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS))
        source.volume = 0.8
        vc.play(source, after=after_playing)
        await channel.send(embed=create_embed(song, user, guild), view=TeteMusicView(bot, guild.id))
    except Exception as e:
        print(f"Play Error: {e}")
        await channel.send(f"❌ เกิดข้อผิดพลาดในการเล่น: {song['title']}")

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

@bot.tree.command(name="play", description="ค้นหาและเล่นเพลงจาก YouTube")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    
    if not interaction.user.voice:
        return await interaction.followup.send("❌ พี่ต้องเข้าห้องเสียงก่อนนะ!")

    vc = interaction.guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect(self_deaf=True)

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            # ค้นหาเพลง
            info = ydl.extract_info(f"ytsearch:{search}", download=False)
            if not info['entries']:
                return await interaction.followup.send("❌ หาเพลงไม่เจอจริงๆ พี่ ลองเปลี่ยนคำค้นดูนะ")
            
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
                await interaction.followup.send("🎶 กำลังเริ่มเล่นเพลง...")
                await play_engine(interaction.guild, interaction.channel, interaction.user, song)
        except Exception as e:
            print(f"Search Error: {e}")
            await interaction.followup.send("❌ ระบบค้นหาเพลงขัดข้อง ลองใหม่อีกทีครับ")

@bot.tree.command(name="setup", description="สร้างห้องเพลงพิเศษพร้อมหน้าจอควบคุม")
async def setup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    # สร้าง Text Channel ใหม่
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(send_messages=True),
        interaction.guild.me: discord.PermissionOverwrite(send_messages=True, embed_links=True)
    }
    channel = await interaction.guild.create_text_channel('🎵-tete-music', overwrites=overwrites)
    
    # Embed เริ่มต้นตอนยังไม่เล่นเพลง (ตามรูปที่พี่ส่งมา)
    embed = discord.Embed(title="🎵 Tete Music System", color=0x2f3136)
    embed.set_image(url="https://media.discordapp.net/attachments/1118943144889618534/1213054545622319134/standard_1.gif")
    embed.description = "```\nไม่มีเพลงที่กำลังเล่นอยู่ในขณะนี้\n```"
    embed.set_footer(text="พิมพ์ชื่อเพลงที่อยากฟัง หรือแปะลิงก์ได้เลย")
    
    await channel.send(embed=embed, view=TeteMusicView(bot, interaction.guild.id))
    await interaction.followup.send(f"✅ สร้างห้อง <#{channel.id}> เรียบร้อย! พี่ไปลองสั่งเพลงในนั้นได้เลย", ephemeral=True)

bot.run(TOKEN)
