#!/usr/bin/env python3
# economy_module.py — Hoshikuzu Economy System

import os
import sqlite3
import random
import discord
from discord.ext import commands
from datetime import datetime, timedelta

DB_PATH = os.environ.get("HOSHIKUZU_ECO_DB", "economy.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER,
        guild_id INTEGER,
        money INTEGER DEFAULT 0,
        last_daily TEXT,
        last_weekly TEXT,
        PRIMARY KEY(user_id, guild_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS inventory (
        user_id INTEGER,
        guild_id INTEGER,
        item TEXT,
        amount INTEGER DEFAULT 1,
        PRIMARY KEY(user_id, guild_id, item)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS shop (
        guild_id INTEGER,
        item TEXT,
        price INTEGER,
        PRIMARY KEY(guild_id, item)
    )""")
    conn.commit()
    return conn

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_conn()

    def add_money(self, uid, gid, amount):
        c = self.db.cursor()
        c.execute("SELECT money FROM users WHERE user_id=? AND guild_id=?", (uid, gid))
        row = c.fetchone()
        if row:
            money = row[0] + amount
            c.execute("UPDATE users SET money=? WHERE user_id=? AND guild_id=?", (money, uid, gid))
        else:
            money = amount
            c.execute("INSERT INTO users VALUES (?, ?, ?, NULL, NULL)", (uid, gid, money))
        self.db.commit()
        return money

    @commands.command()
    async def balance(self, ctx, member: discord.Member=None):
        member = member or ctx.author
        c = self.db.cursor()
        c.execute("SELECT money FROM users WHERE user_id=? AND guild_id=?", (member.id, ctx.guild.id))
        row = c.fetchone()
        money = row[0] if row else 0
        await ctx.send(f"💰 {member.mention} possède **{money}** coins.")

    @commands.command()
    async def daily(self, ctx):
        uid, gid = ctx.author.id, ctx.guild.id
        c = self.db.cursor()
        now = datetime.utcnow()

        c.execute("SELECT last_daily, money FROM users WHERE user_id=? AND guild_id=?", (uid, gid))
        row = c.fetchone()

        if row:
            last_daily, money = row
            if last_daily:
                last_dt = datetime.fromisoformat(last_daily)
                if now - last_dt < timedelta(hours=24):
                    return await ctx.send("⏳ Tu as déjà récupéré ton daily !")

            reward = random.randint(200, 500)
            money += reward
            c.execute("UPDATE users SET money=?, last_daily=? WHERE user_id=? AND guild_id=?", 
                      (money, now.isoformat(), uid, gid))
        else:
            reward = random.randint(200, 500)
            c.execute("INSERT INTO users VALUES (?, ?, ?, ?, NULL)", (uid, gid, reward, now.isoformat()))

        self.db.commit()
        await ctx.send(f"🎁 Daily récupéré ! Tu gagnes **{reward}** coins.")

def setup(bot):
    bot.add_cog(Economy(bot))
