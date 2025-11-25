import os
import discord
from discord.ext import commands, tasks
from discord import ui
from datetime import datetime, timedelta
import random
import re
import asyncio
import time
from pyfiglet import Figlet
import inspect

# --- VARIABLES D'ÉTAT (Nécessaires pour ces commandes) ---
# Si ces variables n'ont pas été remplies depuis le début du script,
# assurez-vous de les copier/coller depuis la partie originale,
# en particulier les IDs de configuration.

# Configuration des seuils/réponses
BALL_RESPONSES = ["Absolument.", "Sans aucun doute.", "Oui, définitivement.", "Peu probable.", "N'y compte pas.", "Demande plus tard."]
JOKES = ["Pourquoi les poissons vivent-ils dans l'eau salée ? Parce que le poivre, ça les fait éternuer !", "Que dit un informaticien quand il s'ennuie ? 'Je me fais ch** à bits!'"]
QUOTES = ["La seule façon de faire du bon travail est d'aimer ce que vous faites. - Steve Jobs", "Vis comme si tu devais mourir demain. Apprends comme si tu devais vivre toujours. - Gandhi"]

LOG_CHANNEL_ID = 123456789012345670 
WELCOME_CHANNEL_ID = 123456789012345671
DEFAULT_ROLE_ID = 123456789012345672
TICKET_CATEGORY_ID = 123456789012345673 
VOICE_CHANNEL_CREATOR_ID = 123456789012345675 
PIN_REACTION_EMOJI = '📌'
INVITE_LINK = "VOTRE LIEN D'INVITATION ICI"

# Variables de Cooldowns et XP (pour les fonctions d'info/stats)
XP_PER_MESSAGE = 15
XP_COOLDOWN = 60
DAILY_COOLDOWN = 86400
REP_COOLDOWN = 86400
LEVEL_ROLES_MAP = {5: 123456789012345680}
SHOP_ROLES = {123456789012345683: 5000}

# Variables d'état
USER_XP = {}
USER_LAST_MESSAGE = {}
USER_LAST_DAILY = {}
USER_LAST_REP = {}
USER_WARNINGS = {}
TICKET_CHANNELS = {}
TEMP_VOICE_CHANNELS = {}
USER_NAME_HISTORY = {} 

SERVER_CONFIG = {
    'welcome_channel_id': WELCOME_CHANNEL_ID,
    'log_channel_id': LOG_CHANNEL_ID,
    'default_role_id': DEFAULT_ROLE_ID,
    'ticket_category_id': TICKET_CATEGORY_ID,
    'voice_channel_creator_id': VOICE_CHANNEL_CREATOR_ID,
    'welcome_type': 'text',
    'welcome_message': "👋 Bienvenue {user.mention} ! Nous sommes {member_count} sur {guild.name}.", 
    'leave_type': 'text',
    'leave_message': "🚪 Au revoir {user.name}. Il nous reste {member_count} membres.",
}
START_TIME = time.time()
TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = '!'
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# --- FONCTIONS UTILITAIRES (Incluses dans la partie 1) ---
def get_level_threshold(level): return 5 * (level ** 2) + 50 * level + 100
def get_user_data(user_id):
    if user_id not in USER_XP:
        USER_XP[user_id] = {'xp': 0, 'level': 1, 'currency': 100, 'rep': 0}
    return USER_XP[user_id]
async def get_channel_safe(guild, channel_id):
    if channel_id and channel_id in [c.id for c in guild.channels]: return guild.get_channel(channel_id)
    return None
async def send_log_embed(guild, title, color, fields):
    log_channel = await get_channel_safe(guild, SERVER_CONFIG.get('log_channel_id', LOG_CHANNEL_ID))
    if log_channel:
        embed = discord.Embed(title=title, color=color, timestamp=datetime.now())
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
        await log_channel.send(embed=embed)
        
def format_message(template, member, guild, is_join):
    """Remplace les placeholders dans un template de message ou embed."""
    message = template.replace("{user.mention}", member.mention)
    message = message.replace("{user.name}", member.display_name)
    message = message.replace("{guild.name}", guild.name)
    member_count = guild.member_count 
    message = message.replace("{member_count}", str(member_count)) 
    return message

def format_timedelta(td: timedelta):
    """Formate un timedelta en jours, heures, minutes et secondes."""
    seconds = int(td.total_seconds())
    periods = [
        ('jour', 60*60*24),
        ('heure', 60*60),
        ('minute', 60),
        ('seconde', 1)
    ]
    
    parts = []
    for name, secs in periods:
        if seconds >= secs:
            value, seconds = divmod(seconds, secs)
            parts.append(f"{value} {name}{'s' if value > 1 else ''}")
    return ", ".join(parts) or "Moins d'une seconde"


# --- COMMANDES D'INFO & UTILITAIRES (Suite) ---

@bot.command(name='userinfo')
async def user_info(ctx, member: discord.Member = None):
    """Affiche un Embed complet sur l'utilisateur : rôles, niveau, monnaie, date d'arrivée, âge du compte, warnings."""
    member = member or ctx.author
    user_id = str(member.id)
    data = get_user_data(user_id)
    warnings = USER_WARNINGS.get(user_id, [])

    # Ancienneté
    account_age = datetime.now(member.created_at.tzinfo) - member.created_at
    join_age = datetime.now(member.joined_at.tzinfo) - member.joined_at

    embed = discord.Embed(
        title=f"👤 Informations sur {member.display_name}",
        color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
        timestamp=datetime.now()
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    # Statistiques personnalisées
    embed.add_field(name="🚀 Niveau & XP", value=f"**Niveau:** {data['level']}\n**XP:** {data['xp']}/{get_level_threshold(data['level'])}\n**Monnaie:** {data['currency']} 💰\n**Réputation:** {data['rep']} ⭐", inline=False)
    
    # Dates
    embed.add_field(name="🕰️ Ancienneté du Compte", value=f"Créé le <t:{int(member.created_at.timestamp())}:D>\nIl y a {format_timedelta(account_age)}", inline=True)
    embed.add_field(name="🚪 Arrivée sur le Serveur", value=f"Rejoint le <t:{int(member.joined_at.timestamp())}:D>\nIl y a {format_timedelta(join_age)}", inline=True)
    
    # Rôles et Warnings
    roles = [role.mention for role in member.roles if role.name != "@everyone"]
    embed.add_field(name=f"🛡️ Rôles ({len(roles)})", value=' '.join(roles[:5]) + ('...' if len(roles) > 5 else '') or "Aucun rôle spécial.", inline=False)
    embed.add_field(name="⚠️ Warnings", value=f"Total: **{len(warnings)}**", inline=True)
    embed.add_field(name="ID", value=f"`{member.id}`", inline=True)

    await ctx.send(embed=embed)


@bot.command(name='serverinfo')
async def server_info(ctx):
    """Affiche les statistiques du serveur (nombre de membres, rôles, salons, créateur, date de création)."""
    guild = ctx.guild
    
    embed = discord.Embed(
        title=f"🏛️ Statistiques du Serveur : {guild.name}",
        color=discord.Color.gold(),
        timestamp=datetime.now()
    )
    
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    
    # Infos générales
    embed.add_field(name="Créateur", value=guild.owner.mention if guild.owner else "Inconnu", inline=True)
    embed.add_field(name="ID du Serveur", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="Date de Création", value=f"<t:{int(guild.created_at.timestamp())}:D>", inline=True)

    # Membres et Salons
    members = len([m for m in guild.members if not m.bot])
    bots = len([m for m in guild.members if m.bot])
    embed.add_field(name="Total Membres", value=f"**{guild.member_count}** ({members} humains / {bots} bots)", inline=True)
    embed.add_field(name="Salons (Total)", value=f"{len(guild.channels)}", inline=True)
    embed.add_field(name="Rôles", value=f"{len(guild.roles)}", inline=True)

    # Niveaux de vérification/boost
    boost_status = f"{guild.premium_subscription_count} boosts (Niv. {guild.premium_tier})" if guild.premium_subscription_count else "Aucun boost"
    embed.add_field(name="Boosts", value=boost_status, inline=True)

    await ctx.send(embed=embed)

@bot.command(name='poll')
@commands.has_permissions(manage_messages=True)
async def create_poll(ctx, question: str, *options_raw):
    """Crée un sondage interactif avec des réactions pour voter. Utilisation: !poll <question> | <option1> | <option2>..."""
    
    options = question.split('|')
    if len(options) < 3:
        return await ctx.send("❌ Format invalide. Utilisez: `!poll <question> | <option1> | <option2>...`", delete_after=15)

    question_text = options[0].strip()
    poll_options = [opt.strip() for opt in options[1:] if opt.strip()]
    
    if len(poll_options) > 10:
        return await ctx.send("❌ Limite de 10 options pour le sondage.", delete_after=10)

    emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    
    description = ""
    for i, option in enumerate(poll_options):
        description += f"{emojis[i]} : **{option}**\n"

    embed = discord.Embed(
        title=f"🗳️ Sondage : {question_text}",
        description=description,
        color=discord.Color.purple(),
        timestamp=datetime.now()
    )
    embed.set_footer(text=f"Sondage lancé par {ctx.author.display_name}")

    poll_message = await ctx.send(embed=embed)
    await ctx.message.delete()

    for i in range(len(poll_options)):
        await poll_message.add_reaction(emojis[i])

@bot.command(name='avatar', aliases=['pfp'])
async def display_avatar(ctx, member: discord.Member = None):
    """Affiche la photo de profil (avatar) d'un membre en grande taille."""
    member = member or ctx.author
    
    embed = discord.Embed(
        title=f"🖼️ Avatar de {member.display_name}",
        color=discord.Color.dark_purple()
    )
    embed.set_image(url=member.display_avatar.url)
    embed.set_footer(text=f"Demandé par {ctx.author.display_name}")
    
    await ctx.send(embed=embed)

# La commande !firstmsg a été définie dans la partie précédente mais si elle est demandée à nouveau :
@bot.command(name='firstmsg')
async def get_first_message(ctx, channel: discord.TextChannel = None):
    """Trouve et affiche le tout premier message envoyé dans le salon actuel (utile pour les archives)."""
    channel = channel or ctx.channel
    try:
        async for message in channel.history(limit=1, oldest_first=True):
            first_message = message
            break
        else:
            return await ctx.send(f"❌ Impossible de trouver le premier message dans {channel.mention}.", delete_after=10)

        embed = discord.Embed(
            title=f"🗓️ Premier Message dans #{channel.name}",
            description=f"[Cliquer ici pour voir le message original]({first_message.jump_url})",
            color=discord.Color.blue(),
            timestamp=first_message.created_at
        )
        embed.add_field(name="Auteur", value=first_message.author.mention, inline=True)
        embed.add_field(name="Contenu (extrait)", value=first_message.content[:500] if first_message.content else "*Contenu vide ou embed*", inline=False)
        
        await ctx.send(embed=embed)

    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas la permission de lire l'historique de ce salon.")
    except Exception:
        await ctx.send("❌ Erreur lors de la récupération du premier message.")

@bot.command(name='timer')
async def start_timer(ctx, time_str: str, *, reason: str = "Minuteur terminé"):
    """Démarre un minuteur et vous mentionne lorsque le temps est écoulé (ex: !timer 30m café)."""
    
    match = re.match(r"(\d+)([smhd])", time_str.lower())
    if not match:
        return await ctx.send("❌ Format de temps invalide. Utilisez par exemple `30m`, `1h`, `5s`.", delete_after=10)

    value = int(match.group(1))
    unit = match.group(2)
    
    if unit == 's': duration = timedelta(seconds=value)
    elif unit == 'm': duration = timedelta(minutes=value)
    elif unit == 'h': duration = timedelta(hours=value)
    elif unit == 'd': duration = timedelta(days=value)
    else: return await ctx.send("❌ Unité de temps non reconnue.", delete_after=10)
    
    if duration.total_seconds() > 86400 * 7: # Limite à 7 jours
        return await ctx.send("❌ Le minuteur ne peut pas dépasser 7 jours.", delete_after=10)

    formatted_duration = format_timedelta(duration)
    
    await ctx.send(f"⏱️ Minuteur démarré pour **{formatted_duration}** ({reason}). Je vous notifierai : {ctx.author.mention}.")

    await asyncio.sleep(duration.total_seconds())

    await ctx.send(f"🔔 **{ctx.author.mention}**, votre minuteur est terminé !\n> **Raison:** {reason}")


# [COMMANDES DE BIENVENUE/DÉPART]

@bot.command(name='bvntexte', aliases=['welcometext'])
@commands.has_permissions(administrator=True)
async def set_welcome_text(ctx, *, message: str):
    """Définit le message de bienvenue en format texte."""
    global SERVER_CONFIG
    SERVER_CONFIG['welcome_type'] = 'text'
    SERVER_CONFIG['welcome_message'] = message
    await ctx.send(f"✅ Message de bienvenue TEXTE défini. Placeholders : `{{user.mention}}`, `{{guild.name}}`, `{{member_count}}`")

@bot.command(name='bvnembed', aliases=['welcomeembed'])
@commands.has_permissions(administrator=True)
async def set_welcome_embed(ctx, *, message: str):
    """Définit le message de bienvenue en format Embed (Titre | Description)."""
    if '|' not in message: return await ctx.send("❌ Format invalide. Utilisez: `!bvnembed <Titre> | <Description>`")
    global SERVER_CONFIG
    SERVER_CONFIG['welcome_type'] = 'embed'
    SERVER_CONFIG['welcome_message'] = message
    await ctx.send(f"✅ Message de bienvenue EMBED défini (Titre | Description).")

@bot.command(name='leavetext')
@commands.has_permissions(administrator=True)
async def set_leave_text(ctx, *, message: str):
    """Définit le message de départ en format texte."""
    global SERVER_CONFIG
    SERVER_CONFIG['leave_type'] = 'text'
    SERVER_CONFIG['leave_message'] = message
    await ctx.send(f"✅ Message de départ TEXTE défini. Placeholders : `{{user.name}}`, `{{guild.name}}`, `{{member_count}}`")

@bot.command(name='leaveembed')
@commands.has_permissions(administrator=True)
async def set_leave_embed(ctx, *, message: str):
    """Définit le message de départ en format Embed (Titre | Description)."""
    if '|' not in message: return await ctx.send("❌ Format invalide. Utilisez: `!leaveembed <Titre> | <Description>`")
    global SERVER_CONFIG
    SERVER_CONFIG['leave_type'] = 'embed'
    SERVER_CONFIG['leave_message'] = message
    await ctx.send(f"✅ Message de départ EMBED défini (Titre | Description).")

# Fin de la Partie 1/2
# [COMMANDES DE MODÉRATION & SÉCURITÉ]

# Liste des mots interdits (globale)
FORBIDDEN_WORDS = set() 

@bot.group(name='automod')
@commands.has_permissions(administrator=True)
async def automod(ctx):
    """(Admin) Ensemble des commandes pour gérer l'Auto-Modération (mots interdits)."""
    if ctx.invoked_subcommand is None:
        await ctx.send("❌ Sous-commande manquante. Utilisez `!automod add <mot>` ou `!automod list`.", delete_after=10)

@automod.command(name='add')
@commands.has_permissions(administrator=True)
async def automod_add(ctx, *, word: str):
    """(Admin) Ajoute un mot à la liste des mots interdits (Auto-Modération)."""
    word = word.lower().strip()
    if not word:
        return await ctx.send("❌ Veuillez spécifier le mot à interdire.")
        
    if word in FORBIDDEN_WORDS:
        return await ctx.send(f"⚠️ Le mot `{word}` est déjà dans la liste des mots interdits.", delete_after=10)
    
    FORBIDDEN_WORDS.add(word)
    await ctx.send(f"✅ Le mot **`{word}`** a été ajouté à la liste des mots interdits.")

@automod.command(name='list')
async def automod_list(ctx):
    """(Admin) Affiche la liste des mots interdits configurés."""
    if not FORBIDDEN_WORDS:
        return await ctx.send("✅ La liste des mots interdits est vide.", delete_after=10)
        
    words_list = ", ".join(sorted(list(FORBIDDEN_WORDS)))
    
    embed = discord.Embed(
        title="🚫 Liste des Mots Interdits",
        description=f"**Total :** {len(FORBIDDEN_WORDS)} mots\n\n`{words_list}`",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)

# --- ÉVÉNEMENT POUR L'AUTOMODÉRATION (Vérifie chaque message) ---
@bot.listen('on_message')
async def check_forbidden_words(message):
    if message.author.bot or not message.guild:
        return

    content = message.content.lower()
    
    for word in FORBIDDEN_WORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', content): # Recherche du mot exact
            try:
                await message.delete()
                
                # Envoi d'un message d'avertissement temporaire
                warning_msg = await message.channel.send(f"🚫 **{message.author.mention}**, vous avez utilisé un mot interdit. Message supprimé.", delete_after=5)

                # Optionnel : Enregistrer un warning ou mute la personne après X violations
                
                # Log l'action
                await send_log_embed(message.guild, 
                                     "🚫 Auto-Modération : Mot Interdit", 
                                     discord.Color.red(), 
                                     [
                                         ("Utilisateur", message.author.mention),
                                         ("Mot Interdit", word),
                                         ("Salon", message.channel.mention)
                                     ])
                                     
            except discord.Forbidden:
                # Si le bot n'a pas les permissions de suppression
                pass
            return


@bot.command(name='mute')
@commands.has_permissions(manage_members=True)
async def mute_member(ctx, member: discord.Member, time_str: str = "60m", *, reason: str = "Aucune raison spécifiée."):
    """Met un membre en sourdine temporairement (timeout)."""
    
    # 1. Parsing du temps (réutilise le code de !timer)
    match = re.match(r"(\d+)([smhd])", time_str.lower())
    if not match:
        return await ctx.send("❌ Format de temps invalide. Utilisez par exemple `30m`, `1h`, `5s`.", delete_after=10)

    value = int(match.group(1))
    unit = match.group(2)
    
    if unit == 's': duration = timedelta(seconds=value)
    elif unit == 'm': duration = timedelta(minutes=value)
    elif unit == 'h': duration = timedelta(hours=value)
    elif unit == 'd': duration = timedelta(days=value)
    else: return await ctx.send("❌ Unité de temps non reconnue.", delete_after=10)
    
    if duration.total_seconds() > 2419200: # Limite Discord de 28 jours (2419200 secondes)
        return await ctx.send("❌ Le timeout ne peut pas dépasser 28 jours.", delete_after=10)
        
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("❌ Vous ne pouvez pas mute un membre ayant un rôle égal ou supérieur au vôtre.")
    
    if member.bot:
        return await ctx.send("❌ Je ne peux pas mute un bot.", delete_after=10)

    try:
        # Utiliser l'API timeout (mise en sourdine)
        until_time = datetime.now(timezone.utc) + duration
        await member.timeout(until_time, reason=reason)
        
        formatted_duration = format_timedelta(duration)
        
        await ctx.send(f"🔇 **{member.display_name}** a été mis en sourdine pour **{formatted_duration}**.\n**Raison:** {reason}")
        
        # Log
        await send_log_embed(ctx.guild, 
                             "🔇 Utilisateur Mute", 
                             discord.Color.orange(), 
                             [
                                 ("Utilisateur", member.mention),
                                 ("Modérateur", ctx.author.mention),
                                 ("Durée", formatted_duration),
                                 ("Raison", reason)
                             ])

    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions pour mute ce membre. Vérifiez ma hiérarchie de rôles.")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors du mute : {e}")

@bot.command(name='unmute')
@commands.has_permissions(manage_members=True)
async def unmute_member(ctx, member: discord.Member):
    """Retire le rôle de sourdine (timeout)."""
    
    try:
        if not member.timed_out:
            return await ctx.send(f"✅ **{member.display_name}** n'est pas en sourdine (timeout).", delete_after=10)
            
        await member.timeout(None, reason="Unmute manuel par modérateur.") # Set to None pour retirer le timeout
        
        await ctx.send(f"🔊 **{member.display_name}** a été réactivé (unmute).")
        
        # Log
        await send_log_embed(ctx.guild, 
                             "🔊 Utilisateur Unmute", 
                             discord.Color.green(), 
                             [
                                 ("Utilisateur", member.mention),
                                 ("Modérateur", ctx.author.mention),
                             ])
                             
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions pour unmute ce membre.")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de l'unmute : {e}")


@bot.command(name='kick')
@commands.has_permissions(kick_members=True)
async def kick_member(ctx, member: discord.Member, *, reason: str = "Aucune raison spécifiée."):
    """Expulse un membre du serveur."""
    
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("❌ Vous ne pouvez pas expulser un membre ayant un rôle égal ou supérieur au vôtre.")
    
    if member.bot:
        return await ctx.send("❌ Je ne peux pas expulser un bot.", delete_after=10)

    try:
        # Tenter d'envoyer un MP avant
        await member.send(f"Vous avez été expulsé du serveur **{ctx.guild.name}**.\n**Raison:** {reason}")
    except:
        # Ignore si l'envoi de MP échoue
        pass

    try:
        await member.kick(reason=reason)
        await ctx.send(f"✅ **{member.display_name}** a été expulsé.\n**Raison:** {reason}")
        
        # Log
        await send_log_embed(ctx.guild, 
                             "👢 Utilisateur Expulsé (Kick)", 
                             discord.Color.red(), 
                             [
                                 ("Utilisateur", f"{member.name} ({member.id})"),
                                 ("Modérateur", ctx.author.mention),
                                 ("Raison", reason)
                             ])

    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions nécessaires pour expulser ce membre. Vérifiez ma hiérarchie.")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de l'expulsion : {e}")


@bot.command(name='ban')
@commands.has_permissions(ban_members=True)
async def ban_member(ctx, member: discord.Member, *, reason: str = "Aucune raison spécifiée."):
    """Banni un membre du serveur."""
    
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("❌ Vous ne pouvez pas bannir un membre ayant un rôle égal ou supérieur au vôtre.")
    
    if member.bot:
        return await ctx.send("❌ Je ne peux pas bannir un bot.", delete_after=10)

    try:
        # Tenter d'envoyer un MP avant
        await member.send(f"Vous avez été banni du serveur **{ctx.guild.name}**.\n**Raison:** {reason}")
    except:
        # Ignore si l'envoi de MP échoue
        pass
        
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🔨 **{member.display_name}** a été banni.\n**Raison:** {reason}")
        
        # Log
        await send_log_embed(ctx.guild, 
                             "🔨 Utilisateur Banni", 
                             discord.Color.dark_red(), 
                             [
                                 ("Utilisateur", f"{member.name} ({member.id})"),
                                 ("Modérateur", ctx.author.mention),
                                 ("Raison", reason)
                             ])

    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions nécessaires pour bannir ce membre. Vérifiez ma hiérarchie.")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors du bannissement : {e}")

# Importation nécessaire pour le mute
from datetime import timezone
    # --- COMMANDES D'ÉCONOMIE & GAMING (Partie 3/3) ---

@bot.command(name='daily')
@commands.cooldown(1, DAILY_COOLDOWN, commands.BucketType.user)
async def daily_currency(ctx):
    """Réclame la monnaie journalière."""
    data = get_user_data(str(ctx.author.id))
    daily_amount = random.randint(300, 700)
    data['currency'] += daily_amount
    
    embed = discord.Embed(
        title="☀️ Récompense Journalière",
        description=f"Vous avez réclamé **{daily_amount} 💰** !\nVous avez maintenant **{data['currency']} 💰**.",
        color=discord.Color.gold(),
        timestamp=datetime.now()
    )
    await ctx.send(embed=embed)

# Gestion de l'erreur du cooldown pour !daily
@daily_currency.error
async def daily_currency_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        remaining = format_timedelta(timedelta(seconds=error.retry_after))
        await ctx.send(f"⏳ Vous avez déjà réclamé votre récompense journalière. Réessayez dans **{remaining}**.", delete_after=10)
    else:
        # Relance les autres erreurs
        raise error

@bot.command(name='balance', aliases=['bal'])
async def show_balance(ctx, member: discord.Member = None):
    """Affiche la balance de monnaie d'un utilisateur."""
    member = member or ctx.author
    data = get_user_data(str(member.id))
    
    embed = discord.Embed(
        title=f"💸 Balance de {member.display_name}",
        description=f"**Monnaie :** {data['currency']} 💰\n**Réputation :** {data['rep']} ⭐",
        color=discord.Color.dark_teal()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name='rep')
@commands.cooldown(1, REP_COOLDOWN, commands.BucketType.user)
async def give_reputation(ctx, member: discord.Member):
    """Donne un point de réputation à un membre (une fois par jour)."""
    if member.id == ctx.author.id:
        return await ctx.send("❌ Vous ne pouvez pas vous donner de réputation à vous-même.", delete_after=10)
    if member.bot:
        return await ctx.send("❌ Vous ne pouvez pas donner de réputation à un bot.", delete_after=10)
        
    data = get_user_data(str(member.id))
    data['rep'] += 1
    
    await ctx.send(f"⭐ **{ctx.author.display_name}** a donné un point de réputation à **{member.display_name}** ! Ils ont maintenant **{data['rep']}** points.")

@give_reputation.error
async def give_reputation_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        remaining = format_timedelta(timedelta(seconds=error.retry_after))
        await ctx.send(f"⏳ Vous avez déjà donné un point de réputation aujourd'hui. Réessayez dans **{remaining}**.", delete_after=10)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Veuillez mentionner le membre à qui vous souhaitez donner de la réputation. Exemple: `!rep @Utilisateur`.", delete_after=10)
    else:
        raise error

@bot.command(name='shop')
async def shop(ctx):
    """Affiche la boutique de rôles."""
    if not SHOP_ROLES:
        return await ctx.send("🛍️ La boutique de rôles est actuellement vide.", delete_after=10)
        
    description = "Utilisez `!buy <ID_DU_RÔLE>` pour acheter un rôle.\n\n"
    
    for role_id_str, price in SHOP_ROLES.items():
        role_id = int(role_id_str)
        role = ctx.guild.get_role(role_id)
        if role:
            description += f"**Rôle:** {role.mention}\n"
            description += f"**ID:** `{role_id}`\n"
            description += f"**Prix:** {price} 💰\n---\n"
            
    embed = discord.Embed(
        title="🛒 Boutique de Rôles",
        description=description,
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot.command(name='buy')
async def buy_role(ctx, role_id: int):
    """Achète un rôle de la boutique."""
    role_id_str = str(role_id)
    if role_id_str not in SHOP_ROLES:
        return await ctx.send("❌ Cet ID de rôle n'est pas dans la boutique.", delete_after=10)

    role = ctx.guild.get_role(role_id)
    if not role:
        return await ctx.send("❌ Ce rôle n'existe pas ou n'est plus disponible.", delete_after=10)
        
    price = SHOP_ROLES[role_id_str]
    user_data = get_user_data(str(ctx.author.id))
    
    if role in ctx.author.roles:
        return await ctx.send(f"✅ Vous possédez déjà le rôle {role.mention}.", delete_after=10)

    if user_data['currency'] < price:
        needed = price - user_data['currency']
        return await ctx.send(f"❌ Vous n'avez pas assez de monnaie. Il vous manque **{needed} 💰**.", delete_after=10)

    try:
        await ctx.author.add_roles(role, reason="Achat de rôle via la boutique.")
        user_data['currency'] -= price
        await ctx.send(f"🎉 Félicitations **{ctx.author.display_name}** ! Vous avez acheté et reçu le rôle {role.mention} pour **{price} 💰**.\nBalance restante : **{user_data['currency']} 💰**.")
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions d'ajouter ce rôle. Vérifiez ma hiérarchie et mes permissions.")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de l'achat : {e}")

# Exemple de mini-jeu : !dice (dé)
@bot.command(name='dice')
async def dice_roll(ctx, amount: int = None):
    """Joue aux dés : parie de la monnaie (si un montant est spécifié) et tente de gagner."""
    
    user_data = get_user_data(str(ctx.author.id))
    roll = random.randint(1, 100)
    
    if amount:
        if amount <= 0:
            return await ctx.send("❌ Le montant du pari doit être positif.", delete_after=10)
        if amount > user_data['currency']:
            return await ctx.send(f"❌ Vous n'avez pas assez de monnaie pour parier {amount} 💰.", delete_after=10)

        # Logique de pari (Exemple simple : Gain si > 60)
        if roll > 60:
            gain = amount * 2
            user_data['currency'] += gain
            message = f"🎲 **{ctx.author.display_name}** a fait **{roll}** et **GAGNE** ! Vous recevez **{gain} 💰**.\nBalance : {user_data['currency']} 💰."
        else:
            user_data['currency'] -= amount
            message = f"🎲 **{ctx.author.display_name}** a fait **{roll}** et **PERD** 😞. Vous perdez **{amount} 💰**.\nBalance : {user_data['currency']} 💰."
    
    else:
        # Simple jet de dés sans pari
        message = f"🎲 Jet de dés : **{roll}**."
        
    await ctx.send(message)


# --- COMMANDES FUN & DIVERS (Partie 3/3) ---

@bot.command(name='8ball')
async def eight_ball(ctx, *, question: str):
    """Posez une question à la boule magique 8-ball."""
    if not question.endswith('?'):
        return await ctx.send("❌ Veuillez poser une question se terminant par un point d'interrogation.")
        
    response = random.choice(BALL_RESPONSES)
    
    embed = discord.Embed(
        title="🎱 Boule Magique 8-Ball",
        color=discord.Color.blurple()
    )
    embed.add_field(name="❓ Question", value=question, inline=False)
    embed.add_field(name="🔮 Réponse", value=f"**{response}**", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='joke', aliases=['blague'])
async def send_joke(ctx):
    """Raconte une blague aléatoire."""
    joke = random.choice(JOKES)
    await ctx.send(f"😂 {joke}")

@bot.command(name='quote', aliases=['citation'])
async def send_quote(ctx):
    """Affiche une citation inspirante aléatoire."""
    quote = random.choice(QUOTES)
    await ctx.send(f"📜 {quote}")

@bot.command(name='ascii')
async def ascii_art(ctx, *, text: str):
    """Transforme un texte en art ASCII."""
    if len(text) > 20:
        return await ctx.send("❌ Texte trop long (max 20 caractères) pour l'art ASCII.", delete_after=10)
        
    f = Figlet(font='standard') # 'standard' est un bon choix pour Discord
    ascii_text = f.renderText(text)
    
    # Envoi dans un bloc de code pour préserver la mise en page
    if len(ascii_text) > 2000:
        await ctx.send("❌ L'art ASCII généré est trop long pour un message Discord.")
    else:
        await ctx.send(f"```\n{ascii_text}\n```")

@bot.command(name='say')
@commands.has_permissions(manage_messages=True)
async def say_message(ctx, channel: discord.TextChannel = None, *, message: str):
    """(Modération) Envoie un message spécifié dans un salon donné ou le salon actuel."""
    
    # Si le premier argument n'est pas un salon valide, on suppose que le salon est le salon actuel
    # et que le message commence par ce qui était censé être le salon.
    if channel is None:
        channel = ctx.channel
        message = message
    else:
        # Vérifiez si le salon existe réellement et s'il est différent du salon actuel
        # Le code de commands.TextChannel fait déjà cette vérification,
        # mais on doit s'assurer que le message n'est pas vide
        if not message:
            return await ctx.send("❌ Veuillez fournir le message à envoyer.", delete_after=10)

    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass # Ne peut pas supprimer le message
        
    try:
        await channel.send(message)
    except discord.Forbidden:
        await ctx.send(f"❌ Je n'ai pas la permission d'envoyer des messages dans {channel.mention}.")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de l'envoi du message : {e}")

# --- FIN DES COMMANDES ---
