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
    "welcome_msg": "Bienvenue {user} sur {server}!",
    "leave_msg": "{user} a quitté {server}",
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
    
    if config.get("welcome_embed"):
        embed_data = config["welcome_embed"]
        embed = discord.Embed(
            title=embed_data.get("title", "Bienvenue!").replace("{user}", member.name),
            description=embed_data.get("description", "").replace("{user}", member.mention).replace("{server}", member.guild.name),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)
    else:
        msg = config["welcome_msg"].replace("{user}", member.mention).replace("{server}", member.guild.name)
        await channel.send(msg)
    
    # Log
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
    
    if config.get("leave_embed"):
        embed_data = config["leave_embed"]
        embed = discord.Embed(
            title=embed_data.get("title", "Au revoir!").replace("{user}", member.name),
            description=embed_data.get("description", "").replace("{user}", member.name).replace("{server}", member.guild.name),
            color=discord.Color.red()
        )
        await channel.send(embed=embed)
    else:
        msg = config["leave_msg"].replace("{user}", member.name).replace("{server}", member.guild.name)
        await channel.send(msg)
    
    await log_action(member.guild, "membres", f"📤 {member.name} a quitté le serveur")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    config = server_config[message.guild.id]
    user_key = f"{message.guild.id}_{message.author.id}"
    
    # Stats
    stats_data[user_key]["messages"] += 1
    stats_data[user_key]["last_message"] = datetime.now()
    
    # Antispam
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
    
    # Automod
    for word in config["automod_words"]:
        if word.lower() in message.content.lower():
            await message.delete()
            await message.channel.send(f"{message.author.mention}, ce mot est interdit!", delete_after=5)
            await log_action(message.guild, "modération", f"🚫 Message supprimé de {message.author.mention}: mot interdit")
            return
    
    await bot.process_commands(message)

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

# ============= HELP COMMAND (Style image 1) =============
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
        ("!lock / !unlock", "Verrouille ou déverrouille le salon actuel")
    ]
    
    for cmd, desc in commands_list:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.add_field(
        name="⚠️ Permissions requises pour utiliser ces commandes",
        value="",
        inline=False
    )
    
    # Dropdown pour choisir une catégorie
    select = Select(
        placeholder="🌈 Choisir une catégorie",
        options=[
            discord.SelectOption(label="Modération", emoji="🛡️", value="moderation"),
            discord.SelectOption(label="Économie", emoji="💰", value="economy"),
            discord.SelectOption(label="Fun", emoji="🎮", value="fun"),
            discord.SelectOption(label="Utilitaires", emoji="🔧", value="utility"),
            discord.SelectOption(label="Systèmes", emoji="⚙️", value="systems")
        ]
    )
    
    async def select_callback(interaction: discord.Interaction):
        category = select.values[0]
        
        embeds = {
            "moderation": discord.Embed(
                title="🛡️ Commandes de Modération",
                description="Commandes pour gérer ton serveur",
                color=discord.Color.blue()
            ),
            "economy": discord.Embed(
                title="💰 Commandes d'Économie",
                description="Gagne et dépense de l'argent virtuel",
                color=discord.Color.gold()
            ),
            "fun": discord.Embed(
                title="🎮 Commandes Fun & Jeux",
                description="Amuse-toi avec ces commandes",
                color=discord.Color.red()
            ),
            "utility": discord.Embed(
                title="🔧 Commandes Utilitaires",
                description="Outils pratiques pour le serveur",
                color=discord.Color.greyple()
            ),
            "systems": discord.Embed(
                title="⚙️ Systèmes & Configuration",
                description="Configure le bot selon tes besoins",
                color=discord.Color.purple()
            )
        }
        
        commands_data = {
            "moderation": [
                ("!kick <@membre> [raison]", "Expulse un membre du serveur"),
                ("!ban <@membre> [raison]", "Bannit un membre du serveur"),
                ("!unban <ID>", "Débannit un utilisateur (utilise son ID)"),
                ("!mute <@membre> <durée> [raison]", "Mute temporairement (10s, 5m, 1h, 1d)"),
                ("!unmute <@membre>", "Retire le mute d'un membre"),
                ("!clear <nombre>", "Supprime des messages (1-100)"),
                ("!lock / !unlock", "Verrouille ou déverrouille le salon actuel")
            ],
            "economy": [
                ("!daily", "Récompense journalière"),
                ("!balance [membre]", "Voir ton argent"),
                ("!rep <membre>", "Donner de la réputation"),
                ("!work", "Travailler pour gagner de l'argent"),
                ("!beg", "Demander l'aumône"),
                ("!pay <membre> <montant>", "Payer quelqu'un"),
                ("!rob <membre>", "Tenter de voler quelqu'un"),
                ("!shop", "Voir la boutique"),
                ("!buy <id>", "Acheter un article")
            ],
            "fun": [
                ("!8ball <question>", "Pose une question à la boule magique"),
                ("!joke", "Raconte une blague"),
                ("!coinflip", "Pile ou Face"),
                ("!dice [mise]", "Lance un dé"),
                ("!rps <pierre/papier/ciseaux>", "Pierre-Papier-Ciseaux"),
                ("!tictactoe <membre>", "Jouer au morpion"),
                ("!hangman", "Jeu du pendu"),
                ("!trivia", "Quiz avec récompenses")
            ],
            "utility": [
                ("!userinfo [membre]", "Info sur un membre"),
                ("!serverinfo", "Info sur le serveur"),
                ("!avatar [membre]", "Avatar d'un membre"),
                ("!poll <question> | <opt1> | <opt2>", "Créer un sondage"),
                ("!remind <durée> <message>", "Créer un rappel"),
                ("!timer <temps> [raison]", "Créer un minuteur")
            ],
            "systems": [
                ("!config", "Menu de configuration"),
                ("!ticketsetup", "Configurer les tickets"),
                ("!tempvoc <salon>", "Configurer les vocaux temporaires"),
                ("!giveaway <durée> <prix>", "Créer un giveaway"),
                ("!setlog <type> <salon>", "Configurer les logs"),
                ("!autorole <role>", "Rôle automatique aux nouveaux")
            ]
        }
        
        selected_embed = embeds[category]
        for cmd, desc in commands_data[category]:
            selected_embed.add_field(name=cmd, value=desc, inline=False)
        
        if category == "moderation":
            selected_embed.add_field(
                name="⚠️ Permissions requises pour utiliser ces commandes",
                value="",
                inline=False
            )
        
        await interaction.response.edit_message(embed=selected_embed, view=view)
    
    select.callback = select_callback
    
    view = View(timeout=180)
    view.add_item(select)
    
    await ctx.send(embed=embed, view=view)

# ============= CONFIG COMMAND (Style image 2) =============
@bot.command()
@commands.has_permissions(administrator=True)
async def config(ctx):
    config = server_config[ctx.guild.id]
    
    # Créer l'embed principal
    embed = discord.Embed(
        title="⚙️ Configuration du serveur",
        description="Utilise les menus déroulants ci-dessous pour configurer le bot",
        color=discord.Color.blue()
    )
    
    # Configuration actuelle
    welcome_ch = bot.get_channel(config["welcome_channel"]) if config["welcome_channel"] else None
    log_ch = bot.get_channel(config["log_channels"].get("modération")) if config["log_channels"].get("modération") else None
    autorole = ctx.guild.get_role(config["autorole"]) if config["autorole"] else None
    
    config_text = f"""📋 **Configuration actuelle**
👋 **Salon de bienvenue:** {welcome_ch.mention if welcome_ch else '# Non défini'}
📜 **Salon de logs:** {log_ch.mention if log_ch else '# Non défini'}
👤 **Rôle automatique:** {autorole.mention if autorole else '@Non défini'}
📝 **Questionnaire:** ❌ Désactivé

📚 **Guide**
**1.** Choisis le salon de bienvenue (où le bot accueillera les nouveaux membres)
**2.** Choisis le salon de logs (pour suivre tous les événements)
**3.** Choisis le rôle à donner automatiquement aux nouveaux
**4.** Active/désactive le questionnaire d'arrivée
**5.** Clique sur 💾 pour sauvegarder"""
    
    embed.add_field(name="", value=config_text, inline=False)
    embed.set_footer(text=f"⚙️ Configuré par {ctx.author.name}")
    
    # Image de profil (optionnelle)
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    
    # Selects pour la configuration
    select_welcome = Select(
        placeholder="👋 Choisir le salon de bienvenue",
        options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="👋") 
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
                 for role in ctx.guild.roles[1:26]]  # Skip @everyone
    )
    
    async def welcome_callback(interaction: discord.Interaction):
        channel_id = int(select_welcome.values[0])
        server_config[ctx.guild.id]["welcome_channel"] = channel_id
        await interaction.response.send_message(f"✅ Salon de bienvenue configuré!", ephemeral=True)
    
    async def logs_callback(interaction: discord.Interaction):
        channel_id = int(select_logs.values[0])
        server_config[ctx.guild.id]["log_channels"]["modération"] = channel_id
        await interaction.response.send_message(f"✅ Salon de logs configuré!", ephemeral=True)
    
    async def autorole_callback(interaction: discord.Interaction):
        role_id = int(select_autorole.values[0])
        server_config[ctx.guild.id]["autorole"] = role_id
        await interaction.response.send_message(f"✅ Rôle automatique configuré!", ephemeral=True)
    
    select_welcome.callback = welcome_callback
    select_logs.callback = logs_callback
    select_autorole.callback = autorole_callback
    
    # Boutons
    btn_questionnaire = Button(
        label="📝 Questionnaire", 
        style=discord.ButtonStyle.secondary,
        emoji="📝"
    )
    
    btn_save = Button(
        label="💾 Sauvegarder",
        style=discord.ButtonStyle.success,
        emoji="💾"
    )
    
    async def questionnaire_callback(interaction: discord.Interaction):
        config["questionnaire_active"] = not config["questionnaire_active"]
        status = "✅ Activé" if config["questionnaire_active"] else "❌ Désactivé"
        await interaction.response.send_message(f"📝 Questionnaire: {status}", ephemeral=True)
    
    async def save_callback(interaction: discord.Interaction):
        await interaction.response.send_message("✅ Configuration sauvegardée avec succès!", ephemeral=True)
    
    btn_questionnaire.callback = questionnaire_callback
    btn_save.callback = save_callback
    
    view = View(timeout=300)
    view.add_item(select_welcome)
    view.add_item(select_logs)
    view.add_item(select_autorole)
    view.add_item(btn_questionnaire)
    view.add_item(btn_save)
    
    await ctx.send(embed=embed, view=view)

# Continue dans partie 2...
# ============= PARTIE 2/3: COMMANDES =============
# Cette partie va après la partie 1

# ============= MODÉRATION =============
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Aucune raison"):
    await member.kick(reason=reason)
    await ctx.send(f"✅ {member.mention} a été expulsé! Raison: {reason}")
    await log_action(ctx.guild, "modération", f"👢 {member.mention} expulsé par {ctx.author.mention}. Raison: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison"):
    await member.ban(reason=reason)
    await ctx.send(f"✅ {member.mention} a été banni! Raison: {reason}")
    await log_action(ctx.guild, "modération", f"🔨 {member.mention} banni par {ctx.author.mention}. Raison: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(f"✅ {user.mention} a été débanni!")
    await log_action(ctx.guild, "modération", f"🔓 {user.mention} débanni par {ctx.author.mention}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount < 1 or amount > 100:
        return await ctx.send("❌ Nombre invalide (1-100)")
    
    deleted = await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"✅ {len(deleted)-1} messages supprimés!")
    await asyncio.sleep(3)
    await msg.delete()
    await log_action(ctx.guild, "modération", f"🗑️ {len(deleted)-1} messages supprimés dans {ctx.channel.mention} par {ctx.author.mention}")

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
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: str, *, reason="Aucune raison"):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    
    if not mute_role:
        mute_role = await ctx.guild.create_role(name="Muted")
        for channel in ctx.guild.channels:
            await channel.set_permissions(mute_role, send_messages=False, speak=False)
    
    await member.add_roles(mute_role, reason=reason)
    
    # Parse duration
    time_convert = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    unit = duration[-1]
    if unit not in time_convert:
        return await ctx.send("❌ Format invalide! Utilise: 10s, 5m, 1h, 1d")
    
    amount = int(duration[:-1])
    seconds = amount * time_convert[unit]
    
    await ctx.send(f"🔇 {member.mention} a été mute pour {duration}! Raison: {reason}")
    await log_action(ctx.guild, "modération", f"🔇 {member.mention} mute par {ctx.author.mention} pour {duration}. Raison: {reason}")
    
    await asyncio.sleep(seconds)
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
        await ctx.send("❌ Ce membre n'est pas mute!")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason="Aucune raison"):
    user_key = f"{ctx.guild.id}_{member.id}"
    warnings_data[user_key].append({"reason": reason, "date": datetime.now(), "moderator": ctx.author.id})
    
    await ctx.send(f"⚠️ {member.mention} a reçu un avertissement! Raison: {reason}")
    await log_action(ctx.guild, "modération", f"⚠️ {member.mention} averti par {ctx.author.mention}. Raison: {reason}")

@bot.command()
async def warnings(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_key = f"{ctx.guild.id}_{member.id}"
    warns = warnings_data[user_key]
    
    if not warns:
        return await ctx.send(f"✅ {member.mention} n'a aucun avertissement!")
    
    embed = discord.Embed(title=f"⚠️ Avertissements de {member.name}", color=discord.Color.orange())
    for i, warn in enumerate(warns, 1):
        mod = ctx.guild.get_member(warn["moderator"])
        embed.add_field(
            name=f"Avertissement #{i}",
            value=f"**Raison:** {warn['reason']}\n**Par:** {mod.mention if mod else 'Inconnu'}\n**Date:** {warn['date'].strftime('%d/%m/%Y %H:%M')}",
            inline=False
        )
    
    await ctx.send(embed=embed)

# ============= ÉCONOMIE =============
@bot.command()
async def daily(ctx):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    user_data = economy_data[user_key]
    
    if user_data["daily_claimed"]:
        time_since = datetime.now() - user_data["daily_claimed"]
        if time_since < timedelta(hours=24):
            remaining = timedelta(hours=24) - time_since
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            return await ctx.send(f"⏰ Tu as déjà réclamé ton daily! Reviens dans {hours}h {minutes}min")
    
    amount = random.randint(100, 500)
    user_data["money"] += amount
    user_data["daily_claimed"] = datetime.now()
    
    await ctx.send(f"💰 Tu as reçu **{amount}$** comme récompense journalière!")

@bot.command(aliases=["bal"])
async def balance(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_key = f"{ctx.guild.id}_{member.id}"
    user_data = economy_data[user_key]
    
    embed = discord.Embed(title=f"💰 Portefeuille de {member.name}", color=discord.Color.gold())
    embed.add_field(name="💵 Cash", value=f"{user_data['money']}$", inline=True)
    embed.add_field(name="🏦 Banque", value=f"{user_data['bank']}$", inline=True)
    embed.add_field(name="⭐ Réputation", value=f"{user_data['rep']}", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    
    await ctx.send(embed=embed)

@bot.command()
async def work(ctx):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    user_data = economy_data[user_key]
    
    if user_data["work_claimed"]:
        time_since = datetime.now() - user_data["work_claimed"]
        if time_since < timedelta(hours=1):
            remaining = timedelta(hours=1) - time_since
            minutes = remaining.seconds // 60
            return await ctx.send(f"⏰ Tu es fatigué! Reviens dans {minutes} minutes")
    
    jobs = [
        ("développeur", 200, 400),
        ("médecin", 300, 500),
        ("enseignant", 150, 300),
        ("artiste", 100, 250),
        ("streamer", 250, 450)
    ]
    
    job, min_pay, max_pay = random.choice(jobs)
    amount = random.randint(min_pay, max_pay)
    user_data["money"] += amount
    user_data["work_claimed"] = datetime.now()
    
    await ctx.send(f"💼 Tu as travaillé comme **{job}** et gagné **{amount}$**!")

@bot.command()
async def beg(ctx):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    
    if random.random() < 0.6:  # 60% de chance
        amount = random.randint(10, 50)
        economy_data[user_key]["money"] += amount
        await ctx.send(f"🥺 Quelqu'un t'a donné **{amount}$**!")
    else:
        await ctx.send("😔 Personne ne t'a rien donné...")

@bot.command()
async def pay(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        return await ctx.send("❌ Montant invalide!")
    
    sender_key = f"{ctx.guild.id}_{ctx.author.id}"
    receiver_key = f"{ctx.guild.id}_{member.id}"
    
    if economy_data[sender_key]["money"] < amount:
        return await ctx.send("❌ Tu n'as pas assez d'argent!")
    
    economy_data[sender_key]["money"] -= amount
    economy_data[receiver_key]["money"] += amount
    
    await ctx.send(f"✅ Tu as payé **{amount}$** à {member.mention}!")

@bot.command()
async def rob(ctx, member: discord.Member):
    if member == ctx.author:
        return await ctx.send("❌ Tu ne peux pas te voler toi-même!")
    
    thief_key = f"{ctx.guild.id}_{ctx.author.id}"
    victim_key = f"{ctx.guild.id}_{member.id}"
    
    victim_money = economy_data[victim_key]["money"]
    
    if victim_money < 100:
        return await ctx.send(f"❌ {member.mention} est trop pauvre pour être volé!")
    
    if random.random() < 0.5:  # 50% de chance
        stolen = random.randint(50, min(victim_money, 500))
        economy_data[thief_key]["money"] += stolen
        economy_data[victim_key]["money"] -= stolen
        await ctx.send(f"💰 Tu as volé **{stolen}$** à {member.mention}!")
    else:
        fine = random.randint(100, 300)
        economy_data[thief_key]["money"] = max(0, economy_data[thief_key]["money"] - fine)
        await ctx.send(f"🚓 Tu t'es fait attraper! Amende de **{fine}$**!")

@bot.command()
async def rep(ctx, member: discord.Member):
    if member == ctx.author:
        return await ctx.send("❌ Tu ne peux pas te donner de la réputation!")
    
    user_key = f"{ctx.guild.id}_{member.id}"
    economy_data[user_key]["rep"] += 1
    
    await ctx.send(f"⭐ Tu as donné de la réputation à {member.mention}! Total: {economy_data[user_key]['rep']}")

# ============= JEUX =============
@bot.command(name="8ball")
async def eightball(ctx, *, question):
    responses = [
        "✅ Oui!", "❌ Non!", "🤔 Peut-être...", "🎲 Absolument!",
        "⛔ Absolument pas!", "💭 Demande plus tard", "🔮 Les signes pointent vers oui",
        "🚫 Mieux vaut ne pas te le dire maintenant"
    ]
    await ctx.send(f"**Question:** {question}\n**Réponse:** {random.choice(responses)}")

@bot.command()
async def joke(ctx):
    jokes = [
        "Pourquoi les plongeurs plongent-ils toujours en arrière? Parce que sinon ils tombent dans le bateau!",
        "Qu'est-ce qu'un crocodile qui surveille? Un Lacoste!",
        "Qu'est-ce qu'un canif? Un petit fien!",
        "Comment appelle-t-on un chat tombé dans un pot de peinture? Un chat-peint!"
    ]
    await ctx.send(f"😂 {random.choice(jokes)}")

@bot.command()
async def coinflip(ctx):
    result = random.choice(["Pile", "Face"])
    await ctx.send(f"🪙 C'est... **{result}**!")

@bot.command()
async def dice(ctx, bet: int = 0):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    
    if bet > 0:
        if economy_data[user_key]["money"] < bet:
            return await ctx.send("❌ Tu n'as pas assez d'argent!")
        
        result = random.randint(1, 6)
        
        if result >= 4:
            economy_data[user_key]["money"] += bet
            await ctx.send(f"🎲 Tu as lancé un **{result}**! Tu gagnes **{bet}$**! 🎉")
        else:
            economy_data[user_key]["money"] -= bet
            await ctx.send(f"🎲 Tu as lancé un **{result}**! Tu perds **{bet}$**! 😢")
    else:
        result = random.randint(1, 6)
        await ctx.send(f"🎲 Tu as lancé un **{result}**!")

@bot.command()
async def rps(ctx, choice: str):
    choices = ["pierre", "papier", "ciseaux"]
    choice = choice.lower()
    
    if choice not in choices:
        return await ctx.send("❌ Choix invalide! Utilise: pierre, papier ou ciseaux")
    
    bot_choice = random.choice(choices)
    
    if choice == bot_choice:
        result = "🤝 Égalité!"
    elif (choice == "pierre" and bot_choice == "ciseaux") or \
         (choice == "papier" and bot_choice == "pierre") or \
         (choice == "ciseaux" and bot_choice == "papier"):
        result = "🎉 Tu gagnes!"
    else:
        result = "😢 Tu perds!"
    
    await ctx.send(f"Tu as choisi: **{choice}**\nJ'ai choisi: **{bot_choice}**\n{result}")

# Continue dans partie 3...
# ============= PARTIE 3/3: SYSTÈMES AVANCÉS & DÉMARRAGE =============
# Cette partie va après la partie 2

# ============= UTILITAIRES =============
@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    
    embed = discord.Embed(title=f"📋 Info sur {member.name}", color=discord.Color.blue())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Nom", value=member.name, inline=True)
    embed.add_field(name="🆔 ID", value=member.id, inline=True)
    embed.add_field(name="📅 Compte créé", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="📥 A rejoint le", value=member.joined_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="🎭 Rôles", value=f"{len(member.roles)-1}", inline=True)
    embed.add_field(name="🤖 Bot", value="Oui" if member.bot else "Non", inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    
    embed = discord.Embed(title=f"📊 Info sur {guild.name}", color=discord.Color.green())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.add_field(name="👑 Propriétaire", value=guild.owner.mention, inline=True)
    embed.add_field(name="🆔 ID", value=guild.id, inline=True)
    embed.add_field(name="📅 Créé le", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="👥 Membres", value=guild.member_count, inline=True)
    embed.add_field(name="💬 Salons", value=len(guild.text_channels), inline=True)
    embed.add_field(name="🔊 Vocaux", value=len(guild.voice_channels), inline=True)
    embed.add_field(name="🎭 Rôles", value=len(guild.roles), inline=True)
    embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)
    embed.add_field(name="🚀 Boosts", value=guild.premium_subscription_count, inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    
    embed = discord.Embed(title=f"🖼️ Avatar de {member.name}", color=discord.Color.purple())
    embed.set_image(url=member.display_avatar.url)
    
    await ctx.send(embed=embed)

@bot.command()
async def poll(ctx, *, question):
    if "|" not in question:
        return await ctx.send("❌ Format: `!poll Question | Option1 | Option2 | ...`")
    
    parts = question.split("|")
    question_text = parts[0].strip()
    options = [opt.strip() for opt in parts[1:]]
    
    if len(options) < 2 or len(options) > 10:
        return await ctx.send("❌ Entre 2 et 10 options requises!")
    
    embed = discord.Embed(title="📊 Sondage", description=question_text, color=discord.Color.blue())
    
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, option in enumerate(options):
        embed.add_field(name=f"{emojis[i]} {option}", value="\u200b", inline=False)
    
    embed.set_footer(text=f"Sondage créé par {ctx.author.name}")
    
    msg = await ctx.send(embed=embed)
    
    for i in range(len(options)):
        await msg.add_reaction(emojis[i])

@bot.command()
async def remind(ctx, duration: str, *, message):
    time_convert = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    unit = duration[-1]
    
    if unit not in time_convert:
        return await ctx.send("❌ Format invalide! Utilise: 10s, 5m, 1h, 1d")
    
    amount = int(duration[:-1])
    seconds = amount * time_convert[unit]
    
    await ctx.send(f"⏰ Je te rappellerai dans {duration}!")
    
    await asyncio.sleep(seconds)
    await ctx.send(f"{ctx.author.mention} 🔔 Rappel: {message}")

@bot.command()
async def timer(ctx, time: str, *, reason="Timer"):
    time_convert = {"s": 1, "m": 60, "h": 3600}
    unit = time[-1]
    
    if unit not in time_convert:
        return await ctx.send("❌ Format invalide! Utilise: 10s, 5m, 1h")
    
    amount = int(time[:-1])
    seconds = amount * time_convert[unit]
    
    embed = discord.Embed(title="⏱️ Timer", description=f"**{reason}**\nTemps: {time}", color=discord.Color.orange())
    msg = await ctx.send(embed=embed)
    
    await asyncio.sleep(seconds)
    
    embed.description = f"**{reason}**\n✅ Timer terminé!"
    embed.color = discord.Color.green()
    await msg.edit(embed=embed)
    await ctx.send(f"{ctx.author.mention} ⏰ Timer terminé: {reason}")

# ============= SYSTÈME DE TICKETS =============
@bot.command()
@commands.has_permissions(administrator=True)
async def ticketsetup(ctx):
    config = server_config[ctx.guild.id]
    
    embed = discord.Embed(
        title="🎫 Système de Tickets",
        description="Clique sur le bouton ci-dessous pour créer un ticket!",
        color=discord.Color.blue()
    )
    
    button = Button(label="📩 Créer un Ticket", style=discord.ButtonStyle.primary, emoji="🎫")
    
    async def button_callback(interaction: discord.Interaction):
        config = server_config[interaction.guild.id]
        config["ticket_counter"] += 1
        
        category = interaction.guild.get_channel(config.get("ticket_category"))
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{config['ticket_counter']}",
            category=category,
            overwrites=overwrites
        )
        
        embed = discord.Embed(
            title="🎫 Ticket créé!",
            description=f"Bienvenue {interaction.user.mention}!\nUn staff va bientôt vous répondre.",
            color=discord.Color.green()
        )
        
        close_btn = Button(label="🔒 Fermer", style=discord.ButtonStyle.danger)
        
        async def close_callback(inter: discord.Interaction):
            await inter.response.send_message("🔒 Fermeture du ticket dans 5 secondes...")
            await asyncio.sleep(5)
            await channel.delete()
        
        close_btn.callback = close_callback
        
        view = View(timeout=None)
        view.add_item(close_btn)
        
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Ticket créé: {channel.mention}", ephemeral=True)
        await log_action(interaction.guild, "tickets", f"🎫 Ticket créé par {interaction.user.mention}: {channel.mention}")
    
    button.callback = button_callback
    
    view = View(timeout=None)
    view.add_item(button)
    
    await ctx.send(embed=embed, view=view)

# ============= VOCAUX TEMPORAIRES =============
@bot.command()
@commands.has_permissions(administrator=True)
async def tempvoc(ctx, channel: discord.VoiceChannel):
    config = server_config[ctx.guild.id]
    config["tempvoc_channel"] = channel.id
    config["tempvoc_category"] = channel.category_id if channel.category else None
    
    await ctx.send(f"✅ Salon vocal temporaire configuré: {channel.mention}")

@bot.event
async def on_voice_state_update(member, before, after):
    config = server_config[member.guild.id]
    
    # Création de vocal temporaire
    if after.channel and after.channel.id == config.get("tempvoc_channel"):
        category = member.guild.get_channel(config.get("tempvoc_category"))
        
        temp_channel = await member.guild.create_voice_channel(
            name=f"Vocal de {member.name}",
            category=category,
            user_limit=10
        )
        
        await member.move_to(temp_channel)
        
        # Suppression automatique quand vide
        await asyncio.sleep(2)
        while True:
            await asyncio.sleep(5)
            if len(temp_channel.members) == 0:
                await temp_channel.delete()
                break
    
    # Tracking temps vocal
    user_key = f"{member.guild.id}_{member.id}"
    
    if before.channel is None and after.channel:
        voice_tracking[user_key] = datetime.now()
    elif before.channel and after.channel is None:
        if user_key in voice_tracking:
            time_spent = (datetime.now() - voice_tracking[user_key]).total_seconds()
            stats_data[user_key]["voice_time"] += time_spent
            del voice_tracking[user_key]

# ============= GIVEAWAYS =============
@bot.command()
@commands.has_permissions(manage_guild=True)
async def giveaway(ctx, duration: str, *, prize):
    time_convert = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    unit = duration[-1]
    
    if unit not in time_convert:
        return await ctx.send("❌ Format invalide! Utilise: 10s, 5m, 1h, 1d")
    
    amount = int(duration[:-1])
    seconds = amount * time_convert[unit]
    
    end_time = datetime.now() + timedelta(seconds=seconds)
    
    embed = discord.Embed(
        title="🎉 GIVEAWAY!",
        description=f"**Prix:** {prize}\n**Durée:** {duration}\n**Se termine:** <t:{int(end_time.timestamp())}:R>",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Réagis avec 🎉 pour participer!")
    
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎉")
    
    giveaways_data.append({
        "channel_id": ctx.channel.id,
        "message_id": msg.id,
        "prize": prize,
        "end_time": end_time
    })

# ============= STATISTIQUES =============
@bot.command()
async def stats(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_key = f"{ctx.guild.id}_{member.id}"
    user_stats = stats_data[user_key]
    
    voice_hours = user_stats["voice_time"] / 3600
    
    embed = discord.Embed(title=f"📊 Statistiques de {member.name}", color=discord.Color.blue())
    embed.add_field(name="💬 Messages", value=user_stats["messages"], inline=True)
    embed.add_field(name="🔊 Temps vocal", value=f"{voice_hours:.1f}h", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    
    await ctx.send(embed=embed)

@bot.command()
async def leaderboard(ctx, category="money"):
    valid_categories = ["money", "messages", "voice"]
    
    if category not in valid_categories:
        return await ctx.send(f"❌ Catégories: {', '.join(valid_categories)}")
    
    embed = discord.Embed(title="🏆 Classement", color=discord.Color.gold())
    
    if category == "money":
        sorted_users = sorted(
            [(k, v) for k, v in economy_data.items() if k.startswith(f"{ctx.guild.id}_")],
            key=lambda x: x[1]["money"] + x[1]["bank"],
            reverse=True
        )[:10]
        
        for i, (user_key, data) in enumerate(sorted_users, 1):
            user_id = int(user_key.split("_")[1])
            member = ctx.guild.get_member(user_id)
            if member:
                total = data["money"] + data["bank"]
                embed.add_field(
                    name=f"{i}. {member.name}",
                    value=f"💰 {total}$",
                    inline=False
                )
    
    elif category == "messages":
        sorted_users = sorted(
            [(k, v) for k, v in stats_data.items() if k.startswith(f"{ctx.guild.id}_")],
            key=lambda x: x[1]["messages"],
            reverse=True
        )[:10]
        
        for i, (user_key, data) in enumerate(sorted_users, 1):
            user_id = int(user_key.split("_")[1])
            member = ctx.guild.get_member(user_id)
            if member:
                embed.add_field(
                    name=f"{i}. {member.name}",
                    value=f"💬 {data['messages']} messages",
                    inline=False
                )
    
    elif category == "voice":
        sorted_users = sorted(
            [(k, v) for k, v in stats_data.items() if k.startswith(f"{ctx.guild.id}_")],
            key=lambda x: x[1]["voice_time"],
            reverse=True
        )[:10]
        
        for i, (user_key, data) in enumerate(sorted_users, 1):
            user_id = int(user_key.split("_")[1])
            member = ctx.guild.get_member(user_id)
            if member:
                hours = data["voice_time"] / 3600
                embed.add_field(
                    name=f"{i}. {member.name}",
                    value=f"🔊 {hours:.1f}h",
                    inline=False
                )
    
    await ctx.send(embed=embed)

# ============= CONFIGURATION AVANCÉE =============
@bot.command()
@commands.has_permissions(administrator=True)
async def setlog(ctx, log_type: str, channel: discord.TextChannel):
    valid_types = ["modération", "membres", "messages", "vocaux", "tickets"]
    
    if log_type not in valid_types:
        return await ctx.send(f"❌ Types valides: {', '.join(valid_types)}")
    
    config = server_config[ctx.guild.id]
    config["log_channels"][log_type] = channel.id
    
    await ctx.send(f"✅ Logs **{log_type}** configurés dans {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def autorole(ctx, role: discord.Role):
    config = server_config[ctx.guild.id]
    config["autorole"] = role.id
    
    await ctx.send(f"✅ Rôle automatique configuré: {role.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setwelcome(ctx, channel: discord.TextChannel):
    config = server_config[ctx.guild.id]
    config["welcome_channel"] = channel.id
    
    await ctx.send(f"✅ Salon de bienvenue configuré: {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setleave(ctx, channel: discord.TextChannel):
    config = server_config[ctx.guild.id]
    config["leave_channel"] = channel.id
    
    await ctx.send(f"✅ Salon de départ configuré: {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def antispam(ctx, enabled: str, messages: int = 5, seconds: int = 5):
    config = server_config[ctx.guild.id]
    
    if enabled.lower() in ["on", "true", "1"]:
        config["antispam"]["enabled"] = True
        config["antispam"]["messages"] = messages
        config["antispam"]["seconds"] = seconds
        await ctx.send(f"✅ Antispam activé: {messages} messages en {seconds}s")
    else:
        config["antispam"]["enabled"] = False
        await ctx.send("✅ Antispam désactivé")

# ============= GESTION D'ERREURS =============
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Tu n'as pas les permissions pour cette commande!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant! Utilise `!help` pour plus d'infos")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignore les commandes inconnues
    else:
        await ctx.send(f"❌ Une erreur s'est produite: {error}")
        print(f"Erreur: {error}")

# ============= DÉMARRAGE DU BOT =============
if __name__ == "__main__":
    keep_alive()  # Pour Render/Replit
    TOKEN = os.getenv("DISCORD_TOKEN")  # Ton token Discord dans les variables d'environnement
    
    if not TOKEN:
        print("❌ ERREUR: Token Discord non trouvé!")
        print("📝 Crée une variable d'environnement DISCORD_TOKEN avec ton token")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"❌ Erreur au démarrage: {e}")
