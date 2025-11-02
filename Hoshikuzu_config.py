#!/usr/bin/env python3
import os, json, threading, http.server, socketserver, traceback
import discord
from discord.ext import commands

# === Keep Alive (Render) ===
def keep_alive():
    try:
        port = int(os.environ.get("PORT", 8080))
    except Exception:
        port = 8080
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    with socketserver.TCPServer(("", port), QuietHandler) as httpd:
        print(f"[keep-alive] HTTP running on port {port}")
        httpd.serve_forever()
threading.Thread(target=keep_alive, daemon=True).start()

# === Data Management ===
DATA_FILE = "hoshikuzu_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("load_data error:", e)
    return {"config": {}, "tickets": {}}

def save_data(d):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("save_data error:", e)

data = load_data()

def get_conf(gid, key, default=None):
    return data.get("config", {}).get(str(gid), {}).get(key, default)

def set_conf(gid, key, value):
    data.setdefault("config", {}).setdefault(str(gid), {})[key] = value
    save_data(data)

def get_gconf(gid):
    return data.get("config", {}).get(str(gid), {})

# === Bot Init ===
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)
EMOJI = "<a:caarrow:1433143710094196997>"

@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")

# === Help Command ===
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🌿 Hoshikuzu — Config", color=discord.Color.green())
    e.add_field(name="Config", value="`+config` panneau interactif", inline=False)
    e.add_field(name="Liens", value="`+allowlink #channel` / `+disallowlink #channel`", inline=False)
    e.add_field(name="Vocale", value="`🔊Créer un voc` automatique", inline=False)
    e.add_field(name="Lock", value="`+lock` / `+unlock`", inline=False)
    e.add_field(name="Roles", value="`+role @user @role` / `+rolejoin @role`", inline=False)
    e.add_field(name="Tickets", value="`+ticket`", inline=False)
    await ctx.send(embed=e)

# === Commande +config ===
@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config_cmd(ctx):
    try:
        conf = get_gconf(ctx.guild.id)
        e = discord.Embed(title="⚙️ Panneau de configuration — Hoshikuzu", color=discord.Color.green())
        e.add_field(name="Logs", value=f"<#{conf.get('logs_channel')}>" if conf.get("logs_channel") else "Aucun", inline=True)
        e.add_field(name="Bienvenue", value=f"<#{conf.get('welcome_channel')}>" if conf.get("welcome_channel") else "Aucun", inline=True)
        e.add_field(name="Au revoir", value=f"<#{conf.get('leave_channel')}>" if conf.get("leave_channel") else "Aucun", inline=True)
        e.add_field(name="Invites", value=f"<#{conf.get('invites_channel')}>" if conf.get("invites_channel") else "Aucun", inline=True)
        e.add_field(name="Rolejoin", value=f"<@&{conf.get('auto_role')}>" if conf.get("auto_role") else "Aucun", inline=True)
        await ctx.send(embed=e)
    except Exception as e:
        traceback.print_exc()
        await ctx.send(f"❌ Erreur : `{type(e).__name__}` — {e}")

# === Messages de bienvenue et au revoir ===
@bot.event
async def on_member_join(member):
    guild_id = member.guild.id
    channel_id = get_conf(guild_id, "welcome_channel")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            total = member.guild.member_count
            embed = discord.Embed(
                title="🌿 Bienvenue !",
                description=f"{member.mention} a rejoint le serveur.",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Tu es le {total}ᵉ membre !")
            await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    guild_id = member.guild.id
    channel_id = get_conf(guild_id, "leave_channel")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            total = member.guild.member_count
            embed = discord.Embed(
                title="👋 Au revoir !",
                description=f"{member.name} a quitté le serveur.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Il reste {total} membres.")
            await channel.send(embed=embed)

# === Salon vocal temporaire ===
VOC_TRIGGER_NAME = "🔊Créer un voc"

@bot.event
async def on_voice_state_update(member, before, after):
    try:
        if after.channel and after.channel.name == VOC_TRIGGER_NAME:
            guild = member.guild
            category = after.channel.category
            temp_channel = await guild.create_voice_channel(
                name=f"🎙️ {member.name}",
                category=category,
                user_limit=1
            )
            await member.move_to(temp_channel)

        if before.channel and before.channel != after.channel:
            channel = before.channel
            if channel.name.startswith("🎙️") and len(channel.members) == 0:
                await channel.delete()
    except Exception as e:
        print(f"Erreur voc temporaire : {e}")

# === Run sécurisé pour Render ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN or TOKEN.strip() == "":
    print("❌ Le token Discord est vide ou non défini. Vérifie les variables d’environnement sur Render.")
    while True:
        pass
else:
    try:
        print("✅ Lancement du bot avec le token depuis Render.")
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Erreur lors du lancement du bot : {e}")
        while True:
            pass

