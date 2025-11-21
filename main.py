import discord
from discord.ext import commands
import os

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Charger les extensions
EXTENSIONS = [
    "xp_module",
    "economy",
    "moderation",
    "music",
    "tickets",
    "reaction_roles",
    "verification"
]

for ext in EXTENSIONS:
    try:
        bot.load_extension(ext)
        print(f"Loaded extension: {ext}")
    except Exception as e:
        print(f"Failed to load {ext}: {e}")

TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
