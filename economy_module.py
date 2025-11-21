#!/usr/bin/env python3
# economy_module.py — Hoshikuzu Economy System

import discord
from discord.ext import commands
import sqlite3
import random
import asyncio
from datetime import datetime, timedelta
import os

DB = "economy.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER,
        guild_id INTEGER,
        money INTEGER DEFAULT 0,
        daily_ts INTEGER DEFAULT 0,
        weekly_ts INTEGER DEFAULT 0,
        PRIMARY KEY(user_id, guild_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS inventory (
        user_id INTEGER,
        guild_id INTEGER,
        item TEXT,
        qty INTEGER DEFAULT 1,
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
        self.conn = init_db()

    def add_money(self, uid, gid, amount):
        c = self.conn.cursor()
        c.execute("SELECT money FROM users WHERE user_id=? AND guild_id=?", (uid, gid))
        row = c.fetchone()
        if row is None:
            c.execute("INSERT INTO users(user_id, guild_id, money) VALUES(?,?,?)", (uid, gid, amount))
        else:
            new = row[0] + amount
            c.execute("UPDATE users SET money=? WHERE user_id=? AND guild_id=?", (new, uid, gid))
        self.conn.commit()

    @commands.command()
    async def balance(self, ctx, member: discord.Member=None):
        member = member or ctx.author
        c = self.conn.cursor()
        c.execute("SELECT money FROM users WHERE user_id=? AND guild_id=?", (member.id, ctx.guild.id))
        row = c.fetchone()
        money = row[0] if row else 0
        await ctx.send(f"💰 {member.mention} possède **{money}** coins.")

    @commands.command()
    async def give(self, ctx, member: discord.Member, amount: int):
        if amount <= 0:
            return await ctx.send("Montant invalide.")
        c = self.conn.cursor()
        c.execute("SELECT money FROM users WHERE user_id=? AND guild_id=?", (ctx.author.id, ctx.guild.id))
        row = c.fetchone()
        if not row or row[0] < amount:
            return await ctx.send("Tu n'as pas assez de coins.")
        # remove from sender
        c.execute("UPDATE users SET money=? WHERE user_id=? AND guild_id=?", (row[0]-amount, ctx.author.id, ctx.guild.id))
        # add to recipient
        self.add_money(member.id, ctx.guild.id, amount)
        await ctx.send(f"🔁 {ctx.author.mention} a donné **{amount}** coins à {member.mention}")

    @commands.command()
    async def daily(self, ctx):
        uid = ctx.author.id
        gid = ctx.guild.id
        c = self.conn.cursor()
        c.execute("SELECT daily_ts FROM users WHERE user_id=? AND guild_id=?", (uid, gid))
        row = c.fetchone()
        now = int(datetime.utcnow().timestamp())
        if row and now - row[0] < 86400:
            return await ctx.send("❌ Daily déjà récupéré aujourd'hui.")
        reward = random.randint(200, 350)
        self.add_money(uid, gid, reward)
        c.execute("UPDATE users SET daily_ts=? WHERE user_id=? AND guild_id=?", (now, uid, gid))
        self.conn.commit()
        await ctx.send(f"🎁 Daily claim ! Tu gagnes **{reward}** coins.")

def setup(bot):
    bot.add_cog(Economy(bot))
