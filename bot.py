import discord
from discord.ext import commands
import yt_dlp
import asyncio
import static_ffmpeg
import os
import random

static_ffmpeg.add_paths()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# queue[guild_id] = [(song, user), ...]
queue = {}
now_playing = {}
autoplay_enabled = {}

# ---------------- YDL OPTIONS (แก้ YouTube บล็อก) ----------------
def build_ydl_options():
    opts = {
        'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'extract_flat': False,
        'age_limit': None,
        'geo_bypass': True,
        'geo_bypass_country': 'TH',
        # ใช้ iOS client — ไม่ถูก bot-check เหมือน web
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web'],
                'player_skip': ['webpage', 'js'],
            }
        },
        # headers เหมือน browser จริง
        'http_headers': {
            'User-Agent': (
                'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 '
                'Mobile/15E148 Safari/604.1'
            ),
            'Accept-Language': 'th-TH,th;q=0.9,en;q=0.8',
        },
        'socket_timeout': 15,
        'retries': 3,
    }

    if os.path.exists('cookies.txt'):
        with open('cookies.txt', 'r', errors='ignore') as f:
            first_line = f.readline().strip()
        if 'Netscape' in first_line or first_line.startswith('#'):
            opts['cookiefile'] = 'cookies.txt'
            print("✅ ใช้ cookies.txt")
        else:
            print("⚠️  cookies.txt ผิด format — ข้ามการใช้ cookies")
    else:
        print("⚠️  ไม่พบ cookies.txt — โหลดแบบไม่มี cookies")

    return opts

# fallback ถ้า iOS client ยัง bล็อก — ลอง mweb + android_vr
def build_ydl_options_fallback():
    opts = build_ydl_options()
    opts['extractor_args'] = {
        'youtube': {
            'player_client': ['mweb', 'android_vr'],
        }
    }
    return opts

FFMPEG_OPTIONS = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
        '-nostdin'
    ),
    'options': '-vn -b:a 128k',
}

AUTOPLAY_SEEDS = [
    "lofi hip hop chill",
    "jazz relaxing music",
    "phonk music mix",
    "city pop playlist",
    "anime ost mix",
    "synthwave mix",
    "thai indie music",
]

# ---------------- EMBED ----------------
def embed_now(song, user):
    e = discord.Embed(
        title="🎧 Now Playing",
        description=f"```{song['title']}```",
        color=0x0f0f0f
    )
    e.add_field(name="👤 User", value=user.mention)
    e.add_field(name="⏱️ Duration", value=song['duration'])
    e.add_field(name="📊 Status", value="🟢 Playing")
    e.set_thumbnail(url=song.get("thumbnail"))
    e.set_footer(text="Tete Music System")
    return e

def embed_queue(song, position):
    return discord.Embed(
        description=f"➕ Added to queue (#{position})\n```{song['title']}```",
        color=0x00ffaa
    )

def embed_error(msg):
    return discord.Embed(description=f"❌ {msg}", color=0xff0000)

def embed_info(msg):
    return discord.Embed(description=msg, color=0x00aaff)

# ---------------- CONTROL PANEL ----------------
class Control(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction, button):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭️ Skipped", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ไม่มีเพลงเล่นอยู่", ephemeral=True)

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.success)
    async def pause(self, interaction, button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Paused", ephemeral=True)
        elif vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Resumed", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ไม่มีเพลงเล่นอยู่", ephemeral=True)

    @discord.ui.button(label="🛑 Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction, button):
        vc = interaction.guild.voice_client
        if vc:
            queue[self.guild_id] = []
            now_playing.pop(self.guild_id, None)
            await vc.disconnect()
            await interaction.response.send_message("🛑 Stopped & Disconnected", ephemeral=True)
        else:
            await interaction.response.send_message("❌ บอทไม่ได้อยู่ในห้อง", ephemeral=True)

    @discord.ui.button(label="📋 Queue", style=discord.ButtonStyle.primary)
    async def show_queue(self, interaction, button):
        await interaction.response.send_message(
            embed=build_queue_embed(self.guild_id),
            ephemeral=True
        )

    @discord.ui.button(label="🔀 Autoplay", style=discord.ButtonStyle.secondary)
    async def toggle_autoplay(self, interaction, button):
        gid = self.guild_id
        autoplay_enabled[gid] = not autoplay_enabled.get(gid, True)
        state = "🟢 เปิด" if autoplay_enabled[gid] else "🔴 ปิด"
        await interaction.response.send_message(f"🔀 Autoplay: {state}", ephemeral=True)

# ---------------- QUEUE EMBED ----------------
def build_queue_embed(guild_id):
    np = now_playing.get(guild_id)
    q = queue.get(guild_id, [])
    ap = autoplay_enabled.get(guild_id, True)

    e = discord.Embed(title="📋 Queue", color=0x0f0f0f)
    if np:
        e.add_field(name="🎧 Now Playing", value=f"```{np['song']['title']}```", inline=False)
    else:
        e.add_field(name="🎧 Now Playing", value="```ไม่มีเพลง```", inline=False)

    if q:
        lines = [f"`{i+1}.` {s['title']}" for i, (s, _) in enumerate(q)]
        e.add_field(name=f"📃 Next ({len(q)} songs)", value="\n".join(lines[:10]), inline=False)
        if len(q) > 10:
            e.set_footer(text=f"และอีก {len(q)-10} เพลง...")
    else:
        e.add_field(name="📃 Next", value="```ว่างเปล่า```", inline=False)

    e.add_field(name="🔀 Autoplay", value="🟢 เปิด" if ap else "🔴 ปิด", inline=False)
    return e

# ---------------- FETCH SONG (มี fallback 2 ชั้น) ----------------
async def fetch_song(search):
    query = search if search.startswith("http") else f"ytsearch1:{search}"
    loop = asyncio.get_event_loop()

    # ลองด้วย options หลัก (iOS client)
    for opts_func, label in [
        (build_ydl_options, "iOS client"),
        (build_ydl_options_fallback, "mweb/android_vr fallback"),
    ]:
        try:
            with yt_dlp.YoutubeDL(opts_func()) as ydl:
                info = await loop.run_in_executor(
                    None, lambda: ydl.extract_info(query, download=False)
                )
                data = info['entries'][0] if 'entries' in info else info
                url = data.get('url') or (data.get('formats') or [{}])[-1].get('url')
                if not url:
                    raise ValueError("ไม่พบ stream URL")
                print(f"✅ โหลดสำเร็จด้วย {label}: {data['title']}")
                return {
                    'url': url,
                    'title': data['title'],
                    'duration': data.get('duration_string', '0:00'),
                    'thumbnail': data.get('thumbnail'),
                }
        except Exception as e:
            print(f"⚠️  {label} ล้มเหลว: {e}")

    print("❌ โหลดเพลงล้มเหลวทุก client")
    return None

# ---------------- PLAYER ----------------
async def play_next(guild, channel):
    gid = guild.id
    now_playing.pop(gid, None)

    if queue.get(gid):
        song, user = queue[gid].pop(0)
        await play_song(guild, channel, song, user)
    elif autoplay_enabled.get(gid, True):
        seed = random.choice(AUTOPLAY_SEEDS)
        await channel.send(embed=discord.Embed(
            description=f"🔀 Autoplay กำลังสุ่มเพลง: `{seed}`",
            color=0x888888
        ))
        song = await fetch_song(seed)
        if song:
            await play_song(guild, channel, song, guild.me)
        else:
            await channel.send(embed=embed_error("Autoplay โหลดเพลงไม่ได้"))

async def play_song(guild, channel, song, user):
    vc = guild.voice_client
    if not vc:
        return

    try:
        source = await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS)
    except Exception as e:
        print(f"❌ FFmpeg error: {e}")
        await channel.send(embed=embed_error("เล่นเพลงไม่ได้ ข้ามไปเพลงถัดไป..."))
        await play_next(guild, channel)
        return

    now_playing[guild.id] = {'song': song, 'user': user}

    vc.play(
        source,
        after=lambda e: asyncio.run_coroutine_threadsafe(
            play_next(guild, channel), bot.loop
        )
    )

    await channel.send(embed=embed_now(song, user), view=Control(guild.id))

# ---------------- HANDLE PLAY ----------------
async def handle_play(guild, channel, author, search):
    if not author.voice:
        return await channel.send(embed=embed_error("เข้าห้อง voice ก่อน"))

    vc = guild.voice_client
    if not vc:
        vc = await author.voice.channel.connect()
    elif vc.channel != author.voice.channel:
        await vc.move_to(author.voice.channel)

    # แสดง loading
    loading_msg = await channel.send(embed=discord.Embed(
        description=f"🔍 กำลังโหลด: `{search}`...",
        color=0x888888
    ))

    song = await fetch_song(search)
    await loading_msg.delete()

    if not song:
        return await channel.send(embed=embed_error(
            "โหลดเพลงไม่ได้\n"
            "• YouTube อาจบล็อก IP ของ server\n"
            "• ลองใส่ cookies.txt ใหม่\n"
            "• หรือลอง URL อื่น"
        ))

    if vc.is_playing() or vc.is_paused():
        q = queue.setdefault(guild.id, [])
        q.append((song, author))
        await channel.send(embed=embed_queue(song, len(q)))
    else:
        await play_song(guild, channel, song, author)

# ---------------- AUTO (พิมพ์ในช่อง 🎵-music) ----------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.name == "🎵-music":
        try:
            await message.delete()
        except Exception:
            pass
        if message.content.strip():
            await handle_play(message.guild, message.channel, message.author, message.content)
        return

    await bot.process_commands(message)

# ---------------- PREFIX COMMANDS ----------------
@bot.command(name="play", aliases=["p"])
async def cmd_play(ctx, *, search: str):
    await handle_play(ctx.guild, ctx.channel, ctx.author, search)

@bot.command(name="skip", aliases=["s"])
async def cmd_skip(ctx):
    vc = ctx.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await ctx.send(embed=embed_info("⏭️ Skipped"))
    else:
        await ctx.send(embed=embed_error("ไม่มีเพลงเล่นอยู่"))

@bot.command(name="pause")
async def cmd_pause(ctx):
    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send(embed=embed_info("⏸️ Paused"))
    else:
        await ctx.send(embed=embed_error("ไม่มีเพลงเล่นอยู่"))

@bot.command(name="resume", aliases=["r"])
async def cmd_resume(ctx):
    vc = ctx.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send(embed=embed_info("▶️ Resumed"))
    else:
        await ctx.send(embed=embed_error("ไม่ได้หยุดอยู่"))

@bot.command(name="stop")
async def cmd_stop(ctx):
    vc = ctx.guild.voice_client
    if vc:
        queue[ctx.guild.id] = []
        now_playing.pop(ctx.guild.id, None)
        await vc.disconnect()
        await ctx.send(embed=embed_info("🛑 Stopped & Disconnected"))
    else:
        await ctx.send(embed=embed_error("บอทไม่ได้อยู่ในห้อง"))

@bot.command(name="queue", aliases=["q"])
async def cmd_queue(ctx):
    await ctx.send(embed=build_queue_embed(ctx.guild.id))

@bot.command(name="nowplaying", aliases=["np"])
async def cmd_nowplaying(ctx):
    np = now_playing.get(ctx.guild.id)
    if np:
        await ctx.send(embed=embed_now(np['song'], np['user']))
    else:
        await ctx.send(embed=embed_error("ไม่มีเพลงเล่นอยู่"))

@bot.command(name="clear", aliases=["cl"])
async def cmd_clear(ctx):
    queue[ctx.guild.id] = []
    await ctx.send(embed=embed_info("🗑️ ล้างคิวแล้ว"))

@bot.command(name="autoplay", aliases=["ap"])
async def cmd_autoplay(ctx):
    gid = ctx.guild.id
    autoplay_enabled[gid] = not autoplay_enabled.get(gid, True)
    state = "🟢 เปิด" if autoplay_enabled[gid] else "🔴 ปิด"
    await ctx.send(embed=embed_info(f"🔀 Autoplay: {state}"))

@bot.command(name="move", aliases=["mv"])
async def cmd_move(ctx, from_pos: int, to_pos: int):
    q = queue.get(ctx.guild.id, [])
    if not q:
        return await ctx.send(embed=embed_error("คิวว่างเปล่า"))
    if not (1 <= from_pos <= len(q)) or not (1 <= to_pos <= len(q)):
        return await ctx.send(embed=embed_error(f"ตำแหน่งต้องอยู่ระหว่าง 1-{len(q)}"))
    item = q.pop(from_pos - 1)
    q.insert(to_pos - 1, item)
    await ctx.send(embed=embed_info(f"↕️ ย้าย `{item[0]['title']}` ไปตำแหน่ง {to_pos}"))

@bot.command(name="remove", aliases=["rm"])
async def cmd_remove(ctx, pos: int):
    q = queue.get(ctx.guild.id, [])
    if not q:
        return await ctx.send(embed=embed_error("คิวว่างเปล่า"))
    if not (1 <= pos <= len(q)):
        return await ctx.send(embed=embed_error(f"ตำแหน่งต้องอยู่ระหว่าง 1-{len(q)}"))
    removed = q.pop(pos - 1)
    await ctx.send(embed=embed_info(f"🗑️ ลบ `{removed[0]['title']}` ออกแล้ว"))

@bot.command(name="menu", aliases=["h", "help"])
async def cmd_help(ctx):
    e = discord.Embed(title="🎧 Tete Music — คำสั่งทั้งหมด", color=0x0f0f0f)
    cmds = [
        ("!play / !p <เพลง>", "เล่นเพลงหรือเพิ่มเข้าคิว"),
        ("!skip / !s", "ข้ามเพลง"),
        ("!pause", "หยุดชั่วคราว"),
        ("!resume / !r", "เล่นต่อ"),
        ("!stop", "หยุดและออกจากห้อง"),
        ("!queue / !q", "ดูคิวเพลง"),
        ("!nowplaying / !np", "ดูเพลงที่กำลังเล่น"),
        ("!clear / !cl", "ล้างคิว"),
        ("!autoplay / !ap", "เปิด/ปิด autoplay"),
        ("!move / !mv <จาก> <ไป>", "ย้ายเพลงในคิว"),
        ("!remove / !rm <ตำแหน่ง>", "ลบเพลงออกจากคิว"),
        ("!menu / !h", "แสดงคำสั่งทั้งหมด"),
        ("!setup", "สร้างห้อง 🎵-music + แผงควบคุม"),
    ]
    for name, desc in cmds:
        e.add_field(name=f"`{name}`", value=desc, inline=False)
    e.set_footer(text="หรือพิมพ์ชื่อเพลงในช่อง 🎵-music ได้เลย")
    await ctx.send(embed=e)

# ---------------- SETUP ----------------
@bot.command(name="setup")
async def cmd_setup(ctx):
    channel = discord.utils.get(ctx.guild.text_channels, name="🎵-music")
    if not channel:
        channel = await ctx.guild.create_text_channel("🎵-music")

    embed = discord.Embed(
        title="🎧 Tete Music",
        description="```พิมพ์ชื่อเพลงหรือ URL ได้เลย\nหรือใช้ !play <เพลง>```",
        color=0x0f0f0f
    )
    embed.add_field(name="📌 Status", value="🟢 พร้อมใช้งาน", inline=False)
    embed.add_field(
        name="🎮 ปุ่มควบคุม",
        value="⏭️ Skip | ⏸️ Pause | 🛑 Stop | 📋 Queue | 🔀 Autoplay",
        inline=False
    )
    embed.set_footer(text="Tete Music System")
    await channel.send(embed=embed, view=Control(ctx.guild.id))
    await ctx.send(f"✅ สร้าง {channel.mention} เรียบร้อย")

# ---------------- SLASH COMMANDS ----------------
@bot.tree.command(name="play", description="เล่นเพลงจาก YouTube")
async def slash_play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    await handle_play(interaction.guild, interaction.channel, interaction.user, search)

@bot.tree.command(name="queue", description="ดูคิวเพลง")
async def slash_queue(interaction: discord.Interaction):
    await interaction.response.send_message(embed=build_queue_embed(interaction.guild_id))

@bot.tree.command(name="skip", description="ข้ามเพลง")
async def slash_skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message(embed=embed_info("⏭️ Skipped"))
    else:
        await interaction.response.send_message(embed=embed_error("ไม่มีเพลงเล่นอยู่"))

@bot.tree.command(name="stop", description="หยุดและออกจากห้อง")
async def slash_stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        queue[interaction.guild_id] = []
        now_playing.pop(interaction.guild_id, None)
        await vc.disconnect()
        await interaction.response.send_message(embed=embed_info("🛑 Stopped"))
    else:
        await interaction.response.send_message(embed=embed_error("บอทไม่ได้อยู่ในห้อง"))

# ---------------- READY ----------------
@bot.event
async def on_ready():
    print(f"🔥 Bot Ready: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"❌ Sync failed: {e}")

bot.run(TOKEN)
