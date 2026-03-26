import discord
from discord.ext import commands
import asyncio
import os

TOKEN = os.environ["TOKEN"]

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์: {bot.user} (ID: {bot.user.id})")

# ============================================================
#  Helper: retry อัตโนมัติ
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
                print(f"⏳ Rate limit [{label}] รอ {retry_after:.1f}s")
                await asyncio.sleep(retry_after + 1)
            else:
                print(f"❌ HTTP {e.status} [{label}]: {e.text}")
                return None
        except discord.Forbidden:
            print(f"🚫 Forbidden [{label}]")
            return None
        except Exception as e:
            print(f"⚠️ [{label}]: {type(e).__name__}: {e}")
            return None
    print(f"❌ หมด retry [{label}]")
    return None

# ============================================================
#  !clone
# ============================================================
@bot.command(name="clone")
@commands.has_permissions(administrator=True)
async def clone_server(ctx, source_guild_id: int = None):
    dest_guild = ctx.guild
    author = ctx.author  # เก็บไว้ DM ทีหลัง

    # หา source guild
    if source_guild_id is None:
        source_guild = ctx.guild
    else:
        source_guild = bot.get_guild(source_guild_id)
        if source_guild is None:
            await ctx.send("❌ ไม่พบเซิร์ฟต้นทาง — บอทต้องอยู่ในเซิร์ฟนั้นด้วย")
            return

    total_src_cats = len(source_guild.categories)
    total_src_ch   = len([c for c in source_guild.channels
                          if not isinstance(c, discord.CategoryChannel)])

    # แจ้งก่อนเริ่ม
    try:
        await ctx.send(
            f"⏳ เริ่ม Clone จาก **{source_guild.name}** → **{dest_guild.name}**\n"
            f"📋 ต้นทางมี `{total_src_cats}` categories, `{total_src_ch}` channels\n"
            "⚠️ ห้องทั้งหมดจะถูกลบและสร้างใหม่ — ผลจะส่งผ่าน DM ครับ"
        )
    except Exception:
        pass  # ถ้าส่งไม่ได้ก็ข้ามไป

    print(f"🚀 เริ่ม clone: {source_guild.name} → {dest_guild.name}")

    # ── 1. ลบห้องเดิมทั้งหมด ──
    print("── Step 1: ลบห้องเดิม ──")
    for ch in list(dest_guild.channels):
        print(f"  ลบ: #{ch.name}")
        await safe_run(f"delete {ch.name}", ch.delete())

    print("── Step 1 เสร็จ ──")

    # ── 2. Clone Roles ──
    print("── Step 2: Clone Roles ──")
    role_map = {}
    sorted_roles = sorted(
        [r for r in source_guild.roles if r.name != "@everyone"],
        key=lambda r: r.position
    )
    for role in sorted_roles:
        print(f"  role: {role.name}")
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
    print(f"── Step 2 เสร็จ {len(role_map)} roles ──")

    # ── 3. Clone Categories + Channels ──
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
        print(f"  (no cat) #{ch.name}")
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
        if result: created_ch += 1
        else: failed_ch += 1

    # categories
    sorted_categories = sorted(source_guild.categories, key=lambda c: c.position)
    for cat in sorted_categories:
        print(f"  category: {cat.name}")
        new_cat = await safe_run(
            f"category {cat.name}",
            dest_guild.create_category(
                name=cat.name, overwrites=build_overwrites(cat)
            )
        )
        if new_cat is None:
            print(f"  ❌ สร้าง category ล้มเหลว: {cat.name}")
            failed_ch += len(cat.channels)
            continue

        for ch in sorted(cat.channels, key=lambda c: c.position):
            ow = build_overwrites(ch)
            print(f"    #{ch.name} [{type(ch).__name__}]")
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
            if result: created_ch += 1
            else: failed_ch += 1

    print(f"── Step 3 เสร็จ: {created_ch} OK, {failed_ch} FAIL ──")

    # ── 4. DM แจ้งผล ──
    status = "✅" if failed_ch == 0 else "⚠️"
    summary = (
        f"{status} **Clone เสร็จแล้ว!**\n"
        f"เซิร์ฟ: **{dest_guild.name}**\n"
        f"📁 Categories: `{len(sorted_categories)}`\n"
        f"💬 Channels: `{created_ch}` / `{created_ch + failed_ch}` สำเร็จ\n"
        f"🎭 Roles: `{len(role_map)}`"
    )
    if failed_ch > 0:
        summary += f"\n⚠️ ล้มเหลว `{failed_ch}` ช่อง — ดู log ใน Railway console"

    # ส่ง DM ให้คนที่สั่ง
    try:
        await author.send(summary)
        print(f"📨 DM ส่งผลให้ {author} แล้ว")
    except Exception as e:
        print(f"⚠️ ส่ง DM ไม่ได้: {e}")

    # ลองส่งใน server channel แรกที่หาได้
    try:
        for ch in dest_guild.text_channels:
            await ch.send(summary)
            break
    except Exception:
        pass


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
        await ctx.send("❌ รูปแบบผิด — ตัวอย่าง: `!clone 1234567890`")
    else:
        print(f"Error: {error}")
        await ctx.send(f"❌ Error: {error}")

bot.run(TOKEN)
