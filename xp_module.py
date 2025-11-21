#!/usr/bin/env python3
# xp_module.py
# Hoshikuzu — XP Module (standalone extension)
# Features:
# - XP gain on messages (cooldown)
# - Level up announcements
# - Rank command (text + image rankcard via Pillow)
# - Leaderboard
# - Manual XP boost command (admins)
# - Event XP grant (admins)
# - Badges system (award/remove/list)
#
# Requirements:
# pip install py-cord==2.4.1 Pillow python-dotenv
#
# Usage:
# 1) Put this file in your bot project
# 2) In your main bot: bot.load_extension("xp_module")  OR copy the Cog class content into your bot
# 3) Set environment variable DISCORD_TOKEN and run your bot
#
import os
import sqlite3
import random
import time
from datetime import datetime, timedelta
from io import BytesIO

import discord
from discord.ext import commands, tasks

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None

DB_PATH = os.environ.get("HOSHIKUZU_XP_DB", "xp_module.db")
MSG_COOLDOWN = 10          # seconds between xp gains per user
BASE_XP_MIN = 8
BASE_XP_MAX = 15
LEVEL_MULTIPLIER = 100     # xp needed = level * LEVEL_MULTIPLIER

# --- Database helpers ---
def init_db(conn: sqlite3.Connection):
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, last_gain INTEGER DEFAULT 0, PRIMARY KEY(user_id, guild_id))")
    c.execute("CREATE TABLE IF NOT EXISTS badges (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, badge TEXT NOT NULL, awarded_by INTEGER, awarded_at TEXT, PRIMARY KEY(user_id, guild_id, badge))")
    c.execute("CREATE TABLE IF NOT EXISTS boosts (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, multiplier REAL DEFAULT 1.0, expires_at TEXT, PRIMARY KEY(user_id, guild_id))")
    conn.commit()

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    init_db(conn)
    return conn

# --- Utility functions ---
def xp_needed_for(level: int) -> int:
    return level * LEVEL_MULTIPLIER

def now_ts() -> int:
    return int(time.time())

# --- Cog Implementation ---
class XPModule(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn = get_conn()
        self._cleanup_task.start()

    def cog_unload(self):
        self._cleanup_task.cancel()
        try:
            self.conn.close()
        except Exception:
            pass

    # background cleanup: clear expired boosts every minute
    @tasks.loop(minutes=1.0)
    async def _cleanup_task(self):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM boosts WHERE expires_at IS NOT NULL AND expires_at < ?", (datetime.utcnow().isoformat(),))
        self.conn.commit()

    # --------- XP gain on message ---------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        uid = message.author.id
        gid = message.guild.id
        cur = self.conn.cursor()
        cur.execute("SELECT xp, level, last_gain FROM users WHERE user_id=? AND guild_id=?", (uid, gid))
        row = cur.fetchone()
        row = row or (0, 1, 0)
        xp, level, last_gain = row

        # cooldown per user
        now = now_ts()
        if now - last_gain < MSG_COOLDOWN:
            return

        # base gain plus random
        base_gain = random.randint(BASE_XP_MIN, BASE_XP_MAX)

        # check for boost multiplier
        cur.execute("SELECT multiplier, expires_at FROM boosts WHERE user_id=? AND guild_id=?", (uid, gid))
        boost_row = cur.fetchone()
        multiplier = 1.0
        if boost_row:
            mult, expires = boost_row
            if expires:
                try:
                    exp_dt = datetime.fromisoformat(expires)
                    if exp_dt < datetime.utcnow():
                        # expired; remove
                        cur.execute("DELETE FROM boosts WHERE user_id=? AND guild_id=?", (uid, gid))
                        self.conn.commit()
                    else:
                        multiplier = float(mult)
                except Exception:
                    multiplier = float(mult)
            else:
                multiplier = float(mult)

        gain = int(base_gain * multiplier)
        xp += gain
        cur.execute("REPLACE INTO users(user_id,guild_id,xp,level,last_gain) VALUES(?,?,?,?,?)", (uid, gid, xp, level, now))
        self.conn.commit()

        # level up check
        needed = xp_needed_for(level)
        if xp >= needed:
            xp -= needed
            level += 1
            cur.execute("UPDATE users SET xp=?, level=? WHERE user_id=? AND guild_id=?", (xp, level, uid, gid))
            self.conn.commit()
            # announcement
            try:
                channel = message.channel
                await channel.send(f"🎉 Félicitations {message.author.mention} ! Tu es monté niveau **{level}** 🎉")
            except Exception:
                pass

    # --------- Commands ---------
    @commands.command(name="xp", help="Voir ton xp et niveau")
    async def cmd_xp(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        cur = self.conn.cursor()
        cur.execute("SELECT xp, level FROM users WHERE user_id=? AND guild_id=?", (member.id, ctx.guild.id))
        row = cur.fetchone() or (0, 1)
        xp, level = row
        needed = xp_needed_for(level)
        await ctx.send(f"📊 {member.mention} — Niveau **{level}** — XP: **{xp}/{needed}**")

    @commands.command(name="rank", help="Affiche la rank card (image) ou info textuelle")
    async def cmd_rank(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        cur = self.conn.cursor()
        cur.execute("SELECT xp, level FROM users WHERE user_id=? AND guild_id=?", (member.id, ctx.guild.id))
        row = cur.fetchone() or (0, 1)
        xp, level = row
        needed = xp_needed_for(level)
        pct = xp / needed if needed else 0.0

        # if PIL available, generate a nice image rank card
        if Image:
            try:
                W, H = 900, 240
                im = Image.new("RGBA", (W, H), (24, 24, 24, 255))
                draw = ImageDraw.Draw(im)

                # bar background
                draw.rectangle((40, 160, W-40, 200), fill=(45,45,45))
                draw.rectangle((40, 160, 40 + int((W-80)*pct), 200), fill=(120, 80, 200))

                # avatar
                avatar_asset = member.display_avatar.replace(size=128)
                av_bytes = await avatar_asset.read()
                av = Image.open(BytesIO(av_bytes)).convert("RGBA").resize((128,128))
                im.paste(av, (40, 24), av)

                # fonts
                try:
                    f_large = ImageFont.truetype("arial.ttf", 28)
                    f_small = ImageFont.truetype("arial.ttf", 18)
                except Exception:
                    f_large = ImageFont.load_default()
                    f_small = ImageFont.load_default()

                # text
                draw.text((180, 40), f"{member.display_name}", font=f_large, fill=(255,255,255))
                draw.text((180, 78), f"Niveau {level} — {xp}/{needed} XP", font=f_small, fill=(200,200,200))

                # badges (fetch up to 4)
                cur.execute("SELECT badge FROM badges WHERE user_id=? AND guild_id=? LIMIT 4", (member.id, ctx.guild.id))
                badges = [r[0] for r in cur.fetchall()]
                bx = W - 40 - (len(badges) * 36)
                for i, b in enumerate(badges):
                    draw.rectangle((bx + i*36, 40, bx + i*36 + 28, 68), fill=(255,215,0))
                    draw.text((bx + i*36+2, 44), b[:2].upper(), font=f_small, fill=(0,0,0))

                # send image
                bio = BytesIO()
                im.save(bio, "PNG")
                bio.seek(0)
                await ctx.send(file=discord.File(bio, "rank.png"))
                return
            except Exception as e:
                # fallback to text on any error
                await ctx.send(f"{member.mention} — Niveau **{level}** — XP: **{xp}/{needed}** (image failed: {e})")
                return

        # fallback text
        await ctx.send(f"{member.mention} — Niveau **{level}** — XP: **{xp}/{needed}**")

    @commands.command(name="leaderboard", help="Top 10 des joueurs par level puis xp")
    async def cmd_leaderboard(self, ctx: commands.Context):
        cur = self.conn.cursor()
        cur.execute("SELECT user_id, level, xp FROM users WHERE guild_id=? ORDER BY level DESC, xp DESC LIMIT 10", (ctx.guild.id,))
        rows = cur.fetchall()
        if not rows:
            return await ctx.send("Aucun utilisateur avec de l'XP dans ce serveur.")
        lines = []
        for i, (user_id, level, xp) in enumerate(rows, start=1):
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            lines.append(f"{i}. **{name}** — Niveau {level} — XP {xp}")
        await ctx.send("🏆 Leaderboard:
" + "
".join(lines))

    # Admin: grant XP to a user (event / correction)
    @commands.command(name="grantxp", help="(Admin) Ajoute de l'XP à un utilisateur")
    @commands.has_permissions(administrator=True)
    async def cmd_grantxp(self, ctx: commands.Context, member: discord.Member, amount: int):
        cur = self.conn.cursor()
        cur.execute("SELECT xp, level FROM users WHERE user_id=? AND guild_id=?", (member.id, ctx.guild.id))
        row = cur.fetchone() or (0,1)
        xp, level = row
        xp += amount
        # handle level ups possibly multiple
        leveled = 0
        while xp >= xp_needed_for(level):
            xp -= xp_needed_for(level)
            level += 1
            leveled += 1
        cur.execute("REPLACE INTO users(user_id,guild_id,xp,level,last_gain) VALUES(?,?,?,?,?)", (member.id, ctx.guild.id, xp, level, now_ts()))
        self.conn.commit()
        add_text = f" et monté de {leveled} niveaux" if leveled else ""
        await ctx.send(f"✅ Ajouté {amount} XP à {member.mention}{add_text}")

    # Admin: set boost multiplier for a user for a duration (minutes)
    @commands.command(name="boostxp", help="(Admin) Boost XP pour un utilisateur : minutes et multiplicateur")
    @commands.has_permissions(administrator=True)
    async def cmd_boostxp(self, ctx: commands.Context, member: discord.Member, minutes: int, multiplier: float = 2.0):
        expires = (datetime.utcnow() + timedelta(minutes=minutes)).isoformat()
        cur = self.conn.cursor()
        cur.execute("REPLACE INTO boosts(user_id,guild_id,multiplier,expires_at) VALUES(?,?,?,?)", (member.id, ctx.guild.id, multiplier, expires))
        self.conn.commit()
        await ctx.send(f"🚀 Boost x{multiplier} appliqué à {member.mention} pendant {minutes} minutes.")

    # Badges: award/remove/list
    @commands.command(name="awardbadge", help="(Admin) Attribue un badge à un utilisateur")
    @commands.has_permissions(manage_guild=True)
    async def cmd_awardbadge(self, ctx: commands.Context, member: discord.Member, badge: str):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO badges(user_id,guild_id,badge,awarded_by,awarded_at) VALUES(?,?,?,?,?)",
                    (member.id, ctx.guild.id, badge, ctx.author.id, datetime.utcnow().isoformat()))
        self.conn.commit()
        await ctx.send(f"🏅 Badge '{badge}' attribué à {member.mention}.")

    @commands.command(name="removebadge", help="(Admin) Retire un badge d'un utilisateur")
    @commands.has_permissions(manage_guild=True)
    async def cmd_removebadge(self, ctx: commands.Context, member: discord.Member, badge: str):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM badges WHERE user_id=? AND guild_id=? AND badge=?", (member.id, ctx.guild.id, badge))
        self.conn.commit()
        await ctx.send(f"🗑️ Badge '{badge}' retiré à {member.mention}.")

    @commands.command(name="listbadges", help="Liste les badges d'un utilisateur")
    async def cmd_listbadges(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        cur = self.conn.cursor()
        cur.execute("SELECT badge, awarded_by, awarded_at FROM badges WHERE user_id=? AND guild_id=?", (member.id, ctx.guild.id))
        rows = cur.fetchall()
        if not rows:
            return await ctx.send(f"{member.mention} n'a aucun badge.")
        lines = [f"- {r[0]} (by <@{r[1]}> on {r[2]})" for r in rows]
        await ctx.send(f"🏅 Badges for {member.mention}:
" + "
".join(lines))

# Cog setup
def setup(bot):
    bot.add_cog(XPModule(bot))

# If run directly for testing (creates a small bot)
if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        print("Set DISCORD_TOKEN in environment to test standalone. This file is intended as a Cog/extension.")
    else:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        bot = commands.Bot(command_prefix="+", intents=intents)
        bot.load_extension("xp_module")
        bot.run(TOKEN)
