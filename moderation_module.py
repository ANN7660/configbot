#!/usr/bin/env python3
# moderation_module.py — Full moderation system for Hoshikuzu

import discord
from discord.ext import commands
import sqlite3
import asyncio
import re
from datetime import datetime

DB = "moderation.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS warns (
        user_id INTEGER,
        guild_id INTEGER,
        moderator_id INTEGER,
        reason TEXT,
        date TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS blacklist (
        user_id INTEGER,
        guild_id INTEGER,
        PRIMARY KEY(user_id, guild_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS logs (
        guild_id INTEGER PRIMARY KEY,
        channel_id INTEGER
    )""")
    conn.commit()
    return conn

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = init_db()

    def log(self, guild, text):
        c = self.conn.cursor()
        c.execute("SELECT channel_id FROM logs WHERE guild_id=?", (guild.id,))
        row = c.fetchone()
        if row:
            chan = guild.get_channel(row[0])
            if chan:
                asyncio.create_task(chan.send(text))

    # =======================
    # BAN / KICK / MUTE
    # =======================
    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="Aucune raison"):
        await member.ban(reason=reason)
        await ctx.send(f"🔨 {member} banni : {reason}")
        self.log(ctx.guild, f"🔨 Ban: {member} — {reason}")

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="Aucune raison"):
        await member.kick(reason=reason)
        await ctx.send(f"👢 {member} expulsé : {reason}")
        self.log(ctx.guild, f"👢 Kick: {member} — {reason}")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, minutes: int, *, reason="Aucune raison"):
        duration = discord.Timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        await ctx.send(f"🔇 {member} mute {minutes} min : {reason}")
        self.log(ctx.guild, f"🔇 Mute: {member} — {minutes} min — {reason}")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member):
        await member.timeout(None)
        await ctx.send(f"🔊 {member} unmute.")
        self.log(ctx.guild, f"🔊 Unmute: {member}")

    # =======================
    # WARN SYSTEM
    # =======================
    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason="Aucune raison"):
        c = self.conn.cursor()
        c.execute("INSERT INTO warns VALUES (?,?,?,?,?)", (
            member.id,
            ctx.guild.id,
            ctx.author.id,
            reason,
            datetime.utcnow().isoformat()
        ))
        self.conn.commit()
        await ctx.send(f"⚠️ Warn ajouté pour {member} : {reason}")
        self.log(ctx.guild, f"⚠️ Warn: {member} — {reason}")

    @commands.command()
    async def warns(self, ctx, member: discord.Member=None):
        member = member or ctx.author
        c = self.conn.cursor()
        c.execute("SELECT moderator_id, reason, date FROM warns WHERE user_id=? AND guild_id=?",
                  (member.id, ctx.guild.id))
        rows = c.fetchall()
        if not rows:
            return await ctx.send(f"{member.mention} n'a aucun warn.")
        msg = "\n".join([f"- {reason} (par <@{mod}> — {date})" for mod, reason, date in rows])
        await ctx.send(f"⚠️ Warns pour {member.mention} :\n{msg}")

    # =======================
    # ANTISPAM / BADWORDS
    # =======================
    badwords = ["fuck", "pute", "tg", "fdp", "connard"]

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot: 
            return

        # Anti badwords
        content = msg.content.lower()
        if any(bad in content for bad in self.badwords):
            try:
                await msg.delete()
            except:
                pass
            await msg.channel.send(f"🚫 {msg.author.mention} ton message contenait un mot interdit.")
            return

        # Anti spam (max 5 msgs en 4 secondes)
        if not hasattr(self, "msg_cache"):
            self.msg_cache = {}

        uid = msg.author.id
        now = datetime.utcnow().timestamp()

        if uid not in self.msg_cache:
            self.msg_cache[uid] = []
        self.msg_cache[uid] = [t for t in self.msg_cache[uid] if now - t < 4]
        self.msg_cache[uid].append(now)

        if len(self.msg_cache[uid]) > 5:
            try:
                await msg.author.timeout(discord.Timedelta(minutes=10), reason="Spam")
            except:
                pass
            await msg.channel.send(f"⚠️ {msg.author.mention} mute 10min pour spam.")
            self.log(msg.guild, f"⚠️ Spam mute: {msg.author}")
            return

    # =======================
    # LOG CONFIG
    # =======================
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setlogs(self, ctx, channel: discord.TextChannel):
        c = self.conn.cursor()
        c.execute("REPLACE INTO logs VALUES (?,?)", (ctx.guild.id, channel.id))
        self.conn.commit()
        await ctx.send(f"📝 Logs envoyés dans : {channel.mention}")

def setup(bot):
    bot.add_cog(Moderation(bot))
