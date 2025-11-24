#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Hoshikuzu BOT — FULL SKELETON ⚡

import discord
from discord.ext import commands
import sqlite3
import random
import asyncio

TOKEN = "PUT_YOUR_TOKEN_HERE"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------
# DATABASE
# ----------------------
db = sqlite3.connect("hoshikuzu.db")
cursor = db.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS xp (user_id INTEGER, guild_id INTEGER, xp INTEGER, level INTEGER, PRIMARY KEY(user_id, guild_id))")
db.commit()

# ----------------------
# XP SYSTEM
# ----------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    cursor.execute("SELECT xp, level FROM xp WHERE user_id=? AND guild_id=?", (message.author.id, message.guild.id))
    data = cursor.fetchone()
    if data is None:
        cursor.execute("INSERT INTO xp VALUES (?, ?, ?, ?)", (message.author.id, message.guild.id, 5, 1))
        db.commit()
    else:
        xp, level = data
        xp += 5
        if xp >= level * 100:
            level += 1
            await message.channel.send(f"⭐ {message.author.mention} monte niveau {level} !")
        cursor.execute("UPDATE xp SET xp=?, level=? WHERE user_id=? AND guild_id=?", (xp, level, message.author.id, message.guild.id))
        db.commit()
    await bot.process_commands(message)

# ----------------------
# SIMPLE COMMAND
# ----------------------
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

# ----------------------
# RUN BOT
# ----------------------
bot.run(TOKEN)
