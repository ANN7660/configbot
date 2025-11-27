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
        
        # Thumbnail
        if embed_data.get("thumbnail") == "member":
            embed.set_thumbnail(url=member.display_avatar.url)
        elif embed_data.get("thumbnail") == "server":
            if member.guild.icon:
                embed.set_thumbnail(url=member.guild.icon.url)
        elif embed_data.get("thumbnail"):
            embed.set_thumbnail(url=embed_data["thumbnail"])
        
        # Image
        if embed_data.get("image"):
            embed.set_image(url=embed_data["image"])
        
        # Footer
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
    
    member_count = member.guild.member_count
    
    # Variables de remplacement
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
        
        # Thumbnail
        if embed_data.get("thumbnail") == "member":
            embed.set_thumbnail(url=member.display_avatar.url)
        elif embed_data.get("thumbnail") == "server":
            if member.guild.icon:
                embed.set_thumbnail(url=member.guild.icon.url)
        elif embed_data.get("thumbnail"):
            embed.set_thumbnail(url=embed_data["thumbnail"])
        
        # Image
        if embed_data.get("image"):
            embed.set_image(url=embed_data["image"])
        
        # Footer
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

# ============= HELP COMMAND =============
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
    
    # Dropdown pour choisir une catégorie
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

# ============= CONFIG COMMAND =============
@bot.command()
@commands.has_permissions(administrator=True)
async def config(ctx):
    config = server_config[ctx.guild.id]
    
    embed = discord.Embed(
        title="⚙️ Configuration du serveur",
        description="Utilise les menus déroulants ci-dessous pour configurer le bot",
        color=discord.Color.blue()
    )
    
    welcome_ch = bot.get_channel(config["welcome_channel"]) if config["welcome_channel"] else None
    leave_ch = bot.get_channel(config["leave_channel"]) if config["leave_channel"] else None
    log_ch = bot.get_channel(config["log_channels"].get("modération")) if config["log_channels"].get("modération") else None
    autorole = ctx.guild.get_role(config["autorole"]) if config["autorole"] else None
    
    config_text = f"""📋 **Configuration actuelle**
👋 **Salon de bienvenue:** {welcome_ch.mention if welcome_ch else '# Non défini'}
👋 **Salon de départ:** {leave_ch.mention if leave_ch else '# Non défini'}
📜 **Salon de logs:** {log_ch.mention if log_ch else '# Non défini'}
👤 **Rôle automatique:** {autorole.mention if autorole else '@Non défini'}
📝 **Questionnaire:** {'✅ Activé' if config['questionnaire_active'] else '❌ Désactivé'}

📚 **Guide**
**1.** Choisis le salon de bienvenue
**2.** Choisis le salon de départ
**3.** Choisis le salon de logs
**4.** Choisis le rôle automatique
**5.** Active/désactive le questionnaire
**6.** Clique sur 💾 pour sauvegarder"""
    
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
    
    btn_questionnaire = Button(label="📝 Questionnaire", style=discord.ButtonStyle.secondary, emoji="📝")
    btn_save = Button(label="💾 Sauvegarder", style=discord.ButtonStyle.success, emoji="💾")
    
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
    view.add_item(select_leave)
    view.add_item(select_logs)
    view.add_item(select_autorole)
    view.add_item(btn_questionnaire)
    view.add_item(btn_save)
    
    await ctx.send(embed=embed, view=view)

# Continue dans partie 2...
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
    
    # Conversion de durée
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
    
    # Auto-sanctions
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

# ============= ÉCONOMIE =============
@bot.command()
async def daily(ctx):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    user = economy_data[user_key]
    
    now = datetime.now()
    if user["daily_claimed"]:
        last_claim = datetime.fromisoformat(user["daily_claimed"])
        if (now - last_claim).total_seconds() < 86400:
            time_left = timedelta(seconds=86400 - (now - last_claim).total_seconds())
            hours, remainder = divmod(time_left.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            await ctx.send(f"⏰ Reviens dans {hours}h {minutes}m {seconds}s pour ta récompense journalière!")
            return
    
    amount = random.randint(500, 1000)
    user["money"] += amount
    user["daily_claimed"] = now.isoformat()
    
    await ctx.send(f"💰 {ctx.author.mention} a reçu **{amount}$** de récompense journalière!")

@bot.command()
async def balance(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_key = f"{ctx.guild.id}_{member.id}"
    user = economy_data[user_key]
    
    embed = discord.Embed(
        title=f"💰 Argent de {member.name}",
        color=discord.Color.gold()
    )
    embed.add_field(name="💵 Argent liquide", value=f"{user['money']}$", inline=True)
    embed.add_field(name="🏦 Banque", value=f"{user['bank']}$", inline=True)
    embed.add_field(name="⭐ Réputation", value=f"{user['rep']}", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    
    await ctx.send(embed=embed)

@bot.command()
async def rep(ctx, member: discord.Member):
    if member == ctx.author:
        await ctx.send("❌ Tu ne peux pas te donner de la réputation!")
        return
    
    user_key = f"{ctx.guild.id}_{member.id}"
    economy_data[user_key]["rep"] += 1
    
    await ctx.send(f"⭐ {ctx.author.mention} a donné de la réputation à {member.mention}!")

@bot.command()
async def work(ctx):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    user = economy_data[user_key]
    
    now = datetime.now()
    if user["work_claimed"]:
        last_claim = datetime.fromisoformat(user["work_claimed"])
        if (now - last_claim).total_seconds() < 3600:
            time_left = timedelta(seconds=3600 - (now - last_claim).total_seconds())
            minutes, seconds = divmod(time_left.seconds, 60)
            await ctx.send(f"⏰ Tu es fatigué! Reviens dans {minutes}m {seconds}s!")
            return
    
    jobs = [
        ("développeur", 200, 400),
        ("streamer", 150, 350),
        ("livreur", 100, 250),
        ("serveur", 80, 200),
        ("jardinier", 50, 150)
    ]
    
    job, min_pay, max_pay = random.choice(jobs)
    amount = random.randint(min_pay, max_pay)
    user["money"] += amount
    user["work_claimed"] = now.isoformat()
    
    await ctx.send(f"💼 {ctx.author.mention} a travaillé comme **{job}** et a gagné **{amount}$**!")

@bot.command()
async def beg(ctx):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    
    if random.random() < 0.5:
        amount = random.randint(10, 50)
        economy_data[user_key]["money"] += amount
        await ctx.send(f"🙏 Quelqu'un t'a donné **{amount}$**!")
    else:
        await ctx.send("❌ Personne ne t'a donné d'argent...")

@bot.command()
async def pay(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ Montant invalide!")
        return
    
    sender_key = f"{ctx.guild.id}_{ctx.author.id}"
    receiver_key = f"{ctx.guild.id}_{member.id}"
    
    if economy_data[sender_key]["money"] < amount:
        await ctx.send("❌ Tu n'as pas assez d'argent!")
        return
    
    economy_data[sender_key]["money"] -= amount
    economy_data[receiver_key]["money"] += amount
    
    await ctx.send(f"💸 {ctx.author.mention} a payé **{amount}$** à {member.mention}!")

@bot.command()
async def rob(ctx, member: discord.Member):
    if member == ctx.author:
        await ctx.send("❌ Tu ne peux pas te voler toi-même!")
        return
    
    robber_key = f"{ctx.guild.id}_{ctx.author.id}"
    victim_key = f"{ctx.guild.id}_{member.id}"
    
    victim_money = economy_data[victim_key]["money"]
    
    if victim_money < 100:
        await ctx.send(f"❌ {member.mention} n'a pas assez d'argent à voler!")
        return
    
    if random.random() < 0.5:
        amount = random.randint(50, min(victim_money, 500))
        economy_data[robber_key]["money"] += amount
        economy_data[victim_key]["money"] -= amount
        await ctx.send(f"💰 {ctx.author.mention} a volé **{amount}$** à {member.mention}!")
    else:
        fine = random.randint(100, 300)
        economy_data[robber_key]["money"] = max(0, economy_data[robber_key]["money"] - fine)
        await ctx.send(f"🚔 {ctx.author.mention} s'est fait attraper! Amende: **{fine}$**")

# ============= FUN & JEUX =============
@bot.command(name="8ball")
async def eight_ball(ctx, *, question):
    responses = [
        "✅ Oui, absolument!",
        "✅ C'est certain!",
        "✅ Sans aucun doute!",
        "🤔 Probablement...",
        "🤔 Peut-être...",
        "❌ Je ne pense pas...",
        "❌ Non, définitivement pas!",
        "❌ Très peu probable..."
    ]
    
    await ctx.send(f"🎱 Question: {question}\n💬 Réponse: {random.choice(responses)}")

@bot.command()
async def joke(ctx):
    jokes = [
        "Pourquoi les plongeurs plongent-ils toujours en arrière et jamais en avant ? Parce que sinon ils tombent dans le bateau ! 😂",
        "Qu'est-ce qu'un crocodile qui surveille une maison ? Un Lacoste garde ! 🐊",
        "Comment appelle-t-on un chat tombé dans un pot de peinture le jour de Noël ? Un chat-peint de Noël ! 🎅",
        "Qu'est-ce qu'un cannibale ? Quelqu'un qui en a marre de la salade ! 😱"
    ]
    
    await ctx.send(random.choice(jokes))

@bot.command()
async def coinflip(ctx):
    result = random.choice(["Pile", "Face"])
    await ctx.send(f"🪙 {result}!")

@bot.command()
async def dice(ctx, bet: int = 0):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    dice_result = random.randint(1, 6)
    
    if bet > 0:
        if economy_data[user_key]["money"] < bet:
            await ctx.send("❌ Tu n'as pas assez d'argent!")
            return
        
        if dice_result >= 4:
            economy_data[user_key]["money"] += bet
            await ctx.send(f"🎲 Tu as fait **{dice_result}**! Tu gagnes **{bet}$**! 💰")
        else:
            economy_data[user_key]["money"] -= bet
            await ctx.send(f"🎲 Tu as fait **{dice_result}**! Tu perds **{bet}$**! 😢")
    else:
        await ctx.send(f"🎲 Tu as fait **{dice_result}**!")

@bot.command()
async def rps(ctx, choice: str):
    choices = ["pierre", "papier", "ciseaux"]
    choice = choice.lower()
    
    if choice not in choices:
        await ctx.send("❌ Choix invalide! (pierre/papier/ciseaux)")
        return
    
    bot_choice = random.choice(choices)
    
    emojis = {"pierre": "🪨", "papier": "📄", "ciseaux": "✂️"}
    
    result = ""
    if choice == bot_choice:
        result = "🤝 Égalité!"
    elif (choice == "pierre" and bot_choice == "ciseaux") or \
         (choice == "papier" and bot_choice == "pierre") or \
         (choice == "ciseaux" and bot_choice == "papier"):
        result = "🎉 Tu gagnes!"
    else:
        result = "😢 Tu perds!"
    
    await ctx.send(f"{emojis[choice]} vs {emojis[bot_choice]}\n{result}")

# Continue dans partie 3...
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
    
    # Conversion de durée
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
    
    # Auto-sanctions
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

# ============= ÉCONOMIE =============
@bot.command()
async def daily(ctx):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    user = economy_data[user_key]
    
    now = datetime.now()
    if user["daily_claimed"]:
        last_claim = datetime.fromisoformat(user["daily_claimed"])
        if (now - last_claim).total_seconds() < 86400:
            time_left = timedelta(seconds=86400 - (now - last_claim).total_seconds())
            hours, remainder = divmod(time_left.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            await ctx.send(f"⏰ Reviens dans {hours}h {minutes}m {seconds}s pour ta récompense journalière!")
            return
    
    amount = random.randint(500, 1000)
    user["money"] += amount
    user["daily_claimed"] = now.isoformat()
    
    await ctx.send(f"💰 {ctx.author.mention} a reçu **{amount}$** de récompense journalière!")

@bot.command()
async def balance(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_key = f"{ctx.guild.id}_{member.id}"
    user = economy_data[user_key]
    
    embed = discord.Embed(
        title=f"💰 Argent de {member.name}",
        color=discord.Color.gold()
    )
    embed.add_field(name="💵 Argent liquide", value=f"{user['money']}$", inline=True)
    embed.add_field(name="🏦 Banque", value=f"{user['bank']}$", inline=True)
    embed.add_field(name="⭐ Réputation", value=f"{user['rep']}", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    
    await ctx.send(embed=embed)

@bot.command()
async def rep(ctx, member: discord.Member):
    if member == ctx.author:
        await ctx.send("❌ Tu ne peux pas te donner de la réputation!")
        return
    
    user_key = f"{ctx.guild.id}_{member.id}"
    economy_data[user_key]["rep"] += 1
    
    await ctx.send(f"⭐ {ctx.author.mention} a donné de la réputation à {member.mention}!")

@bot.command()
async def work(ctx):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    user = economy_data[user_key]
    
    now = datetime.now()
    if user["work_claimed"]:
        last_claim = datetime.fromisoformat(user["work_claimed"])
        if (now - last_claim).total_seconds() < 3600:
            time_left = timedelta(seconds=3600 - (now - last_claim).total_seconds())
            minutes, seconds = divmod(time_left.seconds, 60)
            await ctx.send(f"⏰ Tu es fatigué! Reviens dans {minutes}m {seconds}s!")
            return
    
    jobs = [
        ("développeur", 200, 400),
        ("streamer", 150, 350),
        ("livreur", 100, 250),
        ("serveur", 80, 200),
        ("jardinier", 50, 150)
    ]
    
    job, min_pay, max_pay = random.choice(jobs)
    amount = random.randint(min_pay, max_pay)
    user["money"] += amount
    user["work_claimed"] = now.isoformat()
    
    await ctx.send(f"💼 {ctx.author.mention} a travaillé comme **{job}** et a gagné **{amount}$**!")

@bot.command()
async def beg(ctx):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    
    if random.random() < 0.5:
        amount = random.randint(10, 50)
        economy_data[user_key]["money"] += amount
        await ctx.send(f"🙏 Quelqu'un t'a donné **{amount}$**!")
    else:
        await ctx.send("❌ Personne ne t'a donné d'argent...")

@bot.command()
async def pay(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ Montant invalide!")
        return
    
    sender_key = f"{ctx.guild.id}_{ctx.author.id}"
    receiver_key = f"{ctx.guild.id}_{member.id}"
    
    if economy_data[sender_key]["money"] < amount:
        await ctx.send("❌ Tu n'as pas assez d'argent!")
        return
    
    economy_data[sender_key]["money"] -= amount
    economy_data[receiver_key]["money"] += amount
    
    await ctx.send(f"💸 {ctx.author.mention} a payé **{amount}$** à {member.mention}!")

@bot.command()
async def rob(ctx, member: discord.Member):
    if member == ctx.author:
        await ctx.send("❌ Tu ne peux pas te voler toi-même!")
        return
    
    robber_key = f"{ctx.guild.id}_{ctx.author.id}"
    victim_key = f"{ctx.guild.id}_{member.id}"
    
    victim_money = economy_data[victim_key]["money"]
    
    if victim_money < 100:
        await ctx.send(f"❌ {member.mention} n'a pas assez d'argent à voler!")
        return
    
    if random.random() < 0.5:
        amount = random.randint(50, min(victim_money, 500))
        economy_data[robber_key]["money"] += amount
        economy_data[victim_key]["money"] -= amount
        await ctx.send(f"💰 {ctx.author.mention} a volé **{amount}$** à {member.mention}!")
    else:
        fine = random.randint(100, 300)
        economy_data[robber_key]["money"] = max(0, economy_data[robber_key]["money"] - fine)
        await ctx.send(f"🚔 {ctx.author.mention} s'est fait attraper! Amende: **{fine}$**")

# ============= FUN & JEUX =============
@bot.command(name="8ball")
async def eight_ball(ctx, *, question):
    responses = [
        "✅ Oui, absolument!",
        "✅ C'est certain!",
        "✅ Sans aucun doute!",
        "🤔 Probablement...",
        "🤔 Peut-être...",
        "❌ Je ne pense pas...",
        "❌ Non, définitivement pas!",
        "❌ Très peu probable..."
    ]
    
    await ctx.send(f"🎱 Question: {question}\n💬 Réponse: {random.choice(responses)}")

@bot.command()
async def joke(ctx):
    jokes = [
        "Pourquoi les plongeurs plongent-ils toujours en arrière et jamais en avant ? Parce que sinon ils tombent dans le bateau ! 😂",
        "Qu'est-ce qu'un crocodile qui surveille une maison ? Un Lacoste garde ! 🐊",
        "Comment appelle-t-on un chat tombé dans un pot de peinture le jour de Noël ? Un chat-peint de Noël ! 🎅",
        "Qu'est-ce qu'un cannibale ? Quelqu'un qui en a marre de la salade ! 😱"
    ]
    
    await ctx.send(random.choice(jokes))

@bot.command()
async def coinflip(ctx):
    result = random.choice(["Pile", "Face"])
    await ctx.send(f"🪙 {result}!")

@bot.command()
async def dice(ctx, bet: int = 0):
    user_key = f"{ctx.guild.id}_{ctx.author.id}"
    dice_result = random.randint(1, 6)
    
    if bet > 0:
        if economy_data[user_key]["money"] < bet:
            await ctx.send("❌ Tu n'as pas assez d'argent!")
            return
        
        if dice_result >= 4:
            economy_data[user_key]["money"] += bet
            await ctx.send(f"🎲 Tu as fait **{dice_result}**! Tu gagnes **{bet}$**! 💰")
        else:
            economy_data[user_key]["money"] -= bet
            await ctx.send(f"🎲 Tu as fait **{dice_result}**! Tu perds **{bet}$**! 😢")
    else:
        await ctx.send(f"🎲 Tu as fait **{dice_result}**!")

@bot.command()
async def rps(ctx, choice: str):
    choices = ["pierre", "papier", "ciseaux"]
    choice = choice.lower()
    
    if choice not in choices:
        await ctx.send("❌ Choix invalide! (pierre/papier/ciseaux)")
        return
    
    bot_choice = random.choice(choices)
    
    emojis = {"pierre": "🪨", "papier": "📄", "ciseaux": "✂️"}
    
    result = ""
    if choice == bot_choice:
        result = "🤝 Égalité!"
    elif (choice == "pierre" and bot_choice == "ciseaux") or \
         (choice == "papier" and bot_choice == "pierre") or \
         (choice == "ciseaux" and bot_choice == "papier"):
        result = "🎉 Tu gagnes!"
    else:
        result = "😢 Tu perds!"
    
    await ctx.send(f"{emojis[choice]} vs {emojis[bot_choice]}\n{result}")

# ============= UTILITAIRES =============
@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    
    roles = [role.mention for role in member.roles[1:]]
    roles_str = ", ".join(roles) if roles else "Aucun rôle"
    
    embed = discord.Embed(
        title=f"📋 Info sur {member.name}",
        color=member.color
    )
    
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Nom", value=member.name, inline=True)
    embed.add_field(name="🆔 ID", value=member.id, inline=True)
    embed.add_field(name="📅 Compte créé", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="📥 A rejoint", value=member.joined_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="👑 Rôle principal", value=member.top_role.mention, inline=True)
    embed.add_field(name="🎭 Rôles", value=roles_str, inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    
    embed = discord.Embed(
        title=f"📊 Info sur {guild.name}",
        color=discord.Color.blue()
    )
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.add_field(name="👑 Propriétaire", value=guild.owner.mention, inline=True)
    embed.add_field(name="🆔 ID", value=guild.id, inline=True)
    embed.add_field(name="📅 Créé le", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="👥 Membres", value=guild.member_count, inline=True)
    embed.add_field(name="💬 Salons texte", value=len(guild.text_channels), inline=True)
    embed.add_field(name="🔊 Salons vocaux", value=len(guild.voice_channels), inline=True)
    embed.add_field(name="🎭 Rôles", value=len(guild.roles), inline=True)
    embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    
    embed = discord.Embed(
        title=f"🖼️ Avatar de {member.name}",
        color=member.color
    )
    embed.set_image(url=member.display_avatar.url)
    
    await ctx.send(embed=embed)

@bot.command()
async def poll(ctx, *, args):
    try:
        parts = args.split("|")
        question = parts[0].strip()
        options = [opt.strip() for opt in parts[1:]]
        
        if len(options) < 2:
            await ctx.send("❌ Tu dois fournir au moins 2 options!")
            return
        
        if len(options) > 10:
            await ctx.send("❌ Maximum 10 options!")
            return
        
        embed = discord.Embed(
            title="📊 Sondage",
            description=f"**{question}**\n\n" + "\n".join([f"{chr(127462 + i)} {opt}" for i, opt in enumerate(options)]),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Sondage créé par {ctx.author.name}")
        
        msg = await ctx.send(embed=embed)
        
        for i in range(len(options)):
            await msg.add_reaction(chr(127462 + i))
        
    except Exception as e:
        await ctx.send(f"❌ Format invalide! Utilise: `!poll Question | Option1 | Option2`")

@bot.command()
async def remind(ctx, duration: str, *, message):
    time_convert = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    
    try:
        amount = int(duration[:-1])
        unit = duration[-1]
        
        if unit not in time_convert:
            await ctx.send("❌ Durée invalide! Utilise: 10s, 5m, 1h, 1d")
            return
        
        sleep_time = amount * time_convert[unit]
        
        await ctx.send(f"⏰ Rappel défini pour dans {duration}!")
        await asyncio.sleep(sleep_time)
        await ctx.send(f"🔔 {ctx.author.mention} **Rappel:** {message}")
        
    except Exception as e:
        await ctx.send("❌ Format invalide! Utilise: `!remind 5m Mon message`")

@bot.command()
async def timer(ctx, time: str, *, reason="Timer"):
    time_convert = {"s": 1, "m": 60, "h": 3600}
    
    try:
        amount = int(time[:-1])
        unit = time[-1]
        
        if unit not in time_convert:
            await ctx.send("❌ Durée invalide! Utilise: 10s, 5m, 1h")
            return
        
        sleep_time = amount * time_convert[unit]
        
        embed = discord.Embed(
            title="⏱️ Timer démarré",
            description=f"**{reason}**\nDurée: {time}",
            color=discord.Color.green()
        )
        
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(sleep_time)
        
        embed.title = "⏰ Timer terminé!"
        embed.color = discord.Color.red()
        
        await msg.edit(embed=embed)
        await ctx.send(f"🔔 {ctx.author.mention} Timer **{reason}** terminé!")
        
    except Exception as e:
        await ctx.send("❌ Format invalide! Utilise: `!timer 5m Raison`")

@bot.command()
async def stats(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_key = f"{ctx.guild.id}_{member.id}"
    stats = stats_data[user_key]
    
    voice_hours = int(stats["voice_time"] // 3600)
    voice_minutes = int((stats["voice_time"] % 3600) // 60)
    
    embed = discord.Embed(
        title=f"📊 Statistiques de {member.name}",
        color=discord.Color.purple()
    )
    
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="💬 Messages envoyés", value=stats["messages"], inline=True)
    embed.add_field(name="🔊 Temps vocal", value=f"{voice_hours}h {voice_minutes}m", inline=True)
    
    if stats["last_message"]:
        embed.add_field(name="📝 Dernier message", value=stats["last_message"].strftime("%d/%m/%Y %H:%M"), inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def leaderboard(ctx, category: str = "messages"):
    guild_users = {}
    
    for key, data in stats_data.items():
        guild_id, user_id = key.split("_")
        if int(guild_id) == ctx.guild.id:
            guild_users[int(user_id)] = data
    
    if category == "messages":
        sorted_users = sorted(guild_users.items(), key=lambda x: x[1]["messages"], reverse=True)[:10]
        title = "💬 Top Messages"
        value_key = "messages"
    elif category == "voice":
        sorted_users = sorted(guild_users.items(), key=lambda x: x[1]["voice_time"], reverse=True)[:10]
        title = "🔊 Top Vocal"
        value_key = "voice_time"
    else:
        await ctx.send("❌ Catégorie invalide! Utilise: messages ou voice")
        return
    
    embed = discord.Embed(
        title=f"🏆 {title}",
        color=discord.Color.gold()
    )
    
    for i, (user_id, data) in enumerate(sorted_users, 1):
        member = ctx.guild.get_member(user_id)
        if member:
            if value_key == "voice_time":
                hours = int(data[value_key] // 3600)
                minutes = int((data[value_key] % 3600) // 60)
                value = f"{hours}h {minutes}m"
            else:
                value = data[value_key]
            
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**#{i}**"
            embed.add_field(name=f"{medal} {member.name}", value=value, inline=False)
    
    await ctx.send(embed=embed)

# ============= BIENVENUE/DÉPART =============
@bot.command()
@commands.has_permissions(administrator=True)
async def bvntext(ctx, *, message):
    server_config[ctx.guild.id]["welcome_text"] = message
    server_config[ctx.guild.id]["welcome_embed"] = None
    
    await ctx.send(f"✅ Message de bienvenue configuré!\nVariables: `{{user}}`, `{{server}}`, `{{count}}`")

@bot.command()
@commands.has_permissions(administrator=True)
async def bvnembed(ctx):
    embed = discord.Embed(
        title="🎨 Configuration de l'embed de bienvenue",
        description="Réponds aux questions suivantes pour créer ton embed personnalisé",
        color=discord.Color.green()
    )
    
    await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        await ctx.send("📝 **Titre de l'embed** (ou 'skip'):")
        title_msg = await bot.wait_for('message', check=check, timeout=60)
        title = title_msg.content if title_msg.content.lower() != "skip" else "Bienvenue!"
        
        await ctx.send("📝 **Description** (Variables: {user}, {server}, {count}) (ou 'skip'):")
        desc_msg = await bot.wait_for('message', check=check, timeout=60)
        description = desc_msg.content if desc_msg.content.lower() != "skip" else ""
        
        await ctx.send("🎨 **Couleur** (green/blue/red/purple/gold) (ou 'skip'):")
        color_msg = await bot.wait_for('message', check=check, timeout=60)
        color = color_msg.content.lower() if color_msg.content.lower() != "skip" else "green"
        
        await ctx.send("🖼️ **Thumbnail** (member/server/url) (ou 'skip'):")
        thumb_msg = await bot.wait_for('message', check=check, timeout=60)
        thumbnail = thumb_msg.content if thumb_msg.content.lower() != "skip" else None
        
        await ctx.send("📷 **Image URL** (ou 'skip'):")
        img_msg = await bot.wait_for('message', check=check, timeout=60)
        image = img_msg.content if img_msg.content.lower() != "skip" else None
        
        await ctx.send("👣 **Footer** (ou 'skip'):")
        footer_msg = await bot.wait_for('message', check=check, timeout=60)
        footer = footer_msg.content if footer_msg.content.lower() != "skip" else None
        
        server_config[ctx.guild.id]["welcome_embed"] = {
            "title": title,
            "description": description,
            "color": color,
            "thumbnail": thumbnail,
            "image": image,
            "footer": footer
        }
        
        server_config[ctx.guild.id]["welcome_text"] = None
        
        await ctx.send("✅ Embed de bienvenue configuré avec succès!")
        
    except asyncio.TimeoutError:
        await ctx.send("❌ Temps écoulé! Configuration annulée.")

@bot.command()
@commands.has_permissions(administrator=True)
async def leavetext(ctx, *, message):
    server_config[ctx.guild.id]["leave_text"] = message
    server_config[ctx.guild.id]["leave_embed"] = None
    
    await ctx.send(f"✅ Message de départ configuré!\nVariables: `{{user}}`, `{{server}}`, `{{count}}`")

@bot.command()
@commands.has_permissions(administrator=True)
async def leaveembed(ctx):
    embed = discord.Embed(
        title="🎨 Configuration de l'embed de départ",
        description="Réponds aux questions suivantes pour créer ton embed personnalisé",
        color=discord.Color.red()
    )
    
    await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        await ctx.send("📝 **Titre de l'embed** (ou 'skip'):")
        title_msg = await bot.wait_for('message', check=check, timeout=60)
        title = title_msg.content if title_msg.content.lower() != "skip" else "Au revoir!"
        
        await ctx.send("📝 **Description** (Variables: {user}, {server}, {count}) (ou 'skip'):")
        desc_msg = await bot.wait_for('message', check=check, timeout=60)
        description = desc_msg.content if desc_msg.content.lower() != "skip" else ""
        
        await ctx.send("🎨 **Couleur** (green/blue/red/purple/gold) (ou 'skip'):")
        color_msg = await bot.wait_for('message', check=check, timeout=60)
        color = color_msg.content.lower() if color_msg.content.lower() != "skip" else "red"
        
        await ctx.send("🖼️ **Thumbnail** (member/server/url) (ou 'skip'):")
        thumb_msg = await bot.wait_for('message', check=check, timeout=60)
        thumbnail = thumb_msg.content if thumb_msg.content.lower() != "skip" else None
        
        await ctx.send("📷 **Image URL** (ou 'skip'):")
        img_msg = await bot.wait_for('message', check=check, timeout=60)
        image = img_msg.content if img_msg.content.lower() != "skip" else None
        
        await ctx.send("👣 **Footer** (ou 'skip'):")
        footer_msg = await bot.wait_for('message', check=check, timeout=60)
        footer = footer_msg.content if footer_msg.content.lower() != "skip" else None
        
        server_config[ctx.guild.id]["leave_embed"] = {
            "title": title,
            "description": description,
            "color": color,
            "thumbnail": thumbnail,
            "image": image,
            "footer": footer
        }
        
        server_config[ctx.guild.id]["leave_text"] = None
        
        await ctx.send("✅ Embed de départ configuré avec succès!")
        
    except asyncio.TimeoutError:
        await ctx.send("❌ Temps écoulé! Configuration annulée.")

@bot.command()
@commands.has_permissions(administrator=True)
async def setwelcome(ctx, channel: discord.TextChannel):
    server_config[ctx.guild.id]["welcome_channel"] = channel.id
    await ctx.send(f"✅ Salon de bienvenue défini: {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setleave(ctx, channel: discord.TextChannel):
    server_config[ctx.guild.id]["leave_channel"] = channel.id
    await ctx.send(f"✅ Salon de départ défini: {channel.mention}")

# ============= SYSTÈMES =============
@bot.command()
@commands.has_permissions(administrator=True)
async def ticketsetup(ctx):
    embed = discord.Embed(
        title="🎫 Système de Tickets",
        description="Clique sur le bouton ci-dessous pour créer un ticket",
        color=discord.Color.blue()
    )
    
    button = Button(label="📩 Créer un ticket", style=discord.ButtonStyle.primary, emoji="🎫")
    
    async def button_callback(interaction: discord.Interaction):
        config = server_config[interaction.guild.id]
        config["ticket_counter"] += 1
        
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{config['ticket_counter']}",
            category=interaction.guild.get_channel(config.get("ticket_category"))
        )
        
        await ticket_channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        await ticket_channel.set_permissions(interaction.guild.default_role, read_messages=False)
        
        ticket_embed = discord.Embed(
            title="🎫 Nouveau Ticket",
            description=f"Bienvenue {interaction.user.mention}!\nUn membre du staff va bientôt vous répondre.",
            color=discord.Color.green()
        )
        
        close_button = Button(label="🔒 Fermer", style=discord.ButtonStyle.danger)
        
        async def close_callback(inter: discord.Interaction):
            await ticket_channel.delete()
        
        close_button.callback = close_callback
        
        close_view = View(timeout=None)
        close_view.add_item(close_button)
        
        await ticket_channel.send(embed=ticket_embed, view=close_view)
        await interaction.response.send_message(f"✅ Ticket créé: {ticket_channel.mention}", ephemeral=True)
    
    button.callback = button_callback
    
    view = View(timeout=None)
    view.add_item(button)
    
    await ctx.send(embed=embed, view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def tempvoc(ctx, channel: discord.VoiceChannel):
    config = server_config[ctx.guild.id]
    config["tempvoc_channel"] = channel.id
    config["tempvoc_category"] = channel.category_id
    
    await ctx.send(f"✅ Vocal temporaire configuré: {channel.mention}\nLes utilisateurs qui rejoignent ce salon auront leur propre vocal!")

@bot.command()
@commands.has_permissions(administrator=True)
async def giveaway(ctx, duration: str, *, prize):
    time_convert = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    
    try:
        amount = int(duration[:-1])
        unit = duration[-1]
        
        if unit not in time_convert:
            await ctx.send("❌ Durée invalide! Utilise: 10s, 5m, 1h, 1d")
            return
        
        sleep_time = amount * time_convert[unit]
        end_time = datetime.now() + timedelta(seconds=sleep_time)
        
        embed = discord.Embed(
            title="🎉 GIVEAWAY!",
            description=f"**Prix:** {prize}\n**Durée:** {duration}\n**Fin:** {end_time.strftime('%d/%m/%Y %H:%M')}\n\nRéagis avec 🎉 pour participer!",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Organisé par {ctx.author.name}")
        
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("🎉")
        
        giveaways_data.append({
            "message_id": msg.id,
            "channel_id": ctx.channel.id,
            "end_time": end_time,
            "prize": prize
        })
        
    except Exception as e:
        await ctx.send("❌ Format invalide! Utilise: `!giveaway 1d Prix du giveaway`")

@bot.command()
@commands.has_permissions(administrator=True)
async def setlog(ctx, log_type: str, channel: discord.TextChannel):
    valid_types = ["modération", "membres", "messages", "vocal"]
    
    if log_type not in valid_types:
        await ctx.send(f"❌ Type invalide! Types disponibles: {', '.join(valid_types)}")
        return
    
    server_config[ctx.guild.id]["log_channels"][log_type] = channel.id
    await ctx.send(f"✅ Logs **{log_type}** configurés dans {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def autorole(ctx, role: discord.Role):
    server_config[ctx.guild.id]["autorole"] = role.id
    await ctx.send(f"✅ Rôle automatique défini: {role.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def antispam(ctx, status: str):
    if status.lower() not in ["on", "off"]:
        await ctx.send("❌ Utilise: `!antispam on` ou `!antispam off`")
        return
    
    server_config[ctx.guild.id]["antispam"]["enabled"] = (status.lower() == "on")
    
    await ctx.send(f"✅ Antispam {'activé' if status.lower() == 'on' else 'désactivé'}!")

# ============= LANCEMENT DU BOT =============
if __name__ == "__main__":
    keep_alive()
    
    # Remplace "TON_TOKEN" par ton vrai token Discord
    TOKEN = os.environ.get("DISCORD_TOKEN") or "TON_TOKEN"
    
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        print("Vérifie que ton token est correct!")
