#!/usr/bin/env python3
"""
Hoshikuzu Discord Bot - Version Sans Modération (Corrigée)
Bot de gestion de serveur Discord complet et sécurisé
"""

import os
import json
import threading
import http.server
import socketserver
import asyncio
import datetime
import re
import logging
from typing import Optional, Dict, Any

import discord
from discord.ext import commands
from discord.ui import View, Button

# ==================== CONFIGURATION LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('hoshikuzu.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('hoshikuzu')

# ==================== KEEP ALIVE ====================
def keep_alive():
    """Serveur HTTP pour maintenir le bot actif sur les plateformes d'hébergement"""
    port = int(os.environ.get("PORT", 8080))
    
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args): 
            pass
    
    try:
        with socketserver.TCPServer(("", port), QuietHandler) as httpd:
            logger.info(f"Keep-alive HTTP server running on port {port}")
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"Keep-alive server error: {e}")

threading.Thread(target=keep_alive, daemon=True).start()

# ==================== GESTION SÉCURISÉE DES DONNÉES ====================
DATA_FILE = "hoshikuzu_data.json"
BACKUP_FILE = "hoshikuzu_data.backup.json"
data_lock = asyncio.Lock()

def load_data() -> Dict[str, Any]:
    """Charge les données avec validation et gestion d'erreur"""
    default_data = {
        "config": {},
        "tickets": {},
        "temp_vocs": {},
        "allowed_links": {},
        "reaction_roles": {},
        "invites": {}
    }
    
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if not isinstance(loaded, dict):
                    raise ValueError("Invalid data structure")
                for key in default_data:
                    if key not in loaded:
                        loaded[key] = default_data[key]
                logger.info("Data loaded successfully")
                return loaded
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error loading data: {e}")
            if os.path.exists(BACKUP_FILE):
                try:
                    with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                        logger.info("Loading from backup")
                        return json.load(f)
                except Exception:
                    pass
    
    logger.info("Using default data structure")
    return default_data

def save_data_sync(d: Dict[str, Any]):
    """Sauvegarde les données de manière synchrone (pour threading)"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                backup_data = f.read()
            with open(BACKUP_FILE, "w", encoding="utf-8") as f:
                f.write(backup_data)
        
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        logger.debug("Data saved successfully")
    except Exception as e:
        logger.error(f"Error saving data: {e}")

data = load_data()

async def get_conf(gid: int, key: str, default=None):
    """Récupère une configuration de manière async-safe"""
    async with data_lock:
        return data.get("config", {}).get(str(gid), {}).get(key, default)

async def set_conf(gid: int, key: str, value):
    """Définit une configuration de manière async-safe"""
    async with data_lock:
        data.setdefault("config", {}).setdefault(str(gid), {})[key] = value
        await asyncio.to_thread(save_data_sync, data)

async def get_gconf(gid: int) -> Dict[str, Any]:
    """Récupère toute la configuration d'une guilde"""
    async with data_lock:
        return data.get("config", {}).get(str(gid), {}).copy()

# ==================== BOT INIT ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)
EMOJI = "<a:caarrow:1433143710094196997>"
VOC_TRIGGER_NAME = "🔊Créer un voc"

# ==================== LOG HELPER ====================
async def send_log(guild: discord.Guild, content):
    """Envoie un message dans le salon de logs"""
    logs_channel_id = await get_conf(guild.id, "logs_channel")
    if not logs_channel_id:
        return
    
    channel = guild.get_channel(logs_channel_id)
    if not channel:
        return
    
    try:
        if isinstance(content, discord.Embed):
            await channel.send(embed=content)
        elif isinstance(content, discord.File):
            await channel.send(file=content)
        else:
            await channel.send(content)
    except discord.Forbidden:
        logger.warning(f"Cannot send log to channel {logs_channel_id}: Missing permissions")
    except Exception as e:
        logger.error(f"Error sending log: {e}")

# ==================== READY ====================
@bot.event
async def on_ready():
    """Initialisation du bot au démarrage"""
    logger.info(f"Bot connected as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="hoshikuzu | +help"))
    
    bot.add_view(TicketPanelView())
    bot.add_view(TicketView())
    logger.info("Persistent views registered")

# ==================== HELP ====================
@bot.command(name="help")
async def help_cmd(ctx):
    """Affiche l'aide du bot"""
    e = discord.Embed(
        title="🌿 Commandes Hoshikuzu",
        description="Voici toutes les commandes disponibles",
        color=discord.Color.green()
    )
    
    e.add_field(
        name="📊 Configuration",
        value=(
            "`+config` - Afficher la configuration\n"
            "`+setwelcome #channel embed/text` - Configurer les messages de bienvenue\n"
            "`+setleave #channel embed/text` - Configurer les messages de départ\n"
            "`+setjoinrole @role` - Rôle auto pour nouveaux membres\n"
            "`+setlogs #channel` - Salon de logs"
        ),
        inline=False
    )
    
    e.add_field(
        name="👥 Invitations",
        value=(
            "`+roleinvite <nombre> @role` - Rôle après X invitations\n"
            "`+invites [@user]` - Voir les invitations"
        ),
        inline=False
    )
    
    e.add_field(
        name="🔗 Liens",
        value=(
            "`+allowlink #channel` - Autoriser les liens\n"
            "`+disallowlink #channel` - Bloquer les liens"
        ),
        inline=False
    )
    
    e.add_field(
        name="👤 Rôles",
        value=(
            "`+role @user @role` - Ajouter/retirer un rôle\n"
            "`+rolejoin @role` - Rôle automatique à l'arrivée"
        ),
        inline=False
    )
    
    e.add_field(
        name="🎫 Tickets",
        value=(
            "`+ticket` - Créer un ticket\n"
            "`+ticketpanel` - Panel de tickets\n"
            "`+close` - Fermer le ticket actuel\n"
            "`+ticketrole @role` - Gérer les rôles de support"
        ),
        inline=False
    )
    
    e.add_field(
        name="🎭 Rôles Réactions",
        value="`+reactionrole #channel emoji @role` - Créer un rôle réaction",
        inline=False
    )
    
    e.add_field(
        name="💬 Utilitaires",
        value="`+say <message>` - Faire parler le bot",
        inline=False
    )
    
    e.add_field(
        name="🔊 Vocaux Temporaires",
        value=(
            "`+createvoc` - Créer le salon trigger\n"
            "`+setupvoc #salon` - Configurer un salon existant"
        ),
        inline=False
    )
    
    e.set_footer(text="Bot Hoshikuzu | Gestion de serveur")
    await ctx.send(embed=e)

# ==================== CONFIG ====================
@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config(ctx):
    """Affiche la configuration actuelle du serveur"""
    conf = await get_gconf(ctx.guild.id)
    e = discord.Embed(
        title="⚙️ Configuration du serveur",
        description=f"Configuration pour **{ctx.guild.name}**",
        color=discord.Color.blue()
    )
    
    welcome_embed = conf.get("welcome_embed_channel")
    welcome_text = conf.get("welcome_text_channel")
    if welcome_embed:
        e.add_field(name="Bienvenue (Embed)", value=f"<#{welcome_embed}>", inline=False)
    if welcome_text:
        e.add_field(name="Bienvenue (Texte)", value=f"<#{welcome_text}>", inline=False)
    
    leave_embed = conf.get("leave_embed_channel")
    leave_text = conf.get("leave_text_channel")
    if leave_embed:
        e.add_field(name="Départ (Embed)", value=f"<#{leave_embed}>", inline=False)
    if leave_text:
        e.add_field(name="Départ (Texte)", value=f"<#{leave_text}>", inline=False)
    
    role_join = conf.get("role_join")
    if role_join:
        e.add_field(name="Rôle automatique", value=f"<@&{role_join}>", inline=False)
    
    logs_channel = conf.get("logs_channel")
    if logs_channel:
        e.add_field(name="Salon logs", value=f"<#{logs_channel}>", inline=False)
    
    voc_trigger = conf.get("voc_trigger_channel")
    if voc_trigger:
        e.add_field(name="Salon vocal trigger", value=f"<#{voc_trigger}>", inline=False)
    
    ticket_roles = conf.get("ticket_roles", [])
    if ticket_roles:
        roles_mentions = ", ".join([f"<@&{r}>" for r in ticket_roles])
        e.add_field(name="Rôles tickets", value=roles_mentions, inline=False)
    
    if not conf:
        e.description = "Aucune configuration définie pour le moment.\nUtilise les commandes `+set...` pour configurer le bot."
    
    e.set_footer(text=f"Demandé par {ctx.author}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=e)

# ==================== SETWELCOME ====================
@bot.command(name="setwelcome")
@commands.has_permissions(manage_guild=True)
async def setwelcome(ctx, channel: Optional[discord.TextChannel] = None, mode: Optional[str] = None):
    """Configure les messages de bienvenue"""
    if not channel or not mode or mode.lower() not in ["embed", "text"]:
        return await ctx.send("❌ Usage : `+setwelcome #channel embed/text`")
    
    if mode.lower() == "embed":
        await set_conf(ctx.guild.id, "welcome_embed_channel", channel.id)
        await ctx.send(f"✅ Messages de bienvenue (embed) configurés dans {channel.mention}")
    else:
        await set_conf(ctx.guild.id, "welcome_text_channel", channel.id)
        await ctx.send(f"✅ Messages de bienvenue (texte) configurés dans {channel.mention}")
    
    logger.info(f"Welcome {mode} set to {channel.name} in {ctx.guild.name}")

# ==================== SETLEAVE ====================
@bot.command(name="setleave")
@commands.has_permissions(manage_guild=True)
async def setleave(ctx, channel: Optional[discord.TextChannel] = None, mode: Optional[str] = None):
    """Configure les messages de départ"""
    if not channel or not mode or mode.lower() not in ["embed", "text"]:
        return await ctx.send("❌ Usage : `+setleave #channel embed/text`")
    
    if mode.lower() == "embed":
        await set_conf(ctx.guild.id, "leave_embed_channel", channel.id)
        await ctx.send(f"✅ Messages de départ (embed) configurés dans {channel.mention}")
    else:
        await set_conf(ctx.guild.id, "leave_text_channel", channel.id)
        await ctx.send(f"✅ Messages de départ (texte) configurés dans {channel.mention}")
    
    logger.info(f"Leave {mode} set to {channel.name} in {ctx.guild.name}")

# ==================== SETJOINROLE ====================
@bot.command(name="setjoinrole")
@commands.has_permissions(manage_guild=True)
async def setjoinrole(ctx, role: Optional[discord.Role] = None):
    """Configure le rôle automatique pour les nouveaux membres"""
    if not role:
        return await ctx.send("❌ Usage : `+setjoinrole @role`")
    
    if role >= ctx.guild.me.top_role:
        return await ctx.send("❌ Ce rôle est trop élevé dans la hiérarchie.")
    
    await set_conf(ctx.guild.id, "role_join", role.id)
    await ctx.send(f"✅ Rôle {role.mention} sera attribué automatiquement aux nouveaux membres.")
    logger.info(f"Auto-role set to {role.name} in {ctx.guild.name}")

# ==================== SETLOGS ====================
@bot.command(name="setlogs")
@commands.has_permissions(manage_guild=True)
async def setlogs(ctx, channel: Optional[discord.TextChannel] = None):
    """Configure le salon de logs"""
    if not channel:
        return await ctx.send("❌ Usage : `+setlogs #channel`")
    
    await set_conf(ctx.guild.id, "logs_channel", channel.id)
    await ctx.send(f"✅ Salon de logs configuré : {channel.mention}")
    
    test_embed = discord.Embed(
        title="📊 Logs configurés",
        description="Ce salon recevra désormais tous les logs du serveur.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    await send_log(ctx.guild, test_embed)
    logger.info(f"Logs channel set to {channel.name} in {ctx.guild.name}")

# ==================== WELCOME / LEAVE ====================
async def send_welcome(member: discord.Member):
    """Envoie les messages de bienvenue et attribue le rôle automatique"""
    conf = await get_gconf(member.guild.id)
    total = member.guild.member_count
    
    role_join_id = conf.get("role_join")
    if role_join_id:
        role = member.guild.get_role(role_join_id)
        if role:
            try:
                await member.add_roles(role, reason="Rôle automatique")
                logger.info(f"Auto-role {role.name} given to {member}")
            except discord.Forbidden:
                logger.warning(f"Cannot give auto-role to {member}: Missing permissions")
            except Exception as e:
                logger.error(f"Error giving auto-role: {e}")
    
    embed_ch = conf.get("welcome_embed_channel")
    if embed_ch:
        ch = member.guild.get_channel(embed_ch)
        if ch:
            try:
                e = discord.Embed(
                    title="✨ Bienvenue sur **Hoshikuzu** !",
                    description=f"{member.mention} vient de rejoindre ✨",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                e.add_field(
                    name="Infos",
                    value=f"{EMOJI} **BVN {member.mention} sur Hoshikuzu !**\n{EMOJI} Nous sommes maintenant **{total} membres**."
                )
                e.set_thumbnail(url=member.display_avatar.url)
                e.set_footer(text=f"ID: {member.id}")
                await ch.send(embed=e)
            except Exception as e:
                logger.error(f"Error sending welcome embed: {e}")
    
    text_ch = conf.get("welcome_text_channel")
    if text_ch:
        ch = member.guild.get_channel(text_ch)
        if ch:
            try:
                await ch.send(
                    f"{EMOJI} **BVN {member.mention} sur Hoshikuzu !**\n"
                    f"{EMOJI} Nous sommes maintenant **{total} membres**."
                )
            except Exception as e:
                logger.error(f"Error sending welcome text: {e}")

async def send_leave(member: discord.Member):
    """Envoie les messages de départ"""
    conf = await get_gconf(member.guild.id)
    total = member.guild.member_count
    
    embed_ch = conf.get("leave_embed_channel")
    if embed_ch:
        ch = member.guild.get_channel(embed_ch)
        if ch:
            try:
                e = discord.Embed(
                    title="❌ Un membre nous quitte...",
                    description=f"{member.mention} vient de partir.",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                e.add_field(
                    name="Infos",
                    value=f"{EMOJI} {member.mention} a quitté Hoshikuzu...\n{EMOJI} Il reste maintenant **{total} membres**."
                )
                e.set_thumbnail(url=member.display_avatar.url)
                e.set_footer(text=f"ID: {member.id}")
                await ch.send(embed=e)
            except Exception as e:
                logger.error(f"Error sending leave embed: {e}")
    
    text_ch = conf.get("leave_text_channel")
    if text_ch:
        ch = member.guild.get_channel(text_ch)
        if ch:
            try:
                await ch.send(
                    f"{EMOJI} {member.mention} a quitté Hoshikuzu...\n"
                    f"{EMOJI} Il reste maintenant **{total} membres**."
                )
            except Exception as e:
                logger.error(f"Error sending leave text: {e}")

@bot.event
async def on_member_join(member: discord.Member):
    """Gestion de l'arrivée d'un membre"""
    await send_welcome(member)
    
    try:
        async with data_lock:
            invites_before = data.get("invites", {}).get(str(member.guild.id), {})
        
        invites_after = {inv.code: inv.uses for inv in await member.guild.invites()}
        
        for code, uses in invites_after.items():
            if code in invites_before and uses > invites_before[code]:
                for inv in await member.guild.invites():
                    if inv.code == code and inv.inviter:
                        inviter_id = str(inv.inviter.id)
                        async with data_lock:
                            data.setdefault("invites", {}).setdefault(str(member.guild.id), {}).setdefault(inviter_id, {"count": 0, "members": []})
                            data["invites"][str(member.guild.id)][inviter_id]["count"] += 1
                            data["invites"][str(member.guild.id)][inviter_id]["members"].append(member.id)
                            await asyncio.to_thread(save_data_sync, data)
                        logger.info(f"{member} invited by {inv.inviter}")
                        break
        
        async with data_lock:
            data.setdefault("invites", {})[str(member.guild.id)] = invites_after
            await asyncio.to_thread(save_data_sync, data)
    except discord.Forbidden:
        logger.warning(f"Cannot track invites in {member.guild.name}: Missing permissions")
    except Exception as e:
        logger.error(f"Error tracking invite: {e}")

@bot.event
async def on_member_remove(member: discord.Member):
    """Gestion du départ d'un membre"""
    await send_leave(member)

# ==================== INVITES ====================
@bot.command(name="invites")
async def invites(ctx, member: Optional[discord.Member] = None):
    """Affiche les statistiques d'invitations"""
    member = member or ctx.author
    gid = str(ctx.guild.id)
    
    async with data_lock:
        invites_data = data.get("invites", {}).get(gid, {}).get(str(member.id), {"count": 0, "members": []})
    
    count = invites_data.get("count", 0)
    e = discord.Embed(
        title=f"📊 Invitations de {member.display_name}",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    e.add_field(name="Total", value=f"**{count}** invitation(s)")
    e.set_thumbnail(url=member.display_avatar.url)
    e.set_footer(text=f"Demandé par {ctx.author}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=e)

# ==================== ROLEINVITE ====================
@bot.command(name="roleinvite")
@commands.has_permissions(manage_guild=True)
async def roleinvite(ctx, count: Optional[int] = None, role: Optional[discord.Role] = None):
    """Configure un rôle à donner après X invitations"""
    if not count or not role:
        return await ctx.send("❌ Usage : `+roleinvite <nombre> @role`")
    
    if count < 1:
        return await ctx.send("❌ Le nombre d'invitations doit être positif.")
    
    if role >= ctx.guild.me.top_role:
        return await ctx.send("❌ Ce rôle est trop élevé dans la hiérarchie.")
    
    gid = str(ctx.guild.id)
    async with data_lock:
        data.setdefault("config", {}).setdefault(gid, {}).setdefault("role_invites", {})[str(role.id)] = count
        await asyncio.to_thread(save_data_sync, data)
    
    await ctx.send(f"✅ Le rôle {role.mention} sera donné après **{count}** invitation(s).")
    logger.info(f"Role invite set: {count} invites for {role.name} in {ctx.guild.name}")

# ==================== ROLE ====================
@bot.command(name="role")
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def role(ctx, member: Optional[discord.Member] = None, role: Optional[discord.Role] = None):
    """Ajoute ou retire un rôle à un membre"""
    if not member or not role:
        return await ctx.send("❌ Usage : `+role @user @role`")
    
    if role >= ctx.guild.me.top_role:
        return await ctx.send("❌ Ce rôle est trop élevé dans la hiérarchie.")
    
    if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("❌ Tu ne peux pas gérer ce rôle.")
    
    try:
        if role in member.roles:
            await member.remove_roles(role, reason=f"Retiré par {ctx.author}")
            await ctx.send(f"❌ Rôle {role.mention} retiré de {member.mention}")
            logger.info(f"Role {role.name} removed from {member} by {ctx.author}")
        else:
            await member.add_roles(role, reason=f"Ajouté par {ctx.author}")
            await ctx.send(f"✅ Rôle {role.mention} ajouté à {member.mention}")
            logger.info(f"Role {role.name} added to {member} by {ctx.author}")
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions pour gérer ce rôle.")
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")
        logger.error(f"Role error: {e}")

# ==================== ROLE JOIN ====================
@bot.command(name="rolejoin")
@commands.has_permissions(manage_guild=True)
async def rolejoin(ctx, role: Optional[discord.Role] = None):
    """Configure le rôle automatique (alias de setjoinrole)"""
    if not role:
        return await ctx.send("❌ Usage : `+rolejoin @role`")
    
    if role >= ctx.guild.me.top_role:
        return await ctx.send("❌ Ce rôle est trop élevé dans la hiérarchie.")
    
    await set_conf(ctx.guild.id, "role_join", role.id)
    await ctx.send(f"✅ Rôle {role.mention} sera attribué à chaque nouvel arrivant.")
    logger.info(f"Auto-role set to {role.name} in {ctx.guild.name}")

# ==================== TICKETROLE ====================
@bot.command(name="ticketrole")
@commands.has_permissions(manage_guild=True)
async def ticketrole(ctx, role: Optional[discord.Role] = None):
    """Ajoute ou retire un rôle de support ticket"""
    if not role:
        return await ctx.send("❌ Usage : `+ticketrole @role`")
    
    ticket_roles = await get_conf(ctx.guild.id, "ticket_roles") or []
    
    if role.id in ticket_roles:
        ticket_roles.remove(role.id)
        await set_conf(ctx.guild.id, "ticket_roles", ticket_roles)
        await ctx.send(f"❌ Rôle {role.mention} retiré des rôles de support ticket.")
        logger.info(f"Ticket role {role.name} removed in {ctx.guild.name}")
    else:
        ticket_roles.append(role.id)
        await set_conf(ctx.guild.id, "ticket_roles", ticket_roles)
        await ctx.send(f"✅ Rôle {role.mention} ajouté aux rôles de support ticket.")
        logger.info(f"Ticket role {role.name} added in {ctx.guild.name}")

# ==================== CLOSE ====================
@bot.command(name="close")
async def close(ctx):
    """Ferme le ticket actuel"""
    if "ticket-" not in ctx.channel.name:
        return await ctx.send("❌ Cette commande ne fonctionne que dans un ticket.")
    
    await ctx.send("🔒 Ce ticket sera supprimé dans 5 secondes...")
    await asyncio.sleep(5)
    
    try:
        await ctx.channel.delete(reason=f"Ticket fermé par {ctx.author}")
        logger.info(f"Ticket {ctx.channel.name} closed by {ctx.author}")
    except Exception as e:
        logger.error(f"Error closing ticket: {e}")

# ==================== TICKETPANEL ====================
class CreateTicketButton(Button):
    def __init__(self):
        super().__init__(label="Créer un ticket", style=discord.ButtonStyle.green, emoji="🎫")
    
    async def callback(self, interaction: discord.Interaction):
        for channel in interaction.guild.text_channels:
            if f"ticket-{interaction.user.name}".lower() in channel.name.lower():
                return await interaction.response.send_message(
                    f"❌ Tu as déjà un ticket ouvert : {channel.mention}",
                    ephemeral=True
                )
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        try:
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                overwrites=overwrites,
                reason=f"Ticket créé par {interaction.user}"
            )
            
            ticket_roles = await get_conf(interaction.guild.id, "ticket_roles") or []
            for role_id in ticket_roles:
                role = interaction.guild.get_role(role_id)
                if role:
                    await channel.set_permissions(role, read_messages=True, send_messages=True)
            
            embed = discord.Embed(
                title="🎫 Ticket ouvert",
                description=f"{interaction.user.mention}, explique ton problème ici.\nUn membre du staff va te répondre.",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.set_footer(text=f"Ticket de {interaction.user}", icon_url=interaction.user.display_avatar.url)
            
            await channel.send(embed=embed, view=TicketView())
            await interaction.response.send_message(f"✅ Ticket créé : {channel.mention}", ephemeral=True)
            logger.info(f"Ticket created by {interaction.user} in {interaction.guild.name}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Erreur : permissions insuffisantes.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
            logger.error(f"Ticket creation error: {e}")

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CreateTicketButton())

@bot.command(name="ticketpanel")
@commands.has_permissions(manage_guild=True)
async def ticketpanel(ctx):
    """Crée un panel de tickets avec bouton"""
    embed = discord.Embed(
        title="🎫 Système de Tickets",
        description="Clique sur le bouton ci-dessous pour créer un ticket.\nUn membre du staff te répondra dès que possible.",
        color=discord.Color.blue()
    )
    embed.add_field(name="📌 Rappel", value="N'ouvre un ticket que si tu as vraiment besoin d'aide !")
    embed.set_footer(text=f"Serveur {ctx.guild.name}", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
    
    await ctx.send(embed=embed, view=TicketPanelView())
    logger.info(f"Ticket panel created in {ctx.guild.name}")

# ==================== VOC TEMPORAIRES ====================
@bot.command(name="setupvoc")
@commands.has_permissions(manage_guild=True)
async def setup_voc(ctx, channel: Optional[discord.VoiceChannel] = None):
    """Configure un salon vocal existant comme trigger"""
    if not channel:
        return await ctx.send("❌ Usage : `+setupvoc #salon`")
    
    try:
        await set_conf(ctx.guild.id, "voc_trigger_channel", channel.id)
        await channel.edit(name=VOC_TRIGGER_NAME, reason=f"Configuré par {ctx.author}")
        await ctx.send(f"✅ Salon vocal trigger configuré : {channel.mention}")
        logger.info(f"Voice trigger set to {channel.name} in {ctx.guild.name}")
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions pour modifier ce salon.")
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")
        logger.error(f"Setup voice error: {e}")

@bot.command(name="createvoc")
@commands.has_permissions(manage_guild=True)
async def create_voc(ctx):
    """Crée un nouveau salon vocal trigger"""
    category = ctx.channel.category
    
    try:
        voc_trigger = await ctx.guild.create_voice_channel(
            name=VOC_TRIGGER_NAME,
            category=category,
            reason=f"Créé par {ctx.author}"
        )
        await set_conf(ctx.guild.id, "voc_trigger_channel", voc_trigger.id)
        await ctx.send(f"✅ Salon vocal trigger créé : {voc_trigger.mention}")
        logger.info(f"Voice trigger created in {ctx.guild.name}")
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions pour créer un salon vocal.")
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")
        logger.error(f"Create voice error: {e}")

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Gestion des vocaux temporaires"""
    guild = member.guild
    trigger_channel_id = await get_conf(guild.id, "voc_trigger_channel")
    
    if after.channel and after.channel.id == trigger_channel_id:
        try:
            voc = await guild.create_voice_channel(
                name=f"🔊 {member.display_name}",
                category=after.channel.category,
                reason="Vocal temporaire"
            )
            
            async with data_lock:
                data.setdefault("temp_vocs", {})[str(voc.id)] = {
                    "owner": member.id,
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                await asyncio.to_thread(save_data_sync, data)
            
            await member.move_to(voc)
            logger.info(f"Temporary voice channel created for {member} in {guild.name}")
        except discord.Forbidden:
            logger.warning(f"Cannot create temp voice in {guild.name}: Missing permissions")
        except Exception as e:
            logger.error(f"Error creating temp voice: {e}")
    
    if before.channel:
        cid = str(before.channel.id)
        async with data_lock:
            if cid in data.get("temp_vocs", {}) and len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Vocal temporaire vide")
                    del data["temp_vocs"][cid]
                    await asyncio.to_thread(save_data_sync, data)
                    logger.info(f"Temporary voice channel deleted in {guild.name}")
                except discord.Forbidden:
                    logger.warning(f"Cannot delete temp voice in {guild.name}: Missing permissions")
                except Exception as e:
                    logger.error(f"Error deleting temp voice: {e}")

# ==================== LIENS ====================
@bot.command(name="allowlink")
@commands.has_permissions(manage_guild=True)
async def allow_link(ctx, channel: Optional[discord.TextChannel] = None):
    """Autorise les liens dans un salon"""
    if not channel:
        return await ctx.send("❌ Usage : `+allowlink #channel`")
    
    gid = str(ctx.guild.id)
    
    async with data_lock:
        data.setdefault("allowed_links", {}).setdefault(gid, [])
        
        if channel.id not in data["allowed_links"][gid]:
            data["allowed_links"][gid].append(channel.id)
            await asyncio.to_thread(save_data_sync, data)
            await ctx.send(f"✅ Liens autorisés dans {channel.mention}")
            logger.info(f"Links allowed in {channel.name} ({ctx.guild.name})")
        else:
            await ctx.send(f"ℹ️ Les liens étaient déjà autorisés dans {channel.mention}")

@bot.command(name="disallowlink")
@commands.has_permissions(manage_guild=True)
async def disallow_link(ctx, channel: Optional[discord.TextChannel] = None):
    """Bloque les liens dans un salon"""
    if not channel:
        return await ctx.send("❌ Usage : `+disallowlink #channel`")
    
    gid = str(ctx.guild.id)
    
    async with data_lock:
        if gid in data.get("allowed_links", {}) and channel.id in data["allowed_links"][gid]:
            data["allowed_links"][gid].remove(channel.id)
            await asyncio.to_thread(save_data_sync, data)
            await ctx.send(f"❌ Liens bloqués dans {channel.mention}")
            logger.info(f"Links blocked in {channel.name} ({ctx.guild.name})")
        else:
            await ctx.send(f"ℹ️ Les liens étaient déjà bloqués dans {channel.mention}")

@bot.event
async def on_message(message: discord.Message):
    """Filtre les liens et traite les commandes"""
    if message.author.bot:
        await bot.process_commands(message)
        return
    
    if message.guild:
        gid = str(message.guild.id)
        async with data_lock:
            allowed_channels = data.get("allowed_links", {}).get(gid, [])
        
        url_regex = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        
        if message.channel.id not in allowed_channels and re.search(url_regex, message.content):
            try:
                await message.delete()
                await message.channel.send(
                    f"❌ {message.author.mention}, les liens ne sont pas autorisés ici !",
                    delete_after=5
                )
                
                e = discord.Embed(
                    title="🔗 Lien supprimé",
                    color=discord.Color.orange(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                e.add_field(name="Auteur", value=message.author.mention, inline=False)
                e.add_field(name="Salon", value=message.channel.mention, inline=False)
                e.add_field(name="Message", value=message.content[:1024], inline=False)
                
                await send_log(message.guild, e)
                logger.info(f"Link deleted from {message.author} in {message.channel.name}")
                return
            except discord.Forbidden:
                logger.warning(f"Cannot delete message in {message.channel.name}: Missing permissions")
    
    await bot.process_commands(message)

# ==================== SAY ====================
@bot.command(name="say")
@commands.has_permissions(manage_guild=True)
async def say(ctx, *, msg: Optional[str] = None):
    """Fait parler le bot"""
    if not msg:
        return await ctx.send("❌ Usage : `+say <message>`")
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    await ctx.send(msg)
    logger.info(f"Say command used by {ctx.author} in {ctx.guild.name}")

# ==================== REACTION ROLES ====================
class ReactionButton(Button):
    def __init__(self, emoji: str, role_id: int):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.gray)
        self.role_id = role_id
    
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.response.send_message("❌ Rôle introuvable.", ephemeral=True)
        
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Rôle réaction")
                await interaction.response.send_message(f"❌ Rôle **{role.name}** retiré", ephemeral=True)
            else:
                await interaction.user.add_roles(role, reason="Rôle réaction")
                await interaction.response.send_message(f"✅ Rôle **{role.name}** ajouté", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Je n'ai pas les permissions pour gérer ce rôle.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

@bot.command(name="reactionrole")
@commands.has_permissions(manage_roles=True)
async def reactionrole(ctx, channel: Optional[discord.TextChannel] = None, emoji: Optional[str] = None, role: Optional[discord.Role] = None):
    """Crée un rôle réaction"""
    if not all([channel, emoji, role]):
        return await ctx.send("❌ Usage : `+reactionrole #channel emoji @role`")
    
    if role >= ctx.guild.me.top_role:
        return await ctx.send("❌ Ce rôle est trop élevé dans la hiérarchie.")
    
    try:
        view = View(timeout=None)
        view.add_item(ReactionButton(emoji, role.id))
        
        embed = discord.Embed(
            title="🎭 Rôles Réactions",
            description=f"Clique sur {emoji} pour obtenir le rôle {role.mention}",
            color=discord.Color.blue()
        )
        
        msg = await channel.send(embed=embed, view=view)
        
        async with data_lock:
            data.setdefault("reaction_roles", {})[str(msg.id)] = {
                "channel_id": channel.id,
                "emoji": emoji,
                "role_id": role.id
            }
            await asyncio.to_thread(save_data_sync, data)
        
        await ctx.send(f"✅ Rôle réaction configuré dans {channel.mention}")
        logger.info(f"Reaction role created in {channel.name} for {role.name}")
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions pour envoyer des messages dans ce salon.")
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")
        logger.error(f"Reaction role error: {e}")

# ==================== GESTION ERREURS ====================
@bot.event
async def on_command_error(ctx, error):
    """Gestionnaire d'erreurs global"""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Tu n'as pas les permissions nécessaires pour utiliser cette commande.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ Je n'ai pas les permissions nécessaires pour exécuter cette commande.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant. Utilise `+help` pour voir l'usage correct.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Argument invalide. Vérifie ta commande.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"❌ Cette commande est en cooldown. Réessaye dans {error.retry_after:.1f}s.")
    else:
        logger.error(f"Command error in {ctx.command}: {error}", exc_info=error)
        await ctx.send("❌ Une erreur est survenue lors de l'exécution de la commande.")

# ==================== LANCEMENT DU BOT ====================
if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    
    if not TOKEN:
        logger.error("DISCORD_TOKEN missing in environment variables")
        print("❌ DISCORD_TOKEN manquant dans les variables d'environnement")
        print("💡 Crée un fichier .env avec : DISCORD_TOKEN=ton_token_ici")
        exit(1)
    
    logger.info("Starting Hoshikuzu bot...")
    print("🚀 Démarrage du bot Hoshikuzu...")
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.error("Invalid Discord token")
        print("❌ Token Discord invalide. Vérifie ta variable d'environnement DISCORD_TOKEN.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=e)
        print(f"❌ Erreur fatale : {e}")TS ====================
class CloseButton(Button):
    def __init__(self):
        super().__init__(label="Fermer le ticket", style=discord.ButtonStyle.red, emoji="🔒")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔒 Ce ticket sera supprimé dans 5 secondes...", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket fermé par {interaction.user}")
            logger.info(f"Ticket {interaction.channel.name} closed by {interaction.user}")
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseButton())

@bot.command(name="ticket")
async def ticket(ctx):
    """Crée un ticket privé"""
    for channel in ctx.guild.text_channels:
        if f"ticket-{ctx.author.name}".lower() in channel.name.lower():
            return await ctx.send(f"❌ Tu as déjà un ticket ouvert : {channel.mention}", delete_after=5)
    
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    try:
        channel = await ctx.guild.create_text_channel(
            name=f"ticket-{ctx.author.name}",
            overwrites=overwrites,
            reason=f"Ticket créé par {ctx.author}"
        )
        
        ticket_roles = await get_conf(ctx.guild.id, "ticket_roles") or []
        for role_id in ticket_roles:
            role = ctx.guild.get_role(role_id)
            if role:
                await channel.set_permissions(role, read_messages=True, send_messages=True)
        
        embed = discord.Embed(
            title="🎫 Ticket ouvert",
            description=f"{ctx.author.mention}, explique ton problème ici.\nUn membre du staff va te répondre.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=f"Ticket de {ctx.author}", icon_url=ctx.author.display_avatar.url)
        
        await channel.send(embed=embed, view=TicketView())
        await ctx.send(f"✅ Ticket créé : {channel.mention}", delete_after=5)
        logger.info(f"Ticket created by {ctx.author} in {ctx.guild.name}")
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions pour créer un ticket.")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de la création du ticket : {e}")
        logger.error(f"Ticket creation error: {e}")

# ==================== TICKE
