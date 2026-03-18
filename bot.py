import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import static_ffmpeg
import os  # เพิ่มเพื่อดึงค่าจาก Environment Variables
from datetime import datetime, timedelta

# --- [ตั้งค่า ID ทั้งหมด] ---
# สำหรับ Railway: แนะนำให้ใส่ TOKEN ในหน้า Config Variables ของ Railway 
# แล้วใช้ os.getenv('TOKEN') แทนการแปะลงไปตรงๆ ในโค้ด
TOKEN = os.getenv('TOKEN') or 'ใส่_TOKEN_เดิม_ตรงนี้_ถ้ายังไม่เอาลง_Railway'

MY_GUILD_ID = discord.Object(id=1470028388335882394)
TARGET_CATEGORY_ID = 1482303742866100315 
BLACKLIST_ROLE_ID = 1482330184395788331 
LOG_CHANNEL_ID = 1483080342528196681
UNBAN_CHANNEL_ID = 1482347205107908730  

# --- [ตั้งค่าระบบเพลง] ---
YDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'no_warnings': True, 'default_search': 'ytsearch', 'source_address': '0.0.0.0'}
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.warnings = {} 
        self.queue = {}    
        self.voice_log_id = None
        self.server_log_id = None

    async def setup_hook(self):
        static_ffmpeg.add_paths()
        self.tree.copy_global_to(guild=MY_GUILD_ID)
        await self.tree.sync(guild=MY_GUILD_ID)
        print(f"✅ บอทออนไลน์สมบูรณ์แบบ 100% พร้อมระบบ Log!")

bot = MusicBot()

# --- [1. คำสั่งตั้งค่าระบบ Log] ---
@bot.command()
@commands.has_permissions(administrator=True)
async def setvoice(ctx, channel: discord.TextChannel):
    bot.voice_log_id = channel.id
    await ctx.send(f"✅ ตั้งค่าห้อง Log เสียงไปที่ {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setlog(ctx, channel: discord.TextChannel):
    bot.server_log_id = channel.id
    await ctx.send(f"✅ ตั้งค่าห้อง Log เซิร์ฟเวอร์ไปที่ {channel.mention}")

# --- [2. ระบบ Log เหตุการณ์ต่างๆ] ---
@bot.event
async def on_voice_state_update(member, before, after):
    if not bot.voice_log_id: return
    channel = bot.get_channel(bot.voice_log_id)
    if not channel: return
    embed = discord.Embed(timestamp=datetime.now())
    if before.channel is None and after.channel is not None:
        embed.title, embed.description, embed.color = "📥 เข้าห้องเสียง", f"**{member}** เข้าห้อง `{after.channel.name}`", discord.Color.green()
    elif before.channel is not None and after.channel is None:
        embed.title, embed.description, embed.color = "📤 ออกจากห้องเสียง", f"**{member}** ออกจากห้อง `{before.channel.name}`", discord.Color.red()
    elif before.channel != after.channel:
        embed.title, embed.description, embed.color = "🔄 ย้ายห้องเสียง", f"**{member}** ย้ายจาก `{before.channel.name}` ➡️ `{after.channel.name}`", discord.Color.blue()
    else: return
    await channel.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    if after.author.bot or not bot.server_log_id or before.content == after.content: return
    channel = bot.get_channel(bot.server_log_id)
    if not channel: return
    embed = discord.Embed(title="📝 แก้ไขข้อความ", color=discord.Color.orange(), timestamp=datetime.now())
    embed.set_author(name=after.author, icon_url=after.author.display_avatar.url)
    embed.add_field(name="ก่อนแก้ไข", value=before.content or "ไม่มีข้อความ", inline=False)
    embed.add_field(name="หลังแก้ไข", value=after.content or "ไม่มีข้อความ", inline=False)
    embed.add_field(name="ห้อง", value=after.channel.mention)
    await channel.send(embed=embed)

@bot.event
async def on_member_update(before, after):
    if before.nick != after.nick and bot.server_log_id:
        channel = bot.get_channel(bot.server_log_id)
        if not channel: return
        embed = discord.Embed(title="👤 เปลี่ยนชื่อเล่น", color=discord.Color.magenta(), timestamp=datetime.now())
        embed.set_author(name=after, icon_url=after.display_avatar.url)
        embed.add_field(name="ชื่อเดิม", value=before.nick or before.name)
        embed.add_field(name="ชื่อใหม่", value=after.nick or after.name)
        await channel.send(embed=embed)

# --- [3. ระบบ Blacklist & Log ลบข้อความ] ---
@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.category_id == TARGET_CATEGORY_ID:
        if any(role.id == BLACKLIST_ROLE_ID for role in message.author.roles):
            try:
                await message.delete()
                return
            except: pass
    await bot.process_commands(message)

@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    if bot.server_log_id:
        log_ch = bot.get_channel(bot.server_log_id)
        if log_ch:
            embed = discord.Embed(title="🗑️ ลบข้อความ", color=discord.Color.red(), timestamp=datetime.now())
            embed.set_author(name=message.author, icon_url=message.author.display_avatar.url)
            embed.description = f"**เนื้อหา:** {message.content or 'ไม่มีข้อความ'}\n**ห้อง:** {message.channel.mention}"
            await log_ch.send(embed=embed)

    if message.channel.category_id == TARGET_CATEGORY_ID:
        if any(role.id == BLACKLIST_ROLE_ID for role in message.author.roles): return
        uid, now = message.author.id, datetime.now()
        if uid in bot.warnings and now - bot.warnings[uid]['last_time'] > timedelta(hours=1):
            bot.warnings[uid] = {'count': 0, 'last_time': now}
        if uid not in bot.warnings:
            bot.warnings[uid] = {'count': 1, 'last_time': now}
        else:
            bot.warnings[uid]['count'] += 1
            bot.warnings[uid]['last_time'] = now

        count = bot.warnings[uid]['count']
        if count == 1:
            await message.channel.send(f"⚠️ {message.author.mention} **อย่าลบข้อความตอนประมูล!** (เตือนครั้งที่ 1/2)", delete_after=15)
        elif count >= 2:
            role = message.guild.get_role(BLACKLIST_ROLE_ID)
            if role:
                try:
                    await message.author.add_roles(role)
                    bot.warnings[uid]['count'] = 0 
                    log_black = bot.get_channel(LOG_CHANNEL_ID)
                    if log_black:
                        embed = discord.Embed(title="🚫 ประกาศ Blacklist", description=f"สมาชิก {message.author.mention} ทำผิดกฎการลบข้อความประมูล", color=0xff0000, timestamp=now)
                        embed.set_thumbnail(url=message.author.display_avatar.url)
                        embed.add_field(name="📌 สาเหตุ", value="ลบข้อความในห้องประมูล (2/2)", inline=False)
                        embed.add_field(name="🔓 การปลด", value=f"ติดต่อที่ <#{UNBAN_CHANNEL_ID}>", inline=True)
                        view = discord.ui.View()
                        view.add_item(discord.ui.Button(label="ไปที่ห้องปลด Blacklist", url=f"https://discord.com/channels/{message.guild.id}/{UNBAN_CHANNEL_ID}"))
                        await log_black.send(embed=embed, view=view)
                except: pass

# --- [4. ระบบเพลง] ---
async def play_next(interaction):
    gid = interaction.guild_id
    if gid in bot.queue and bot.queue[gid]:
        song = bot.queue[gid].pop(0)
        vc = interaction.guild.voice_client
        if vc:
            source = await discord.FFmpegOpusAudio.from_probe(song['url'], **FFMPEG_OPTIONS)
            vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop))
            await interaction.channel.send(f"🎶 เพลงถัดไป: **{song['title']}**")

@bot.tree.command(name="play", description="เล่นเพลงจาก YouTube")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    if not interaction.user.voice: return await interaction.followup.send("❌ เข้าห้องเสียงก่อนนะ!")
    vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect(self_deaf=True)
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(search, download=False)
            if 'entries' in info: info = info['entries'][0]
            url, title = info['url'], info['title']
        except Exception: return await interaction.followup.send(f"❌ หาเพลงไม่เจอ")
    source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
    if vc.is_playing():
        bot.queue.setdefault(interaction.guild_id, []).append({'url': url, 'title': title})
        await interaction.followup.send(f"➕ เพิ่มเข้าคิว: **{title}**")
    else:
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop))
        await interaction.followup.send(f"▶️ กำลังเล่น: **{title}**")

@bot.tree.command(name="skip", description="ข้ามเพลง")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing(): vc.stop(); await interaction.response.send_message("⏭️ ข้ามเพลงเรียบร้อย")
    else: await interaction.response.send_message("❌ ไม่มีเพลงเล่นอยู่")

@bot.tree.command(name="stop", description="หยุดเพลงและล้างคิว")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect(); bot.queue[interaction.guild_id] = []
        await interaction.response.send_message("⏹️ ออกจากห้องเสียงแล้ว")
    else: await interaction.response.send_message("❌ บอทไม่ได้อยู่ในห้องเสียง")

bot.run(TOKEN)