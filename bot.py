import discord
from discord.ext import commands
import asyncio
import os

# ============================================================
#  ตั้งค่า Bot
# ============================================================
TOKEN = os.environ["TOKEN"]   # อ่านจาก Environment Variable บน Railway

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================================
#  Events
# ============================================================
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} (ID: {bot.user.id})")
    print("--------------------------------------------")


# ============================================================
#  !clone  —  Clone ห้องและหมวดหมู่จาก server ต้นทาง
# ============================================================
@bot.command(name="clone")
@commands.has_permissions(administrator=True)
async def clone_server(ctx, source_guild_id: int = None):
    """
    ใช้งาน:
        !clone                  → clone server ปัจจุบัน (จัดโครงสร้างใหม่)
        !clone <SERVER_ID>      → clone จาก server อื่นที่บอทอยู่

    บอทต้องมีสิทธิ์ Administrator ใน server ปลายทาง
    """
    dest_guild = ctx.guild

    # กำหนด server ต้นทาง
    if source_guild_id is None:
        source_guild = ctx.guild
    else:
        source_guild = bot.get_guild(source_guild_id)
        if source_guild is None:
            await ctx.send("❌ ไม่พบ Server ต้นทาง — ตรวจสอบว่าบอทอยู่ใน Server นั้นด้วย")
            return

    if source_guild.id == dest_guild.id and source_guild_id is not None:
        await ctx.send("⚠️ Server ต้นทางและปลายทางเป็น Server เดียวกัน")
        return

    msg = await ctx.send(
        f"⏳ กำลัง Clone จาก **{source_guild.name}** ไปยัง **{dest_guild.name}**...\n"
        "*(กระบวนการนี้จะลบห้องและหมวดหมู่เดิมทั้งหมดในเซิร์ฟเวอร์ปลายทาง)*"
    )

    # ────────────────────────────────────────────
    # 1. ลบทุกช่องและหมวดหมู่ใน server ปลายทาง
    # ────────────────────────────────────────────
    await msg.edit(content="🗑️ กำลังลบช่องและหมวดหมู่เดิม...")
    for channel in dest_guild.channels:
        try:
            await channel.delete()
            await asyncio.sleep(0.5)   # หน่วงเวลาเพื่อเลี่ยง rate limit
        except discord.Forbidden:
            await ctx.send(f"⚠️ ไม่มีสิทธิ์ลบ: {channel.name}")
        except Exception as e:
            await ctx.send(f"⚠️ Error ลบ {channel.name}: {e}")

    # ────────────────────────────────────────────
    # 2. Clone Roles (ข้าม @everyone)
    # ────────────────────────────────────────────
    await msg.edit(content="🎭 กำลัง Clone Roles...")
    role_map = {}   # source role id → dest role object

    # เรียงจาก position ต่ำไปสูง (ยกเว้น @everyone)
    sorted_roles = sorted(
        [r for r in source_guild.roles if r.name != "@everyone"],
        key=lambda r: r.position
    )

    for role in sorted_roles:
        try:
            new_role = await dest_guild.create_role(
                name=role.name,
                permissions=role.permissions,
                colour=role.colour,
                hoist=role.hoist,
                mentionable=role.mentionable,
            )
            role_map[role.id] = new_role
            await asyncio.sleep(0.5)
        except discord.Forbidden:
            await ctx.send(f"⚠️ ไม่มีสิทธิ์สร้าง Role: {role.name}")
        except Exception as e:
            await ctx.send(f"⚠️ Error สร้าง Role {role.name}: {e}")

    # ────────────────────────────────────────────
    # 3. Clone Categories และ Channels
    # ────────────────────────────────────────────
    await msg.edit(content="📁 กำลัง Clone หมวดหมู่และห้อง...")

    def build_overwrites(source_channel):
        """แปลง permission overwrites จาก source → dest"""
        new_overwrites = {}
        for target, overwrite in source_channel.overwrites.items():
            if isinstance(target, discord.Role):
                if target.name == "@everyone":
                    dest_role = dest_guild.default_role
                else:
                    dest_role = role_map.get(target.id)
                if dest_role:
                    new_overwrites[dest_role] = overwrite
        return new_overwrites

    # ── Channels ที่ไม่มี Category ──
    no_cat_channels = sorted(
        [c for c in source_guild.channels
         if c.category is None and not isinstance(c, discord.CategoryChannel)],
        key=lambda c: c.position
    )
    for ch in no_cat_channels:
        try:
            ow = build_overwrites(ch)
            if isinstance(ch, discord.TextChannel):
                await dest_guild.create_text_channel(
                    name=ch.name,
                    topic=ch.topic,
                    slowmode_delay=ch.slowmode_delay,
                    nsfw=ch.nsfw,
                    overwrites=ow,
                )
            elif isinstance(ch, discord.VoiceChannel):
                await dest_guild.create_voice_channel(
                    name=ch.name,
                    bitrate=min(ch.bitrate, dest_guild.bitrate_limit),
                    user_limit=ch.user_limit,
                    overwrites=ow,
                )
            elif isinstance(ch, discord.ForumChannel):
                await dest_guild.create_forum(
                    name=ch.name,
                    topic=ch.topic or "",
                    overwrites=ow,
                )
            await asyncio.sleep(0.5)
        except Exception as e:
            await ctx.send(f"⚠️ Error สร้างช่อง {ch.name}: {e}")

    # ── Categories + ช่องข้างใน ──
    sorted_categories = sorted(
        [c for c in source_guild.categories],
        key=lambda c: c.position
    )
    for category in sorted_categories:
        try:
            ow_cat = build_overwrites(category)
            new_category = await dest_guild.create_category(
                name=category.name,
                overwrites=ow_cat,
            )
            await asyncio.sleep(0.5)

            for channel in sorted(category.channels, key=lambda c: c.position):
                try:
                    ow_ch = build_overwrites(channel)
                    if isinstance(channel, discord.TextChannel):
                        await dest_guild.create_text_channel(
                            name=channel.name,
                            category=new_category,
                            topic=channel.topic,
                            slowmode_delay=channel.slowmode_delay,
                            nsfw=channel.nsfw,
                            overwrites=ow_ch,
                        )
                    elif isinstance(channel, discord.VoiceChannel):
                        await dest_guild.create_voice_channel(
                            name=channel.name,
                            category=new_category,
                            bitrate=min(channel.bitrate, dest_guild.bitrate_limit),
                            user_limit=channel.user_limit,
                            overwrites=ow_ch,
                        )
                    elif isinstance(channel, discord.StageChannel):
                        await dest_guild.create_stage_channel(
                            name=channel.name,
                            category=new_category,
                            overwrites=ow_ch,
                        )
                    elif isinstance(channel, discord.ForumChannel):
                        await dest_guild.create_forum(
                            name=channel.name,
                            category=new_category,
                            topic=channel.topic or "",
                            overwrites=ow_ch,
                        )
                    await asyncio.sleep(0.5)
                except Exception as e:
                    await ctx.send(f"⚠️ Error สร้างช่อง {channel.name}: {e}")

        except Exception as e:
            await ctx.send(f"⚠️ Error สร้าง Category {category.name}: {e}")

    # ────────────────────────────────────────────
    # 4. เสร็จสิ้น
    # ────────────────────────────────────────────
    total_cats = len(source_guild.categories)
    total_channels = len([c for c in source_guild.channels
                          if not isinstance(c, discord.CategoryChannel)])
    total_roles = len(role_map)

    await msg.edit(
        content=(
            f"✅ **Clone สำเร็จ!**\n"
            f"📁 หมวดหมู่: `{total_cats}` | "
            f"💬 ห้อง: `{total_channels}` | "
            f"🎭 Roles: `{total_roles}`"
        )
    )


# ============================================================
#  !serverlist  —  ดู Server ที่บอทอยู่ (พร้อม ID)
# ============================================================
@bot.command(name="serverlist")
@commands.has_permissions(administrator=True)
async def server_list(ctx):
    """แสดงรายชื่อ Server ทั้งหมดที่บอทอยู่ พร้อม ID"""
    lines = [f"**Server ที่บอทอยู่ทั้งหมด:**"]
    for guild in bot.guilds:
        lines.append(f"• {guild.name} — `{guild.id}`")
    await ctx.send("\n".join(lines))


# ============================================================
#  Error Handler
# ============================================================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (ต้องการ Administrator)")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ รูปแบบคำสั่งไม่ถูกต้อง\nตัวอย่าง: `!clone` หรือ `!clone 1234567890`")
    else:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {error}")


# ============================================================
#  Run
# ============================================================
bot.run(TOKEN)
