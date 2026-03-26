import discord
from discord.ext import commands
import asyncio
import os

# ============================================================
#  ตั้งค่า Bot
# ============================================================
TOKEN = os.environ["TOKEN"]

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
#  Helper: รัน coroutine พร้อม retry อัตโนมัติตอน rate limit
# ============================================================
async def safe_run(label, coro, retries=5):
    for attempt in range(retries):
        try:
            result = await coro
            await asyncio.sleep(1.0)
            return result
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = 5.0
                try:
                    retry_after = float(e.response.headers.get("Retry-After", 5))
                except Exception:
                    pass
                print(f"⏳ Rate limit [{label}] — รอ {retry_after:.1f}s (ครั้งที่ {attempt+1})")
                await asyncio.sleep(retry_after + 1)
            else:
                print(f"❌ HTTP {e.status} [{label}]: {e.text}")
                return None
        except discord.Forbidden:
            print(f"🚫 Forbidden [{label}]: บอทไม่มีสิทธิ์")
            return None
        except Exception as e:
            print(f"⚠️ Error [{label}]: {type(e).__name__}: {e}")
            return None
    print(f"❌ หมดจำนวน retry [{label}]")
    return None


# ============================================================
#  !clone
# ============================================================
@bot.command(name="clone")
@commands.has_permissions(administrator=True)
async def clone_server(ctx, source_guild_id: int = None):
    """
    !clone                → clone โครงสร้างใน server นี้ใหม่
    !clone <SERVER_ID>    → clone จาก server อื่น
    """
    dest_guild = ctx.guild

    if source_guild_id is None:
        source_guild = ctx.guild
    else:
        source_guild = bot.get_guild(source_guild_id)
        if source_guild is None:
            await ctx.send("❌ ไม่พบ Server ต้นทาง — บอทต้องอยู่ใน Server นั้นด้วย")
            return

    if source_guild.id == dest_guild.id and source_guild_id is not None:
        await ctx.send("⚠️ ต้นทางและปลายทางเป็น Server เดียวกัน")
        return

    total_src_cats = len(source_guild.categories)
    total_src_ch   = len([c for c in source_guild.channels
                          if not isinstance(c, discord.CategoryChannel)])
    print(f"📋 ต้นทาง: {source_guild.name} | {total_src_cats} categories, {total_src_ch} channels")

    msg = await ctx.send(
        f"⏳ กำลัง Clone จาก **{source_guild.name}** → **{dest_guild.name}**\n"
        f"📋 ต้นทางมี `{total_src_cats}` categories, `{total_src_ch}` channels\n"
        "*(ห้องและหมวดหมู่เดิมจะถูกลบก่อน)*"
    )

    # ── 1. ลบห้องเดิม ──
    await msg.edit(content="🗑️ [1/4] กำลังลบห้องและหมวดหมู่เดิม...")
    print("── Step 1: ลบห้องเดิม ──")
    channels_to_delete = list(dest_guild.channels)
    for ch in channels_to_delete:
        print(f"  ลบ: #{ch.name}")
        await safe_run(f"delete {ch.name}", ch.delete())
    print(f"  ✅ ลบเสร็จ {len(channels_to_delete)} ช่อง")

    # ── 2. Clone Roles ──
    await msg.edit(content="🎭 [2/4] กำลัง Clone Roles...")
    print("── Step 2: Clone Roles ──")
    role_map = {}
    sorted_roles = sorted(
        [r for r in source_guild.roles if r.name != "@everyone"],
        key=lambda r: r.position
    )
    for role in sorted_roles:
        print(f"  สร้าง role: {role.name}")
        new_role = await safe_run(
            f"role {role.name}",
            dest_guild.create_role(
                name=role.name,
                permissions=role.permissions,
                colour=role.colour,
                hoist=role.hoist,
                mentionable=role.mentionable,
            )
        )
        if new_role:
            role_map[role.id] = new_role
    print(f"  ✅ สร้าง roles เสร็จ {len(role_map)} roles")

    # ── 3. Clone Categories + Channels ──
    await msg.edit(content="📁 [3/4] กำลัง Clone Categories และ Channels...")
    print("── Step 3: Clone Channels ──")

    def build_overwrites(src_ch):
        ow = {}
        for target, overwrite in src_ch.overwrites.items():
            if isinstance(target, discord.Role):
                if target.name == "@everyone":
                    ow[dest_guild.default_role] = overwrite
                elif target.id in role_map:
                    ow[role_map[target.id]] = overwrite
        return ow

    created_ch = 0
    failed_ch  = 0

    # ช่องไม่มี category
    no_cat = sorted(
        [c for c in source_guild.channels
         if c.category is None and not isinstance(c, discord.CategoryChannel)],
        key=lambda c: c.position
    )
    for ch in no_cat:
        ow = build_overwrites(ch)
        print(f"  สร้างช่อง (no cat): #{ch.name}")
        result = None
        if isinstance(ch, discord.TextChannel):
            result = await safe_run(
                f"text {ch.name}",
                dest_guild.create_text_channel(
                    name=ch.name, topic=ch.topic,
                    slowmode_delay=ch.slowmode_delay,
                    nsfw=ch.nsfw, overwrites=ow,
                )
            )
        elif isinstance(ch, discord.VoiceChannel):
            result = await safe_run(
                f"voice {ch.name}",
                dest_guild.create_voice_channel(
                    name=ch.name,
                    bitrate=min(ch.bitrate, dest_guild.bitrate_limit),
                    user_limit=ch.user_limit, overwrites=ow,
                )
            )
        if result:
            created_ch += 1
        else:
            failed_ch += 1

    # categories + ช่องข้างใน
    sorted_categories = sorted(source_guild.categories, key=lambda c: c.position)
    for cat in sorted_categories:
        print(f"  สร้าง category: {cat.name}")
        ow_cat = build_overwrites(cat)
        new_cat = await safe_run(
            f"category {cat.name}",
            dest_guild.create_category(name=cat.name, overwrites=ow_cat)
        )
        if new_cat is None:
            print(f"  ❌ สร้าง category ล้มเหลว: {cat.name}")
            failed_ch += len(cat.channels)
            continue

        for ch in sorted(cat.channels, key=lambda c: c.position):
            ow = build_overwrites(ch)
            print(f"    สร้าง: #{ch.name} [{type(ch).__name__}]")
            result = None

            if isinstance(ch, discord.TextChannel):
                result = await safe_run(
                    f"text {ch.name}",
                    dest_guild.create_text_channel(
                        name=ch.name, category=new_cat, topic=ch.topic,
                        slowmode_delay=ch.slowmode_delay,
                        nsfw=ch.nsfw, overwrites=ow,
                    )
                )
            elif isinstance(ch, discord.VoiceChannel):
                result = await safe_run(
                    f"voice {ch.name}",
                    dest_guild.create_voice_channel(
                        name=ch.name, category=new_cat,
                        bitrate=min(ch.bitrate, dest_guild.bitrate_limit),
                        user_limit=ch.user_limit, overwrites=ow,
                    )
                )
            elif isinstance(ch, discord.StageChannel):
                result = await safe_run(
                    f"stage {ch.name}",
                    dest_guild.create_stage_channel(
                        name=ch.name, category=new_cat, overwrites=ow,
                    )
                )
            elif isinstance(ch, discord.ForumChannel):
                result = await safe_run(
                    f"forum {ch.name}",
                    dest_guild.create_forum(
                        name=ch.name, category=new_cat,
                        topic=ch.topic or "", overwrites=ow,
                    )
                )

            if result:
                created_ch += 1
            else:
                failed_ch += 1

    print(f"  ✅ สร้างช่องเสร็จ: {created_ch} สำเร็จ, {failed_ch} ล้มเหลว")

    # ── 4. สรุป ──
    status = "✅" if failed_ch == 0 else "⚠️"
    summary = (
        f"{status} **Clone เสร็จแล้ว!**\n"
        f"📁 Categories: `{len(sorted_categories)}`\n"
        f"💬 Channels: `{created_ch}` / `{created_ch + failed_ch}` สำเร็จ\n"
        f"🎭 Roles: `{len(role_map)}`"
    )
    if failed_ch > 0:
        summary += f"\n⚠️ ล้มเหลว `{failed_ch}` ช่อง — ดู log ใน Railway console"

    await msg.edit(content=summary)
    print(f"── Clone เสร็จ: {created_ch} OK, {failed_ch} FAIL ──")


# ============================================================
#  !serverlist
# ============================================================
@bot.command(name="serverlist")
@commands.has_permissions(administrator=True)
async def server_list(ctx):
    lines = ["**Server ที่บอทอยู่ทั้งหมด:**"]
    for guild in bot.guilds:
        lines.append(f"• {guild.name} — `{guild.id}`")
    await ctx.send("\n".join(lines))


# ============================================================
#  Error Handler
# ============================================================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ ต้องการสิทธิ์ Administrator")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ รูปแบบผิด — ตัวอย่าง: `!clone` หรือ `!clone 1234567890`")
    else:
        print(f"Unhandled error: {error}")
        await ctx.send(f"❌ Error: {error}")


# ============================================================
#  Run
# ============================================================
bot.run(TOKEN)
