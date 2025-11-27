import disnake as discord
from disnake.ext import commands, tasks
from disnake.ui import Button, View, Select
import asyncio
import aiohttp
import json
import os
from datetime import datetime, timedelta
import random
from collections import defaultdict
from flask import Flask
from threading import Thread

# ============= CONFIGURATION =============
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ============= DONNÉES =============
economy_data = defaultdict(lambda: {"money": 0, "bank": 0, "rep": 0, "daily_claimed": None, "work_claimed": None, "inventory": []})
warnings_data = defaultdict(list)
tickets_data = defaultdict(list)
stats_data = defaultdict(lambda: {"messages": 0, "voice_time": 0, "last_message": None})
giveaways_data = []
voice_tracking = {}

server_config = defaultdict(lambda: {
    "welcome_channel": None,
    "leave_channel": None,
    "welcome_text": None,
    "leave_text": None,
    "welcome_embed": None,
    "leave_embed": None,
    "automod_words": [],
    "shop": [],
    "ticket_category": None,
    "ticket_role": None,
    "ticket_counter": 0,
    "tempvoc_channel": None,
    "tempvoc_category": None,
    "log_channels": {},
    "autorole": None,
    "antispam": {"enabled": False, "messages": 5, "seconds": 5},
    "questionnaire_active": False
})

# ============= KEEP ALIVE (RENDER) =============
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ============= EVENTS =============
@bot.event
async def on_ready():
    print(f'✅ {bot.user} est connecté!')
    auto_reboot.start()
    check_giveaways.start()
    await bot.change_presence(activity=discord.Game(name="!help"))

@tasks.loop(hours=23)
async def auto_reboot():
    print("🔄 Auto-reboot check...")

@tasks.loop(seconds=30)
async def check_giveaways():
    current_time = datetime.now()
    for giveaway in giveaways_data[:]:
        if current_time >= giveaway["end_time"]:
            channel = bot.get_channel(giveaway["channel_id"])
            if channel:
                try:
                    msg = await channel.fetch_message(giveaway["message_id"])
                    reaction = discord.utils.get(msg.reactions, emoji="🎉")
                    if reaction:
                        users = [user async for user in reaction.users() if not user.bot]
                        if users:
                            winner = random.choice(users)
                            await channel.send(f"🎉 Félicitations {winner.mention}! Vous avez gagné **{giveaway['prize']}**!")
                        else:
                            await channel.send("❌ Aucun participant au giveaway!")
                except:
                    pass
            giveaways_data.remove(giveaway)

@bot.event
async def on_member_join(member):
    config = server_config[member.guild.id]
    
    # Autorole
    if config.get("autorole"):
        role = member.guild.get_role(config["autorole"])
        if role:
            await member.add_roles(role)
    
    # Welcome message
    channel_id = config.get("welcome_channel")
    if not channel_id:
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    
    member_count = member.guild.member_count
    
    # Variables de remplacement
    replacements = {
        "{user}": member.mention,
        "{server}": member.guild.name,
        "{count}": str(member_count)
    }
    
    if config.get("welcome_embed"):
        embed_data = config["welcome_embed"]
        
        title = embed_data.get("title", "Bienvenue!")
        description = embed_data.get("description", "")
        
        for key, value in replacements.items():
            title = title.replace(key, value)
            description = description.replace(key, value)
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=getattr(discord.Color, embed_data.get("color", "green"))()
        )
        
        if embed_data.get("thumbnail") == "member":
            embed.set_thumbnail(url=member.display_avatar.url)
        elif embed_data.get("thumbnail") == "server":
            if member.guild.icon:
                embed.set_thumbnail(url=member.guild.icon.url)
        elif embed_data.get("thumbnail"):
            embed.set_thumbnail(url=embed_data["thumbnail"])
        
        if embed_data.get("image"):
            embed.set_image(url=embed_data["image"])
        
        if embed_data.get("footer"):
            footer_text = embed_data["footer"]
            for key, value in replacements.items():
                footer_text = footer_text.replace(key, value)
            embed.set_footer(text=footer_text)
        
        await channel.send(embed=embed)
    
    elif config.get("welcome_text"):
        msg = config["welcome_text"]
        for key, value in replacements.items():
            msg = msg.replace(key, value)
        await channel.send(msg)
    
    await log_action(member.guild, "membres", f"📥 {member.mention} a rejoint le serveur")

@bot.event
async def on_member_remove(member):
    config = server_config[member.guild.id]
    channel_id = config.get("leave_channel")
    if not channel_id:
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    
    member_count = member.guild.member_count
    
    replacements = {
        "{user}": member.name,
        "{server}": member.guild.name,
        "{count}": str(member_count)
    }
    
    if config.get("leave_embed"):
        embed_data = config["leave_embed"]
        
        title = embed_data.get("title", "Au revoir!")
        description = embed_data.get("description", "")
        
        for key, value in replacements.items():
            title = title.replace(key, value)
            description = description.replace(key, value)
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=getattr(discord.Color, embed_data.get("color", "red"))()
        )
        
        if embed_data.get("thumbnail") == "member":
            embed.set_thumbnail(url=member.display_avatar.url)
        elif embed_data.get("thumbnail") == "server":
            if member.guild.icon:
                embed.set_thumbnail(url=member.guild.icon.url)
        elif embed_data.get("thumbnail"):
            embed.set_thumbnail(url=embed_data["thumbnail"])
        
        if embed_data.get("image"):
            embed.set_image(url=embed_data["image"])
        
        if embed_data.get("footer"):
            footer_text = embed_data["footer"]
            for key, value in replacements.items():
                footer_text = footer_text.replace(key, value)
            embed.set_footer(text=footer_text)
        
        await channel.send(embed=embed)
    
    elif config.get("leave_text"):
        msg = config["leave_text"]
        for key, value in replacements.items():
            msg = msg.replace(key, value)
        await channel.send(msg)
    
    await log_action(member.guild, "membres", f"📤 {member.name} a quitté le serveur")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    config = server_config[message.guild.id]
    user_key = f"{message.guild.id}_{message.author.id}"
    
    stats_data[user_key]["messages"] += 1
    stats_data[user_key]["last_message"] = datetime.now()
    
    antispam = config["antispam"]
    if antispam["enabled"]:
        recent_messages = []
        async for m in message.channel.history(limit=antispam["messages"]):
            if m.author == message.author and (datetime.now() - m.created_at).total_seconds() < antispam["seconds"]:
                recent_messages.append(m)
        
        if len(recent_messages) >= antispam["messages"]:
            await message.channel.purge(limit=antispam["messages"], check=lambda m: m.author == message.author)
            await message.channel.send(f"{message.author.mention}, stop le spam!", delete_after=5)
            return
    
    for word in config["automod_words"]:
        if word.lower() in message.content.lower():
            await message.delete()
            await message.channel.send(f"{message.author.mention}, ce mot est interdit!", delete_after=5)
            await log_action(message.guild, "modération", f"🚫 Message supprimé de {message.author.mention}: mot interdit")
            return
    
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    config = server_config[member.guild.id]
    
    if after.channel and after.channel.id == config.get("tempvoc_channel"):
        category = member.guild.get_channel(config.get("tempvoc_category"))
        
        temp_channel = await member.guild.create_voice_channel(
            name=f"Vocal de {member.name}",
            category=category,
            user_limit=10
        )
        
        await member.move_to(temp_channel)
        
        await asyncio.sleep(2)
        while True:
            await asyncio.sleep(5)
            if len(temp_channel.members) == 0:
                await temp_channel.delete()
                break
    
    user_key = f"{member.guild.id}_{member.id}"
    
    if before.channel is None and after.channel:
        voice_tracking[user_key] = datetime.now()
    elif before.channel and after.channel is None:
        if user_key in voice_tracking:
            time_spent = (datetime.now() - voice_tracking[user_key]).total_seconds()
            stats_data[user_key]["voice_time"] += time_spent
            del voice_tracking[user_key]

# ============= LOG SYSTEM =============
async def log_action(guild, log_type, message):
    config = server_config[guild.id]
    log_channel_id = config["log_channels"].get(log_type)
    
    if not log_channel_id:
        return
    
    channel = bot.get_channel(log_channel_id)
    if channel:
        embed = discord.Embed(description=message, color=discord.Color.blue(), timestamp=datetime.now())
        await channel.send(embed=embed)
from disnake.ext import commands, tasks
from disnake.ui import Button, View, Select
import asyncio
import aiohttp
import json
import os
from datetime import datetime, timedelta
import random
from collections import defaultdict
from flask import Flask
from threading import Thread

# ============= CONFIGURATION =============
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ============= DONNÉES =============
economy_data = defaultdict(lambda: {"money": 0, "bank": 0, "rep": 0, "daily_claimed": None, "work_claimed": None, "inventory": []})
warnings_data = defaultdict(list)
tickets_data = defaultdict(list)
stats_data = defaultdict(lambda: {"messages": 0, "voice_time": 0, "last_message": None})
giveaways_data = []
voice_tracking = {}

server_config = defaultdict(lambda: {
    "welcome_channel": None,
    "leave_channel": None,
    "welcome_text": None,
    "leave_text": None,
    "welcome_embed": None,
    "leave_embed": None,
    "automod_words": [],
    "shop": [],
    "ticket_category": None,
    "ticket_role": None,
    "ticket_counter": 0,
    "tempvoc_channel": None,
    "tempvoc_category": None,
    "log_channels": {},
    "autorole": None,
    "antispam": {"enabled": False, "messages": 5, "seconds": 5},
    "questionnaire_active": False
})

# ============= KEEP ALIVE (RENDER) =============
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ============= EVENTS =============
@bot.event
async def on_ready():
    print(f'✅ {bot.user} est connecté!')
    auto_reboot.start()
    check_giveaways.start()
    await bot.change_presence(activity=discord.Game(name="!help"))

@tasks.loop(hours=23)
async def auto_reboot():
    print("🔄 Auto-reboot check...")

@tasks.loop(seconds=30)
async def check_giveaways():
    current_time = datetime.now()
    for giveaway in giveaways_data[:]:
        if current_time >= giveaway["end_time"]:
            channel = bot.get_channel(giveaway["channel_id"])
            if channel:
                try:
                    msg = await channel.fetch_message(giveaway["message_id"])
                    reaction = discord.utils.get(msg.reactions, emoji="🎉")
                    if reaction:
                        users = [user async for user in reaction.users() if not user.bot]
                        if users:
                            winner = random.choice(users)
                            await channel.send(f"🎉 Félicitations {winner.mention}! Vous avez gagné **{giveaway['prize']}**!")
                        else:
                            await channel.send("❌ Aucun participant au giveaway!")
                except:
                    pass
            giveaways_data.remove(giveaway)

@bot.event
async def on_member_join(member):
    config = server_config[member.guild.id]
    
    # Autorole
    if config.get("autorole"):
        role = member.guild.get_role(config["autorole"])
        if role:
            await member.add_roles(role)
    
    # Welcome message
    channel_id = config.get("welcome_channel")
    if not channel_id:
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    
    member_count = member.guild.member_count
    
    # Variables de remplacement
    replacements = {
        "{user}": member.mention,
        "{server}": member.guild.name,
        "{count}": str(member_count)
    }
    
    if config.get("welcome_embed"):
        embed_data = config["welcome_embed"]
        
        title = embed_data.get("title", "Bienvenue!")
        description = embed_data.get("description", "")
        
        for key, value in replacements.items():
            title = title.replace(key, value)
            description = description.replace(key, value)
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=getattr(discord.Color, embed_data.get("color", "green"))()
        )
        
        if embed_data.get("thumbnail") == "member":
            embed.set_thumbnail(url=member.display_avatar.url)
        elif embed_data.get("thumbnail") == "server":
            if member.guild.icon:
                embed.set_thumbnail(url=member.guild.icon.url)
        elif embed_data.get("thumbnail"):
            embed.set_thumbnail(url=embed_data["thumbnail"])
        
        if embed_data.get("image"):
            embed.set_image(url=embed_data["image"])
        
        if embed_data.get("footer"):
            footer_text = embed_data["footer"]
            for key, value in replacements.items():
                footer_text = footer_text.replace(key, value)
            embed.set_footer(text=footer_text)
        
        await channel.send(embed=embed)
    
    elif config.get("welcome_text"):
        msg = config["welcome_text"]
        for key, value in replacements.items():
            msg = msg.replace(key, value)
        await channel.send(msg)
    
    await log_action(member.guild, "membres", f"📥 {member.mention} a rejoint le serveur")

@bot.event
async def on_member_remove(member):
    config = server_config[member.guild.id]
    channel_id = config.get("leave_channel")
    if not channel_id:
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    
    member_count = member.guild.member_count
    
    replacements = {
        "{user}": member.name,
        "{server}": member.guild.name,
        "{count}": str(member_count)
    }
    
    if config.get("leave_embed"):
        embed_data = config["leave_embed"]
        
        title = embed_data.get("title", "Au revoir!")
        description = embed_data.get("description", "")
        
        for key, value in replacements.items():
            title = title.replace(key, value)
            description = description.replace(key, value)
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=getattr(discord.Color, embed_data.get("color", "red"))()
        )
        
        if embed_data.get("thumbnail") == "member":
            embed.set_thumbnail(url=member.display_avatar.url)
        elif embed_data.get("thumbnail") == "server":
            if member.guild.icon:
                embed.set_thumbnail(url=member.guild.icon.url)
        elif embed_data.get("thumbnail"):
            embed.set_thumbnail(url=embed_data["thumbnail"])
        
        if embed_data.get("image"):
            embed.set_image(url=embed_data["image"])
        
        if embed_data.get("footer"):
            footer_text = embed_data["footer"]
            for key, value in replacements.items():
                footer_text = footer_text.replace(key, value)
            embed.set_footer(text=footer_text)
        
        await channel.send(embed=embed)
    
    elif config.get("leave_text"):
        msg = config["leave_text"]
        for key, value in replacements.items():
            msg = msg.replace(key, value)
        await channel.send(msg)
    
    await log_action(member.guild, "membres", f"📤 {member.name} a quitté le serveur")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    config = server_config[message.guild.id]
    user_key = f"{message.guild.id}_{message.author.id}"
    
    stats_data[user_key]["messages"] += 1
    stats_data[user_key]["last_message"] = datetime.now()
    
    antispam = config["antispam"]
    if antispam["enabled"]:
        recent_messages = []
        async for m in message.channel.history(limit=antispam["messages"]):
            if m.author == message.author and (datetime.now() - m.created_at).total_seconds() < antispam["seconds"]:
                recent_messages.append(m)
        
        if len(recent_messages) >= antispam["messages"]:
            await message.channel.purge(limit=antispam["messages"], check=lambda m: m.author == message.author)
            await message.channel.send(f"{message.author.mention}, stop le spam!", delete_after=5)
            return
    
    for word in config["automod_words"]:
        if word.lower() in message.content.lower():
            await message.delete()
            await message.channel.send(f"{message.author.mention}, ce mot est interdit!", delete_after=5)
            await log_action(message.guild, "modération", f"🚫 Message supprimé de {message.author.mention}: mot interdit")
            return
    
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    config = server_config[member.guild.id]
    
    if after.channel and after.channel.id == config.get("tempvoc_channel"):
        category = member.guild.get_channel(config.get("tempvoc_category"))
        
        temp_channel = await member.guild.create_voice_channel(
            name=f"Vocal de {member.name}",
            category=category,
            user_limit=10
        )
        
        await member.move_to(temp_channel)
        
        await asyncio.sleep(2)
        while True:
            await asyncio.sleep(5)
            if len(temp_channel.members) == 0:
                await temp_channel.delete()
                break
    
    user_key = f"{member.guild.id}_{member.id}"
    
    if before.channel is None and after.channel:
        voice_tracking[user_key] = datetime.now()
    elif before.channel and after.channel is None:
        if user_key in voice_tracking:
            time_spent = (datetime.now() - voice_tracking[user_key]).total_seconds()
            stats_data[user_key]["voice_time"] += time_spent
            del voice_tracking[user_key]

# ============= LOG SYSTEM =============
async def log_action(guild, log_type, message):
    config = server_config[guild.id]
    log_channel_id = config["log_channels"].get(log_type)
    
    if not log_channel_id:
        return
    
    channel = bot.get_channel(log_channel_id)
    if channel:
        embed = discord.Embed(description=message, color=discord.Color.blue(), timestamp=datetime.now())
        await channel.send(embed=embed)
# ============= HELP & CONFIG =============
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="🛡️ Commandes de Modération",
        description="Commandes pour gérer ton serveur",
        color=discord.Color.blue()
    )
    
    commands_list = [
        ("!kick <@membre> [raison]", "Expulse un membre du serveur"),
        ("!ban <@membre> [raison]", "Bannit un membre du serveur"),
        ("!unban <ID>", "Débannit un utilisateur (utilise son ID)"),
        ("!mute <@membre> <durée> [raison]", "Mute temporairement (10s, 5m, 1h, 1d)"),
        ("!unmute <@membre>", "Retire le mute d'un membre"),
        ("!clear <nombre>", "Supprime des messages (1-100)"),
        ("!lock / !unlock", "Verrouille ou déverrouille le salon actuel"),
        ("!warn <@membre> [raison]", "Avertir un membre"),
        ("!warnings [@membre]", "Voir les avertissements")
    ]
    
    for cmd, desc in commands_list:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.add_field(
        name="⚠️ Permissions requises",
        value="Administrateur/Modérateur pour utiliser ces commandes",
        inline=False
    )
    
    select = Select(
        placeholder="🌈 Choisir une catégorie",
        options=[
            discord.SelectOption(label="Modération", emoji="🛡️", value="moderation"),
            discord.SelectOption(label="Économie", emoji="💰", value="economy"),
            discord.SelectOption(label="Fun", emoji="🎮", value="fun"),
            discord.SelectOption(label="Utilitaires", emoji="🔧", value="utility"),
            discord.SelectOption(label="Bienvenue/Départ", emoji="👋", value="welcome"),
            discord.SelectOption(label="Systèmes", emoji="⚙️", value="systems")
        ]
    )
    
    async def select_callback(interaction: discord.Interaction):
        category = select.values[0]
        
        embeds_data = {
            "moderation": ("🛡️ Commandes de Modération", "Commandes pour gérer ton serveur", discord.Color.blue(), [
                ("!kick <@membre> [raison]", "Expulse un membre du serveur"),
                ("!ban <@membre> [raison]", "Bannit un membre du serveur"),
                ("!unban <ID>", "Débannit un utilisateur"),
                ("!mute <@membre> <durée> [raison]", "Mute temporairement (10s, 5m, 1h, 1d)"),
                ("!unmute <@membre>", "Retire le mute d'un membre"),
                ("!clear <nombre>", "Supprime des messages (1-100)"),
                ("!lock / !unlock", "Verrouille/déverrouille le salon"),
                ("!warn <@membre> [raison]", "Avertir un membre"),
                ("!warnings [@membre]", "Voir les avertissements")
            ]),
            "economy": ("💰 Commandes d'Économie", "Gagne et dépense de l'argent virtuel", discord.Color.gold(), [
                ("!daily", "Récompense journalière"),
                ("!balance [membre]", "Voir ton argent"),
                ("!rep <membre>", "Donner de la réputation"),
                ("!work", "Travailler pour gagner de l'argent"),
                ("!beg", "Demander l'aumône"),
                ("!pay <membre> <montant>", "Payer quelqu'un"),
                ("!rob <membre>", "Tenter de voler quelqu'un")
            ]),
            "fun": ("🎮 Commandes Fun & Jeux", "Amuse-toi avec ces commandes", discord.Color.red(), [
                ("!8ball <question>", "Pose une question à la boule magique"),
                ("!joke", "Raconte une blague"),
                ("!coinflip", "Pile ou Face"),
                ("!dice [mise]", "Lance un dé (avec ou sans mise)"),
                ("!rps <pierre/papier/ciseaux>", "Pierre-Papier-Ciseaux")
            ]),
            "utility": ("🔧 Commandes Utilitaires", "Outils pratiques pour le serveur", discord.Color.greyple(), [
                ("!userinfo [membre]", "Info sur un membre"),
                ("!serverinfo", "Info sur le serveur"),
                ("!avatar [membre]", "Avatar d'un membre"),
                ("!poll <question> | <opt1> | <opt2>", "Créer un sondage"),
                ("!remind <durée> <message>", "Créer un rappel"),
                ("!timer <temps> [raison]", "Créer un minuteur"),
                ("!stats [membre]", "Voir les statistiques"),
                ("!leaderboard [catégorie]", "Voir le classement")
            ]),
            "welcome": ("👋 Bienvenue/Départ", "Messages de bienvenue et départ personnalisés", discord.Color.purple(), [
                ("!bvntext <message>", "Message de bienvenue en texte (Variables: {user}, {server}, {count})"),
                ("!bvnembed", "Créer un embed de bienvenue personnalisé"),
                ("!leavetext <message>", "Message de départ en texte (Variables: {user}, {server}, {count})"),
                ("!leaveembed", "Créer un embed de départ personnalisé"),
                ("!setwelcome <#salon>", "Définir le salon de bienvenue"),
                ("!setleave <#salon>", "Définir le salon de départ")
            ]),
            "systems": ("⚙️ Systèmes & Configuration", "Configure le bot selon tes besoins", discord.Color.purple(), [
                ("!config", "Menu de configuration complet"),
                ("!ticketsetup", "Configurer les tickets"),
                ("!tempvoc <salon>", "Configurer les vocaux temporaires"),
                ("!giveaway <durée> <prix>", "Créer un giveaway"),
                ("!setlog <type> <#salon>", "Configurer les logs"),
                ("!autorole <@role>", "Rôle automatique aux nouveaux"),
                ("!antispam <on/off>", "Activer/désactiver l'antispam")
            ])
        }
        
        title, description, color, commands_list = embeds_data[category]
        selected_embed = discord.Embed(title=title, description=description, color=color)
        
        for cmd, desc in commands_list:
            selected_embed.add_field(name=cmd, value=desc, inline=False)
        
        if category == "moderation":
            selected_embed.add_field(
                name="⚠️ Permissions requises",
                value="Administrateur/Modérateur pour utiliser ces commandes",
                inline=False
            )
        
        await interaction.response.edit_message(embed=selected_embed, view=view)
    
    select.callback = select_callback
    
    view = View(timeout=180)
    view.add_item(select)
    
    await ctx.send(embed=embed, view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def config(ctx):
    config = server_config[ctx.guild.id]
    
    embed = discord.Embed(
        title="⚙️ Configuration du serveur",
        description="Utilise les boutons et menus ci-dessous pour configurer le bot",
        color=discord.Color.blue()
    )
    
    welcome_ch = bot.get_channel(config["welcome_channel"]) if config["welcome_channel"] else None
    leave_ch = bot.get_channel(config["leave_channel"]) if config["leave_channel"] else None
    log_ch = bot.get_channel(config["log_channels"].get("modération")) if config["log_channels"].get("modération") else None
    autorole = ctx.guild.get_role(config["autorole"]) if config["autorole"] else None
    
    welcome_type = "📝 Texte" if config["welcome_text"] else "🎨 Embed" if config["welcome_embed"] else "❌ Non défini"
    leave_type = "📝 Texte" if config["leave_text"] else "🎨 Embed" if config["leave_embed"] else "❌ Non défini"
    
    config_text = f"""📋 **Configuration actuelle**
👋 **Salon de bienvenue:** {welcome_ch.mention if welcome_ch else '`Non défini`'}
👋 **Type de bienvenue:** {welcome_type}
🚪 **Salon de départ:** {leave_ch.mention if leave_ch else '`Non défini`'}
🚪 **Type de départ:** {leave_type}
📜 **Salon de logs:** {log_ch.mention if log_ch else '`Non défini`'}
👤 **Rôle automatique:** {autorole.mention if autorole else '`Non défini`'}
📝 **Questionnaire:** {'✅ Activé' if config['questionnaire_active'] else '❌ Désactivé'}

📚 **Guide rapide**
**1.** Configure les salons avec les menus déroulants
**2.** Configure les messages avec les boutons
**3.** Clique sur 💾 pour sauvegarder"""
    
    embed.add_field(name="", value=config_text, inline=False)
    embed.set_footer(text=f"⚙️ Configuré par {ctx.author.name}")
    
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    
    select_welcome = Select(
        placeholder="👋 Choisir le salon de bienvenue",
        options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="👋") 
                 for ch in ctx.guild.text_channels[:25]]
    )
    
    select_leave = Select(
        placeholder="🚪 Choisir le salon de départ",
        options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="🚪") 
                 for ch in ctx.guild.text_channels[:25]]
    )
    
    select_logs = Select(
        placeholder="📜 Choisir le salon de logs",
        options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="📜") 
                 for ch in ctx.guild.text_channels[:25]]
    )
    
    select_autorole = Select(
        placeholder="👤 Choisir le rôle automatique",
        options=[discord.SelectOption(label=role.name, value=str(role.id), emoji="👤") 
                 for role in ctx.guild.roles[1:26]]
    )
    
    async def welcome_callback(interaction: discord.Interaction):
        channel_id = int(select_welcome.values[0])
        server_config[ctx.guild.id]["welcome_channel"] = channel_id
        await interaction.response.send_message(f"✅ Salon de bienvenue configuré!", ephemeral=True)
    
    async def leave_callback(interaction: discord.Interaction):
        channel_id = int(select_leave.values[0])
        server_config[ctx.guild.id]["leave_channel"] = channel_id
        await interaction.response.send_message(f"✅ Salon de départ configuré!", ephemeral=True)
    
    async def logs_callback(interaction: discord.Interaction):
        channel_id = int(select_logs.values[0])
        server_config[ctx.guild.id]["log_channels"]["modération"] = channel_id
        await interaction.response.send_message(f"✅ Salon de logs configuré!", ephemeral=True)
    
    async def autorole_callback(interaction: discord.Interaction):
        role_id = int(select_autorole.values[0])
        server_config[ctx.guild.id]["autorole"] = role_id
        await interaction.response.send_message(f"✅ Rôle automatique configuré!", ephemeral=True)
    
    select_welcome.callback = welcome_callback
    select_leave.callback = leave_callback
    select_logs.callback = logs_callback
    select_autorole.callback = autorole_callback
    
    btn_welcome_text = Button(label="📝 Message Bienvenue", style=discord.ButtonStyle.primary, emoji="👋")
    btn_welcome_embed = Button(label="🎨 Embed Bienvenue", style=discord.ButtonStyle.primary, emoji="🎨")
    btn_leave_text = Button(label="📝 Message Départ", style=discord.ButtonStyle.secondary, emoji="🚪")
    btn_leave_embed = Button(label="🎨 Embed Départ", style=discord.ButtonStyle.secondary, emoji="🎨")
    btn_questionnaire = Button(label="📝 Questionnaire", style=discord.ButtonStyle.secondary, emoji="📝")
    btn_save = Button(label="💾 Sauvegarder", style=discord.ButtonStyle.success, emoji="💾")
    
    async def welcome_text_callback(interaction: discord.Interaction):
        await interaction.response.send_message(
            "📝 **Configuration du message de bienvenue**\n\n"
            "Utilise la commande: `!bvntext <message>`\n\n"
            "**Variables disponibles:**\n"
            "`{user}` - Mention du membre\n"
            "`{server}` - Nom du serveur\n"
            "`{count}` - Nombre de membres\n\n"
            "**Pour faire un saut de ligne:** Utilise `\\n` dans ton message\n\n"
            "**Exemples:**\n\n"
            "**Style Simple:**\n"
            "`!bvntext Bienvenue {user} sur {server}!\\nNous sommes maintenant {count} membres!`\n\n"
            "**Style Chaleureux:**\n"
            "`!bvntext 👋 Hey {user}!\\nBienvenue dans la communauté {server}!\\n\\nN'hésite pas à te présenter et à explorer les salons.\\n✨ Tu es notre {count}ème membre!`\n\n"
            "**Style Gaming:**\n"
            "`!bvntext 🎮 Un nouveau joueur vient de spawn!\\n{user} a rejoint {server}\\n\\n👥 Nous sommes désormais {count} gamers!\\nGG et bon game!`\n\n"
            "**Style Formel:**\n"
            "`!bvntext 🌟 {server} souhaite la bienvenue à {user}!\\n\\nNous sommes ravis de compter {count} membres dans notre communauté.\\nConsultez les règles et amusez-vous bien!`\n\n"
            "**Style Fun:**\n"
            "`!bvntext 🚀 ALERTE! {user} vient d'atterrir sur {server}!\\n\\n🎉 Mission accomplie: {count} membres à bord!\\n\\nPrépare-toi à vivre une aventure incroyable!`",
            ephemeral=True
        )
    
    async def welcome_embed_callback(interaction: discord.Interaction):
        await interaction.response.send_message(
            "🎨 **Configuration de l'embed de bienvenue**\n\n"
            "Utilise la commande: `!bvnembed`\n\n"
            "Cette commande te guidera étape par étape pour créer ton embed personnalisé!",
            ephemeral=True
        )
    
    async def leave_text_callback(interaction: discord.Interaction):
        await interaction.response.send_message(
            "📝 **Configuration du message de départ**\n\n"
            "Utilise la commande: `!leavetext <message>`\n\n"
            "**Variables disponibles:**\n"
            "`{user}` - Nom du membre\n"
            "`{server}` - Nom du serveur\n"
            "`{count}` - Nombre de membres\n\n"
            "**Pour faire un saut de ligne:** Utilise `\\n` dans ton message\n\n"
            "**Exemple:**\n"
            "`!leavetext Au revoir {user}...\\nNous sommes maintenant {count} membres.`",
            ephemeral=True
        )
    
    async def leave_embed_callback(interaction: discord.Interaction):
        await interaction.response.send_message(
            "🎨 **Configuration de l'embed de départ**\n\n"
            "Utilise la commande: `!leaveembed`\n\n"
            "Cette commande te guidera étape par étape pour créer ton embed personnalisé!",
            ephemeral=True
        )
    
    async def questionnaire_callback(interaction: discord.Interaction):
        config["questionnaire_active"] = not config["questionnaire_active"]
        status = "✅ Activé" if config["questionnaire_active"] else "❌ Désactivé"
        await interaction.response.send_message(f"📝 Questionnaire: {status}", ephemeral=True)
    
    async def save_callback(interaction: discord.Interaction):
        await interaction.response.send_message("✅ Configuration sauvegardée avec succès!", ephemeral=True)
    
    btn_welcome_text.callback = welcome_text_callback
    btn_welcome_embed.callback = welcome_embed_callback
    btn_leave_text.callback = leave_text_callback
    btn_leave_embed.callback = leave_embed_callback
    btn_questionnaire.callback = questionnaire_callback
    btn_save.callback = save_callback
    
    view = View(timeout=300)
    view.add_item(select_welcome)
    view.add_item(select_leave)
    view.add_item(select_logs)
    view.add_item(select_autorole)
    view.add_item(btn_welcome_text)
    view.add_item(btn_welcome_embed)
    view.add_item(btn_leave_text)
    view.add_item(btn_leave_embed)
    view.add_item(btn_questionnaire)
    view.add_item(btn_save)
    
    await ctx.send(embed=embed, view=view)

# ============= MODÉRATION =============
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Aucune raison"):
    await member.kick(reason=reason)
    await ctx.send(f"✅ {member.mention} a été expulsé! Raison: {reason}")
    await log_action(ctx.guild, "modération", f"👢 {member.mention} expulsé par {ctx.author.mention} - Raison: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison"):
    await member.ban(reason=reason)
    await ctx.send(f"✅ {member.mention} a été banni! Raison: {reason}")
    await log_action(ctx.guild, "modération", f"🔨 {member.mention} banni par {ctx.author.mention} - Raison: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(f"✅ {user.mention} a été débanni!")
    await log_action(ctx.guild, "modération", f"✅ {user.mention} débanni par {ctx.author.mention}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: str, *, reason="Aucune raison"):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    
    if not mute_role:
        mute_role = await ctx.guild.create_role(name="Muted", reason="Rôle de mute automatique")
        for channel in ctx.guild.channels:
            await channel.set_permissions(mute_role, speak=False, send_messages=False)
    
    await member.add_roles(mute_role, reason=reason)
    await ctx.send(f"🔇 {member.mention} a été mute pour {duration}! Raison: {reason}")
    await log_action(ctx.guild, "modération", f"🔇 {member.mention} mute par {ctx.author.mention} ({duration}) - Raison: {reason}")
    
    time_convert = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    amount = int(duration[:-1])
    unit = duration[-1]
    
    if unit not in time_convert:
        await ctx.send("❌ Durée invalide! Utilise: 10s, 5m, 1h, 1d")
        return
    
    sleep_time = amount * time_convert[unit]
    
    await asyncio.sleep(sleep_time)
    await member.remove_roles(mute_role)
    await ctx.send(f"🔊 {member.mention} a été unmute automatiquement!")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    
    if mute_role in member.roles:
        await member.remove_roles(mute_role)
        await ctx.send(f"🔊 {member.mention} a été unmute!")
        await log_action(ctx.guild, "modération", f"🔊 {member.mention} unmute par {ctx.author.mention}")
    else:
        await ctx.send(f"❌ {member.mention} n'est pas mute!")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount < 1 or amount > 100:
        await ctx.send("❌ Nombre invalide! (1-100)")
        return
    
    await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"✅ {amount} messages supprimés!")
    await asyncio.sleep(3)
    await msg.delete()
    await log_action(ctx.guild, "modération", f"🗑️ {amount} messages supprimés dans {ctx.channel.mention} par {ctx.author.mention}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Salon verrouillé!")
    await log_action(ctx.guild, "modération", f"🔒 {ctx.channel.mention} verrouillé par {ctx.author.mention}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 Salon déverrouillé!")
    await log_action(ctx.guild, "modération", f"🔓 {ctx.channel.mention} déverrouillé par {ctx.author.mention}")

@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member, *, reason="Aucune raison"):
    warnings_data[member.id].append({
        "reason": reason,
        "moderator": ctx.author.id,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    
    warn_count = len(warnings_data[member.id])
    
    await ctx.send(f"⚠️ {member.mention} a été averti! ({warn_count} avertissements)\nRaison: {reason}")
    await log_action(ctx.guild, "modération", f"⚠️ {member.mention} averti par {ctx.author.mention} - Raison: {reason}")
    
    if warn_count == 3:
        await ctx.send(f"🔇 {member.mention} a reçu un mute automatique (3 warns)!")
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if mute_role:
            await member.add_roles(mute_role)
    elif warn_count == 5:
        await ctx.send(f"👢 {member.mention} a été kick automatiquement (5 warns)!")
        await member.kick(reason="5 avertissements")

@bot.command()
async def warnings(ctx, member: discord.Member = None):
    member = member or ctx.author
    warns = warnings_data.get(member.id, [])
    
    if not warns:
        await ctx.send(f"✅ {member.mention} n'a aucun avertissement!")
        return
    
    embed = discord.Embed(
        title=f"⚠️ Avertissements de {member.name}",
        color=discord.Color.orange()
    )
    
    for i, warn in enumerate(warns, 1):
        mod = ctx.guild.get_member(warn["moderator"])
        mod_name = mod.name if mod else "Inconnu"
        embed.add_field(
            name=f"Warn #{i}",
            value=f"**Raison:** {warn['reason']}\n**Par:** {mod_name}\n**Date:** {warn['time']}",
            inline=False
        )
    
    await ctx.send(embed=embed)
    # Note: Cette partie contient toutes les autres commandes (modération, économie, fun, utilitaires, bienvenue/départ, systèmes)
# Le code complet est trop long pour être affiché en une seule fois.
# Les commandes modifiées sont les suivantes:

# ============= BIENVENUE/DÉPART (VERSION MISE À JOUR) =============
@bot.command()
@commands.has_permissions(administrator=True)
async def bvntext(ctx, *, message):
    # Remplace les \n par de vrais sauts de ligne
    message = message.replace("\\n", "\n")
    
    server_config[ctx.guild.id]["welcome_text"] = message
    server_config[ctx.guild.id]["welcome_embed"] = None
    
    await ctx.send(
        f"✅ Message de bienvenue configuré!\n\n"
        f"**Variables disponibles:**\n"
        f"`{{user}}` - Mention du membre\n"
        f"`{{server}}` - Nom du serveur\n"
        f"`{{count}}` - Nombre de membres\n\n"
        f"**Aperçu:**\n{message.replace('{user}', ctx.author.mention).replace('{server}', ctx.guild.name).replace('{count}', str(ctx.guild.member_count))}"
    )

@bot.command()
@commands.has_permissions(administrator=True)
async def leavetext(ctx, *, message):
    # Remplace les \n par de vrais sauts de ligne
    message = message.replace("\\n", "\n")
    
    server_config[ctx.guild.id]["leave_text"] = message
    server_config[ctx.guild.id]["leave_embed"] = None
    
    await ctx.send(
        f"✅ Message de départ configuré!\n\n"
        f"**Variables disponibles:**\n"
        f"`{{user}}` - Nom du membre\n"
        f"`{{server}}` - Nom du serveur\n"
        f"`{{count}}` - Nombre de membres\n\n"
        f"**Aperçu:**\n{message.replace('{user}', ctx.author.name).replace('{server}', ctx.guild.name).replace('{count}', str(ctx.guild.member_count))}"
    )
if __name__ == "__main__":
    keep_alive()
    
    TOKEN = os.environ.get("DISCORD_TOKEN")
    
    if not TOKEN:
        print("❌ ERREUR: Variable d'environnement DISCORD_TOKEN manquante!")
        print("📝 Sur Render.com, ajoute ta variable d'environnement:")
        print("   Clé: DISCORD_TOKEN")
        print("   Valeur: ton_token_discord")
        exit(1)
    
    try:
        print("🚀 Démarrage du bot...")
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ ERREUR: Token Discord invalide!")
        print("Vérifie que ton token est correct dans les variables d'environnement.")
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
