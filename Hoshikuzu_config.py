#!/usr/bin/env python3


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
from datetime import timedelta

import discord
from discord.ext import commands
from discord.ui import View, Button, Select, ChannelSelect as DiscordChannelSelect, RoleSelect as DiscordRoleSelect

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
        "invites": {},
        "stats": {}
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
    """Sauvegarde les données de manière synchrone"""
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

# ==================== LOGS AVANCÉS ====================
@bot.event
async def on_message_delete(message: discord.Message):
    """Log des messages supprimés"""
    if message.author.bot or not message.guild:
        return
    
    e = discord.Embed(
        title="🗑️ Message supprimé",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    e.add_field(name="👤 Auteur", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
    e.add_field(name="📍 Salon", value=message.channel.mention, inline=True)
    e.add_field(name="🕐 Envoyé le", value=f"<t:{int(message.created_at.timestamp())}:F>", inline=False)
    
    if message.content:
        content = message.content[:1024] if len(message.content) > 1024 else message.content
        e.add_field(name="💬 Contenu", value=content, inline=False)
    
    if message.attachments:
        attachments_info = "\n".join([f"[{att.filename}]({att.url})" for att in message.attachments[:5]])
        e.add_field(name="📎 Pièces jointes", value=attachments_info, inline=False)
    
    e.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
    e.set_footer(text=f"Message ID: {message.id}")
    
    await send_log(message.guild, e)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """Log des messages édités"""
    if before.author.bot or not before.guild or before.content == after.content:
        return
    
    e = discord.Embed(
        title="✏️ Message édité",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    e.add_field(name="👤 Auteur", value=f"{before.author.mention} (`{before.author.id}`)", inline=True)
    e.add_field(name="📍 Salon", value=before.channel.mention, inline=True)
    e.add_field(name="🔗 Lien", value=f"[Voir le message]({after.jump_url})", inline=True)
    
    old_content = before.content[:1024] if len(before.content) > 1024 else before.content
    new_content = after.content[:1024] if len(after.content) > 1024 else after.content
    
    e.add_field(name="📝 Avant", value=old_content or "`Aucun contenu`", inline=False)
    e.add_field(name="✅ Après", value=new_content or "`Aucun contenu`", inline=False)
    
    e.set_author(name=before.author.display_name, icon_url=before.author.display_avatar.url)
    e.set_footer(text=f"Message ID: {before.id}")
    
    await send_log(before.guild, e)

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Log des changements de membres (rôles, pseudo, etc.)"""
    if before.bot:
        return
    
    if before.nick != after.nick:
        e = discord.Embed(
            title="✏️ Pseudo modifié",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        e.add_field(name="👤 Membre", value=f"{after.mention} (`{after.id}`)", inline=False)
        e.add_field(name="📝 Ancien pseudo", value=before.nick or "`Aucun`", inline=True)
        e.add_field(name="✅ Nouveau pseudo", value=after.nick or "`Aucun`", inline=True)
        e.set_thumbnail(url=after.display_avatar.url)
        await send_log(after.guild, e)
    
    if before.roles != after.roles:
        added_roles = [role for role in after.roles if role not in before.roles]
        removed_roles = [role for role in before.roles if role not in after.roles]
        
        if added_roles or removed_roles:
            e = discord.Embed(
                title="🎭 Rôles modifiés",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            e.add_field(name="👤 Membre", value=f"{after.mention} (`{after.id}`)", inline=False)
            
            if added_roles:
                roles_text = ", ".join([role.mention for role in added_roles])
                e.add_field(name="➕ Rôles ajoutés", value=roles_text, inline=False)
            
            if removed_roles:
                roles_text = ", ".join([role.mention for role in removed_roles])
                e.add_field(name="➖ Rôles retirés", value=roles_text, inline=False)
            
            e.set_thumbnail(url=after.display_avatar.url)
            await send_log(after.guild, e)

@bot.event
async def on_guild_channel_create(channel):
    """Log des créations de salons"""
    e = discord.Embed(
        title="➕ Salon créé",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    
    channel_type = {
        discord.ChannelType.text: "💬 Textuel",
        discord.ChannelType.voice: "🔊 Vocal",
        discord.ChannelType.category: "📁 Catégorie",
        discord.ChannelType.stage_voice: "🎤 Stage",
        discord.ChannelType.forum: "📋 Forum"
    }.get(channel.type, "❓ Autre")
    
    e.add_field(name="📍 Nom", value=channel.mention if hasattr(channel, 'mention') else channel.name, inline=True)
    e.add_field(name="🏷️ Type", value=channel_type, inline=True)
    e.add_field(name="🆔 ID", value=f"`{channel.id}`", inline=True)
    
    if channel.category:
        e.add_field(name="📁 Catégorie", value=channel.category.name, inline=False)
    
    e.set_footer(text=f"Salon ID: {channel.id}")
    await send_log(channel.guild, e)

@bot.event
async def on_guild_channel_delete(channel):
    """Log des suppressions de salons"""
    e = discord.Embed(
        title="🗑️ Salon supprimé",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    
    channel_type = {
        discord.ChannelType.text: "💬 Textuel",
        discord.ChannelType.voice: "🔊 Vocal",
        discord.ChannelType.category: "📁 Catégorie",
        discord.ChannelType.stage_voice: "🎤 Stage",
        discord.ChannelType.forum: "📋 Forum"
    }.get(channel.type, "❓ Autre")
    
    e.add_field(name="📍 Nom", value=channel.name, inline=True)
    e.add_field(name="🏷️ Type", value=channel_type, inline=True)
    e.add_field(name="🆔 ID", value=f"`{channel.id}`", inline=True)
    
    if channel.category:
        e.add_field(name="📁 Catégorie", value=channel.category.name, inline=False)
    
    e.set_footer(text=f"Salon ID: {channel.id}")
    await send_log(channel.guild, e)

@bot.event
async def on_guild_role_create(role: discord.Role):
    """Log des créations de rôles"""
    e = discord.Embed(
        title="➕ Rôle créé",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    e.add_field(name="🎭 Nom", value=role.mention, inline=True)
    e.add_field(name="🎨 Couleur", value=f"`{role.color}`", inline=True)
    e.add_field(name="🆔 ID", value=f"`{role.id}`", inline=True)
    e.set_footer(text=f"Rôle ID: {role.id}")
    await send_log(role.guild, e)

@bot.event
async def on_guild_role_delete(role: discord.Role):
    """Log des suppressions de rôles"""
    e = discord.Embed(
        title="🗑️ Rôle supprimé",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    e.add_field(name="🎭 Nom", value=role.name, inline=True)
    e.add_field(name="🎨 Couleur", value=f"`{role.color}`", inline=True)
    e.add_field(name="🆔 ID", value=f"`{role.id}`", inline=True)
    e.set_footer(text=f"Rôle ID: {role.id}")
    await send_log(role.guild, e)

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    """Log des bannissements"""
    e = discord.Embed(
        title="🔨 Membre banni",
        color=discord.Color.dark_red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    e.add_field(name="👤 Utilisateur", value=f"{user.mention} (`{user.id}`)", inline=False)
    e.add_field(name="📛 Tag", value=f"`{user.name}`", inline=True)
    e.set_thumbnail(url=user.display_avatar.url)
    e.set_footer(text=f"User ID: {user.id}")
    
    try:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id:
                e.add_field(name="👮 Modérateur", value=f"{entry.user.mention}", inline=True)
                if entry.reason:
                    e.add_field(name="📝 Raison", value=entry.reason, inline=False)
                break
    except:
        pass
    
    await send_log(guild, e)

@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    """Log des débannissements"""
    e = discord.Embed(
        title="✅ Membre débanni",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    e.add_field(name="👤 Utilisateur", value=f"{user.mention} (`{user.id}`)", inline=False)
    e.set_thumbnail(url=user.display_avatar.url)
    await send_log(guild, e)

@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    """Log des modifications du serveur"""
    changes = []
    
    if before.name != after.name:
        changes.append(f"**Nom:** `{before.name}` → `{after.name}`")
    if before.icon != after.icon:
        changes.append(f"**Icône:** Modifiée")
    if before.verification_level != after.verification_level:
        changes.append(f"**Niveau de vérification:** `{before.verification_level}` → `{after.verification_level}`")
    
    if changes:
        e = discord.Embed(
            title="⚙️ Serveur modifié",
            description="\n".join(changes),
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        if after.icon:
            e.set_thumbnail(url=after.icon.url)
        await send_log(after, e)

# ==================== TICKETS VIEWS ====================
class CloseButton(Button):
    def __init__(self):
        super().__init__(label="Fermer le ticket", style=discord.ButtonStyle.red, emoji="🔒", custom_id="ticket_close_button")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔒 Ce ticket sera supprimé dans 5 secondes...", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket fermé par {interaction.user}")
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseButton())

class CreateTicketButton(Button):
    def __init__(self):
        super().__init__(label="Créer un ticket", style=discord.ButtonStyle.green, emoji="🎫", custom_id="ticket_create_button")
    
    async def callback(self, interaction: discord.Interaction):
        for channel in interaction.guild.text_channels:
            if f"ticket-{interaction.user.name}".lower() in channel.name.lower():
                return await interaction.response.send_message(f"❌ Tu as déjà un ticket ouvert : {channel.mention}", ephemeral=True)
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        try:
            channel = await interaction.guild.create_text_channel(name=f"ticket-{interaction.user.name}", overwrites=overwrites)
            embed = discord.Embed(title="🎫 Ticket ouvert", description=f"{interaction.user.mention}, explique ton problème ici.", color=discord.Color.green())
            await channel.send(embed=embed, view=TicketView())
            await interaction.response.send_message(f"✅ Ticket créé : {channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CreateTicketButton())

class ReactionButton(Button):
    def __init__(self, emoji: str, role_id: int):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.gray, custom_id=f"reaction_role_{role_id}")
        self.role_id = role_id
    
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.response.send_message("❌ Rôle introuvable.", ephemeral=True)
        
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message(f"❌ Rôle **{role.name}** retiré", ephemeral=True)
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"✅ Rôle **{role.name}** ajouté", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Erreur lors de la gestion du rôle.", ephemeral=True)

# ==================== CONFIG VIEWS (VERSION CORRIGÉE) ====================
class ChannelSelect(DiscordChannelSelect):
    def __init__(self, config_type: str, placeholder: str):
        super().__init__(
            placeholder=placeholder, 
            min_values=1, 
            max_values=1, 
            custom_id=f"config_select_{config_type}",
            channel_types=[discord.ChannelType.text]
        )
        self.config_type = config_type
    
    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Permissions insuffisantes.", ephemeral=True)
        
        channel = self.values[0]
        config_keys = {
            "welcome_embed": "welcome_embed_channel", 
            "welcome_text": "welcome_text_channel",
            "leave_embed": "leave_embed_channel", 
            "leave_text": "leave_text_channel", 
            "logs": "logs_channel"
        }
        
        await set_conf(interaction.guild.id, config_keys[self.config_type], channel.id)
        await interaction.response.send_message(f"✅ Configuration mise à jour pour {channel.mention}", ephemeral=True)
        await update_config_embed(interaction)

class RoleSelect(DiscordRoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="🎭 Rôle automatique", 
            min_values=1, 
            max_values=1, 
            custom_id="config_select_join_role"
        )
    
    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Permissions insuffisantes.", ephemeral=True)
        
        role = self.values[0]
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message("❌ Rôle trop élevé.", ephemeral=True)
        
        await set_conf(interaction.guild.id, "role_join", role.id)
        await interaction.response.send_message(f"✅ Rôle {role.mention} configuré", ephemeral=True)
        await update_config_embed(interaction)

class ConfigView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ChannelSelect("welcome_embed", "📨 Bienvenue (Embed)"))
        self.add_item(ChannelSelect("leave_embed", "📤 Départ (Embed)"))
        self.add_item(ChannelSelect("logs", "📊 Salon de Logs"))
        self.add_item(RoleSelect())

class ConfigView2(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ChannelSelect("welcome_text", "💬 Bienvenue (Texte)"))
        self.add_item(ChannelSelect("leave_text", "💭 Départ (Texte)"))

async def update_config_embed(interaction: discord.Interaction):
    """Met à jour l'embed de configuration"""
    conf = await get_gconf(interaction.guild.id)
    e = discord.Embed(title="⚙️ Configuration", description=f"Config de **{interaction.guild.name}**", color=discord.Color.blue())
    
    for key, label in [("welcome_embed_channel", "📨 Bienvenue (Embed)"), ("welcome_text_channel", "💬 Bienvenue (Texte)"),
                       ("leave_embed_channel", "📤 Départ (Embed)"), ("leave_text_channel", "💭 Départ (Texte)"),
                       ("logs_channel", "📊 Logs")]:
        val = conf.get(key)
        e.add_field(name=label, value=f"<#{val}>" if val else "`Non configuré`", inline=True)
    
    role_join = conf.get("role_join")
    e.add_field(name="🎭 Rôle auto", value=f"<@&{role_join}>" if role_join else "`Non configuré`", inline=True)
    
    try:
        await interaction.message.edit(embed=e)
    except:
        pass

# ==================== READY ====================
@bot.event
async def on_ready():
    logger.info(f"Bot connected as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="hoshikuzu | +help"))
    bot.add_view(TicketPanelView())
    bot.add_view(TicketView())
    bot.add_view(ConfigView())
    bot.add_view(ConfigView2())

# ==================== TRACKING MESSAGES & VOCAL ====================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    
    # Track stats
    if message.guild:
        gid = str(message.guild.id)
        uid = str(message.author.id)
        cid = str(message.channel.id)
        
        async with data_lock:
            data.setdefault("stats", {}).setdefault(gid, {"messages": {}, "channels": {}, "daily": {}})
            data["stats"][gid]["messages"].setdefault(uid, 0)
            data["stats"][gid]["messages"][uid] += 1
            data["stats"][gid]["channels"].setdefault(cid, 0)
            data["stats"][gid]["channels"][cid] += 1
            today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
            data["stats"][gid]["daily"].setdefault(today, 0)
            data["stats"][gid]["daily"][today] += 1
            if data["stats"][gid]["messages"][uid] % 10 == 0:
                await asyncio.to_thread(save_data_sync, data)
    
    # Filtre liens
    if message.guild:
        gid = str(message.guild.id)
        async with data_lock:
            allowed_channels = data.get("allowed_links", {}).get(gid, [])
        
        url_regex = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        if message.channel.id not in allowed_channels and re.search(url_regex, message.content):
            try:
                await message.delete()
                await message.channel.send(f"❌ {message.author.mention}, liens non autorisés !", delete_after=5)
                e = discord.Embed(title="🔗 Lien supprimé", color=discord.Color.orange())
                e.add_field(name="Auteur", value=message.author.mention)
                e.add_field(name="Salon", value=message.channel.mention)
                await send_log(message.guild, e)
                return
            except:
                pass
    
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild = member.guild
    gid = str(guild.id)
    uid = str(member.id)
    
    # Track temps vocal
    if not member.bot:
        async with data_lock:
            data.setdefault("stats", {}).setdefault(gid, {}).setdefault("voice_tracking", {})
            
            if after.channel and not before.channel:
                data["stats"][gid]["voice_tracking"][uid] = {
                    "joined_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "channel_id": after.channel.id
                }
            elif before.channel and not after.channel:
                if uid in data["stats"][gid]["voice_tracking"]:
                    joined_time = datetime.datetime.fromisoformat(data["stats"][gid]["voice_tracking"][uid]["joined_at"])
                    duration = (datetime.datetime.now(datetime.timezone.utc) - joined_time).total_seconds()
                    data["stats"][gid].setdefault("voice_time", {}).setdefault(uid, 0)
                    data["stats"][gid]["voice_time"][uid] += duration
                    del data["stats"][gid]["voice_tracking"][uid]
                    await asyncio.to_thread(save_data_sync, data)
    
    # Vocaux temporaires
    trigger_channel_id = await get_conf(guild.id, "voc_trigger_channel")
    if after.channel and after.channel.id == trigger_channel_id:
        try:
            voc = await guild.create_voice_channel(name=f"🔊 {member.display_name}", category=after.channel.category)
            async with data_lock:
                data.setdefault("temp_vocs", {})[str(voc.id)] = {"owner": member.id, "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
                await asyncio.to_thread(save_data_sync, data)
            await member.move_to(voc)
        except:
            pass
    
    if before.channel:
        cid = str(before.channel.id)
        async with data_lock:
            if cid in data.get("temp_vocs", {}) and len(before.channel.members) == 0:
                try:
                    await before.channel.delete()
                    del data["temp_vocs"][cid]
                    await asyncio.to_thread(save_data_sync, data)
                except:
                    pass

# ==================== WELCOME / LEAVE ====================
async def send_welcome(member: discord.Member):
    conf = await get_gconf(member.guild.id)
    total = member.guild.member_count
    
    role_join_id = conf.get("role_join")
    if role_join_id:
        role = member.guild.get_role(role_join_id)
        if role:
            try:
                await member.add_roles(role)
            except:
                pass
    
    embed_ch = conf.get("welcome_embed_channel")
    if embed_ch:
        ch = member.guild.get_channel(embed_ch)
        if ch:
            e = discord.Embed(title="✨ Bienvenue !", description=f"{member.mention} vient de rejoindre ✨", color=discord.Color.green())
            e.add_field(name="Infos", value=f"{EMOJI} **BVN {member.mention}**\n{EMOJI} Nous sommes **{total} membres**.")
            e.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=e)
    
    text_ch = conf.get("welcome_text_channel")
    if text_ch:
        ch = member.guild.get_channel(text_ch)
        if ch:
            await ch.send(f"{EMOJI} **BVN {member.mention}**\n{EMOJI} Nous sommes **{total} membres**.")

async def send_leave(member: discord.Member):
    conf = await get_gconf(member.guild.id)
    total = member.guild.member_count
    
    embed_ch = conf.get("leave_embed_channel")
    if embed_ch:
        ch = member.guild.get_channel(embed_ch)
        if ch:
            e = discord.Embed(title="❌ Départ", description=f"{member.mention} vient de partir.", color=discord.Color.red())
            e.add_field(name="Infos", value=f"{EMOJI} {member.mention} a quitté...\n{EMOJI} Il reste **{total} membres**.")
            e.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=e)
    
    text_ch = conf.get("leave_text_channel")
    if text_ch:
        ch = member.guild.get_channel(text_ch)
        if ch:
            await ch.send(f"{EMOJI} {member.mention} a quitté...\n{EMOJI} Il reste **{total} membres**.")

@bot.event
async def on_member_join(member: discord.Member):
    await send_welcome(member)

@bot.event
async def on_member_remove(member: discord.Member):
    await send_leave(member)

# ==================== COMMANDES ====================
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🌿 Commandes Hoshikuzu", color=discord.Color.green())
    e.add_field(name="📊 Config", value="`+config` - Panel interactif\n`+setwelcome` `+setleave` `+setlogs` `+setjoinrole`", inline=False)
    e.add_field(name="🎫 Tickets", value="`+ticket` `+ticketpanel` `+close` `+ticketrole`", inline=False)
    e.add_field(name="🎭 Rôles", value="`+role` `+rolejoin` `+reactionrole`", inline=False)
    e.add_field(name="🔗 Liens", value="`+allowlink` `+disallowlink`", inline=False)
    e.add_field(name="🔊 Vocaux", value="`+createvoc` `+setupvoc`", inline=False)
    e.add_field(name="📊 Stats", value="`+stats` `+top` `+channelstats` `+voicestats` `+mystats` `+resetstats`", inline=False)
    e.add_field(name="👥 Invitations", value="`+invites` `+roleinvite`", inline=False)
    e.add_field(name="💬 Utilitaires", value="`+say`", inline=False)
    await ctx.send(embed=e)

@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config(ctx):
    conf = await get_gconf(ctx.guild.id)
    e = discord.Embed(title="⚙️ Configuration", description=f"Config de **{ctx.guild.name}**", color=discord.Color.blue())
    
    for key, label in [("welcome_embed_channel", "📨 Bienvenue (Embed)"), ("welcome_text_channel", "💬 Bienvenue (Texte)"),
                       ("leave_embed_channel", "📤 Départ (Embed)"), ("leave_text_channel", "💭 Départ (Texte)"),
                       ("logs_channel", "📊 Logs")]:
        val = conf.get(key)
        e.add_field(name=label, value=f"<#{val}>" if val else "`Non configuré`", inline=True)
    
    role_join = conf.get("role_join")
    e.add_field(name="🎭 Rôle auto", value=f"<@&{role_join}>" if role_join else "`Non configuré`", inline=True)
    
    # Envoi en deux messages avec les deux views
    await ctx.send(embed=e, view=ConfigView())
    await ctx.send("📝 **Configuration supplémentaire :**", view=ConfigView2())

@bot.command(name="setwelcome")
@commands.has_permissions(manage_guild=True)
async def setwelcome(ctx, channel: Optional[discord.TextChannel] = None, mode: Optional[str] = None):
    if not channel or not mode or mode.lower() not in ["embed", "text"]:
        return await ctx.send("❌ Usage : `+setwelcome #channel embed/text`")
    
    key = "welcome_embed_channel" if mode.lower() == "embed" else "welcome_text_channel"
    await set_conf(ctx.guild.id, key, channel.id)
    await ctx.send(f"✅ Bienvenue ({mode}) configuré dans {channel.mention}")

@bot.command(name="setleave")
@commands.has_permissions(manage_guild=True)
async def setleave(ctx, channel: Optional[discord.TextChannel] = None, mode: Optional[str] = None):
    if not channel or not mode or mode.lower() not in ["embed", "text"]:
        return await ctx.send("❌ Usage : `+setleave #channel embed/text`")
    
    key = "leave_embed_channel" if mode.lower() == "embed" else "leave_text_channel"
    await set_conf(ctx.guild.id, key, channel.id)
    await ctx.send(f"✅ Départ ({mode}) configuré dans {channel.mention}")

@bot.command(name="setjoinrole")
@commands.has_permissions(manage_guild=True)
async def setjoinrole(ctx, role: Optional[discord.Role] = None):
    if not role:
        return await ctx.send("❌ Usage : `+setjoinrole @role`")
    if role >= ctx.guild.me.top_role:
        return await ctx.send("❌ Rôle trop élevé.")
    
    await set_conf(ctx.guild.id, "role_join", role.id)
    await ctx.send(f"✅ Rôle {role.mention} attribué automatiquement.")

@bot.command(name="setlogs")
@commands.has_permissions(manage_guild=True)
async def setlogs(ctx, channel: Optional[discord.TextChannel] = None):
    if not channel:
        return await ctx.send("❌ Usage : `+setlogs #channel`")
    
    await set_conf(ctx.guild.id, "logs_channel", channel.id)
    await ctx.send(f"✅ Logs configurés : {channel.mention}")

@bot.command(name="invites")
async def invites(ctx, member: Optional[discord.Member] = None):
    member = member or ctx.author
    gid = str(ctx.guild.id)
    async with data_lock:
        count = data.get("invites", {}).get(gid, {}).get(str(member.id), {}).get("count", 0)
    
    e = discord.Embed(title=f"📊 Invitations de {member.display_name}", color=discord.Color.blue())
    e.add_field(name="Total", value=f"**{count}** invitation(s)")
    e.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=e)

@bot.command(name="roleinvite")
@commands.has_permissions(manage_guild=True)
async def roleinvite(ctx, count: Optional[int] = None, role: Optional[discord.Role] = None):
    if not count or not role:
        return await ctx.send("❌ Usage : `+roleinvite <nombre> @role`")
    if count < 1:
        return await ctx.send("❌ Nombre invalide.")
    
    gid = str(ctx.guild.id)
    async with data_lock:
        data.setdefault("config", {}).setdefault(gid, {}).setdefault("role_invites", {})[str(role.id)] = count
        await asyncio.to_thread(save_data_sync, data)
    
    await ctx.send(f"✅ Rôle {role.mention} après **{count}** invitations.")

@bot.command(name="role")
@commands.has_permissions(manage_roles=True)
async def role(ctx, member: Optional[discord.Member] = None, role: Optional[discord.Role] = None):
    if not member or not role:
        return await ctx.send("❌ Usage : `+role @user @role`")
    
    try:
        if role in member.roles:
            await member.remove_roles(role)
            await ctx.send(f"❌ Rôle {role.mention} retiré de {member.mention}")
        else:
            await member.add_roles(role)
            await ctx.send(f"✅ Rôle {role.mention} ajouté à {member.mention}")
    except:
        await ctx.send("❌ Erreur lors de la gestion du rôle.")

@bot.command(name="rolejoin")
@commands.has_permissions(manage_guild=True)
async def rolejoin(ctx, role: Optional[discord.Role] = None):
    if not role:
        return await ctx.send("❌ Usage : `+rolejoin @role`")
    
    await set_conf(ctx.guild.id, "role_join", role.id)
    await ctx.send(f"✅ Rôle {role.mention} attribué automatiquement.")

@bot.command(name="ticket")
async def ticket(ctx):
    for channel in ctx.guild.text_channels:
        if f"ticket-{ctx.author.name}".lower() in channel.name.lower():
            return await ctx.send(f"❌ Tu as déjà un ticket ouvert : {channel.mention}", delete_after=5)
    
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    try:
        channel = await ctx.guild.create_text_channel(name=f"ticket-{ctx.author.name}", overwrites=overwrites)
        embed = discord.Embed(title="🎫 Ticket ouvert", description=f"{ctx.author.mention}, explique ton problème.", color=discord.Color.green())
        await channel.send(embed=embed, view=TicketView())
        await ctx.send(f"✅ Ticket créé : {channel.mention}", delete_after=5)
    except:
        await ctx.send("❌ Erreur lors de la création.")

@bot.command(name="ticketrole")
@commands.has_permissions(manage_guild=True)
async def ticketrole(ctx, role: Optional[discord.Role] = None):
    if not role:
        return await ctx.send("❌ Usage : `+ticketrole @role`")
    
    ticket_roles = await get_conf(ctx.guild.id, "ticket_roles") or []
    if role.id in ticket_roles:
        ticket_roles.remove(role.id)
        await set_conf(ctx.guild.id, "ticket_roles", ticket_roles)
        await ctx.send(f"❌ Rôle {role.mention} retiré.")
    else:
        ticket_roles.append(role.id)
        await set_conf(ctx.guild.id, "ticket_roles", ticket_roles)
        await ctx.send(f"✅ Rôle {role.mention} ajouté.")

@bot.command(name="close")
async def close(ctx):
    if "ticket-" not in ctx.channel.name:
        return await ctx.send("❌ Cette commande fonctionne uniquement dans un ticket.")
    
    await ctx.send("🔒 Fermeture dans 5 secondes...")
    await asyncio.sleep(5)
    await ctx.channel.delete()

@bot.command(name="ticketpanel")
@commands.has_permissions(manage_guild=True)
async def ticketpanel(ctx):
    embed = discord.Embed(title="🎫 Système de Tickets", description="Clique pour créer un ticket.", color=discord.Color.blue())
    await ctx.send(embed=embed, view=TicketPanelView())

@bot.command(name="setupvoc")
@commands.has_permissions(manage_guild=True)
async def setup_voc(ctx, channel: Optional[discord.VoiceChannel] = None):
    if not channel:
        return await ctx.send("❌ Usage : `+setupvoc #salon`")
    
    await set_conf(ctx.guild.id, "voc_trigger_channel", channel.id)
    await channel.edit(name=VOC_TRIGGER_NAME)
    await ctx.send(f"✅ Salon trigger configuré : {channel.mention}")

@bot.command(name="createvoc")
@commands.has_permissions(manage_guild=True)
async def create_voc(ctx):
    voc_trigger = await ctx.guild.create_voice_channel(name=VOC_TRIGGER_NAME, category=ctx.channel.category)
    await set_conf(ctx.guild.id, "voc_trigger_channel", voc_trigger.id)
    await ctx.send(f"✅ Salon trigger créé : {voc_trigger.mention}")

@bot.command(name="allowlink")
@commands.has_permissions(manage_guild=True)
async def allow_link(ctx, channel: Optional[discord.TextChannel] = None):
    if not channel:
        return await ctx.send("❌ Usage : `+allowlink #channel`")
    
    gid = str(ctx.guild.id)
    async with data_lock:
        data.setdefault("allowed_links", {}).setdefault(gid, [])
        if channel.id not in data["allowed_links"][gid]:
            data["allowed_links"][gid].append(channel.id)
            await asyncio.to_thread(save_data_sync, data)
    
    await ctx.send(f"✅ Liens autorisés dans {channel.mention}")

@bot.command(name="disallowlink")
@commands.has_permissions(manage_guild=True)
async def disallow_link(ctx, channel: Optional[discord.TextChannel] = None):
    if not channel:
        return await ctx.send("❌ Usage : `+disallowlink #channel`")
    
    gid = str(ctx.guild.id)
    async with data_lock:
        if gid in data.get("allowed_links", {}) and channel.id in data["allowed_links"][gid]:
            data["allowed_links"][gid].remove(channel.id)
            await asyncio.to_thread(save_data_sync, data)
    
    await ctx.send(f"❌ Liens bloqués dans {channel.mention}")

@bot.command(name="say")
@commands.has_permissions(manage_guild=True)
async def say(ctx, *, msg: Optional[str] = None):
    if not msg:
        return await ctx.send("❌ Usage : `+say <message>`")
    
    try:
        await ctx.message.delete()
    except:
        pass
    await ctx.send(msg)

@bot.command(name="reactionrole")
@commands.has_permissions(manage_roles=True)
async def reactionrole(ctx, channel: Optional[discord.TextChannel] = None, emoji: Optional[str] = None, role: Optional[discord.Role] = None):
    if not all([channel, emoji, role]):
        return await ctx.send("❌ Usage : `+reactionrole #channel emoji @role`")
    
    view = View(timeout=None)
    view.add_item(ReactionButton(emoji, role.id))
    
    embed = discord.Embed(title="🎭 Rôles Réactions", description=f"Clique sur {emoji} pour {role.mention}", color=discord.Color.blue())
    await channel.send(embed=embed, view=view)
    await ctx.send(f"✅ Rôle réaction configuré dans {channel.mention}")

# ==================== STATS ====================
@bot.command(name="stats")
async def stats(ctx):
    gid = str(ctx.guild.id)
    async with data_lock:
        guild_stats = data.get("stats", {}).get(gid, {})
        messages_count = guild_stats.get("messages", {})
        daily_stats = guild_stats.get("daily", {})
        voice_time = guild_stats.get("voice_time", {})
    
    total_messages = sum(messages_count.values())
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    messages_today = daily_stats.get(today, 0)
    
    last_7_days = []
    for i in range(7):
        date = (datetime.datetime.now(datetime.timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        last_7_days.append(daily_stats.get(date, 0))
    avg_per_day = sum(last_7_days) / 7 if last_7_days else 0
    
    top_members = sorted(messages_count.items(), key=lambda x: x[1], reverse=True)[:3]
    total_voice_hours = sum(voice_time.values()) / 3600
    
    e = discord.Embed(title=f"📊 Stats de {ctx.guild.name}", color=discord.Color.blue())
    e.add_field(name="📈 Messages", value=f"**Total:** {total_messages:,}\n**Aujourd'hui:** {messages_today:,}\n**Moy/jour:** {int(avg_per_day):,}", inline=True)
    e.add_field(name="👥 Membres", value=f"**Total:** {ctx.guild.member_count}\n**Actifs:** {len(messages_count)}", inline=True)
    e.add_field(name="🔊 Vocal", value=f"**Temps total:** {int(total_voice_hours)}h", inline=True)
    
    if top_members:
        top_text = ""
        for i, (uid, count) in enumerate(top_members, 1):
            member = ctx.guild.get_member(int(uid))
            if member:
                medals = ["🥇", "🥈", "🥉"]
                top_text += f"{medals[i-1]} {member.mention} - **{count:,}** msgs\n"
        e.add_field(name="🏆 Top Actifs", value=top_text, inline=False)
    
    await ctx.send(embed=e)

@bot.command(name="top")
async def top(ctx, limit: int = 10):
    if limit < 1 or limit > 25:
        limit = 10
    
    gid = str(ctx.guild.id)
    async with data_lock:
        messages_count = data.get("stats", {}).get(gid, {}).get("messages", {})
    
    if not messages_count:
        return await ctx.send("❌ Aucune stat disponible.")
    
    top_members = sorted(messages_count.items(), key=lambda x: x[1], reverse=True)[:limit]
    e = discord.Embed(title=f"🏆 Top {limit} Actifs", color=discord.Color.gold())
    
    leaderboard = ""
    for i, (uid, count) in enumerate(top_members, 1):
        member = ctx.guild.get_member(int(uid))
        if member:
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"`#{i}`"
            leaderboard += f"{medal} **{member.display_name}** - {count:,} msgs\n"
    
    e.description = leaderboard
    await ctx.send(embed=e)

@bot.command(name="channelstats")
async def channelstats(ctx):
    gid = str(ctx.guild.id)
    async with data_lock:
        channels_count = data.get("stats", {}).get(gid, {}).get("channels", {})
    
    if not channels_count:
        return await ctx.send("❌ Aucune stat disponible.")
    
    top_channels = sorted(channels_count.items(), key=lambda x: x[1], reverse=True)[:10]
    e = discord.Embed(title="📊 Stats par salon", color=discord.Color.blue())
    
    stats_text = ""
    total_messages = sum(channels_count.values())
    
    for i, (cid, count) in enumerate(top_channels, 1):
        channel = ctx.guild.get_channel(int(cid))
        if channel:
            percentage = (count / total_messages * 100) if total_messages > 0 else 0
            bar_length = int(percentage / 5)
            bar = "█" * bar_length + "░" * (20 - bar_length)
            stats_text += f"`#{i}` {channel.mention}\n     {bar} **{count:,}** ({percentage:.1f}%)\n\n"
    
    e.description = stats_text
    await ctx.send(embed=e)

@bot.command(name="voicestats")
async def voicestats(ctx, member: discord.Member = None):
    gid = str(ctx.guild.id)
    async with data_lock:
        voice_time = data.get("stats", {}).get(gid, {}).get("voice_time", {})
    
    if not voice_time:
        return await ctx.send("❌ Aucune stat vocale disponible.")
    
    if member:
        uid = str(member.id)
        seconds = voice_time.get(uid, 0)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        
        e = discord.Embed(title=f"🔊 Stats vocales de {member.display_name}", color=discord.Color.blue())
        e.add_field(name="⏱️ Temps total", value=f"**{hours}h {minutes}min**", inline=False)
        e.set_thumbnail(url=member.display_avatar.url)
    else:
        top_voice = sorted(voice_time.items(), key=lambda x: x[1], reverse=True)[:10]
        e = discord.Embed(title="🔊 Top 10 Vocal", color=discord.Color.blue())
        
        leaderboard = ""
        for i, (uid, seconds) in enumerate(top_voice, 1):
            member = ctx.guild.get_member(int(uid))
            if member:
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"`#{i}`"
                leaderboard += f"{medal} **{member.display_name}** - {hours}h {minutes}min\n"
        
        e.description = leaderboard
    
    await ctx.send(embed=e)

@bot.command(name="mystats")
async def mystats(ctx):
    gid = str(ctx.guild.id)
    uid = str(ctx.author.id)
    
    async with data_lock:
        guild_stats = data.get("stats", {}).get(gid, {})
        my_messages = guild_stats.get("messages", {}).get(uid, 0)
        my_voice = guild_stats.get("voice_time", {}).get(uid, 0)
        all_messages = guild_stats.get("messages", {})
    
    sorted_messages = sorted(all_messages.items(), key=lambda x: x[1], reverse=True)
    msg_position = next((i for i, (u, _) in enumerate(sorted_messages, 1) if u == uid), None)
    
    voice_hours = int(my_voice // 3600)
    voice_minutes = int((my_voice % 3600) // 60)
    
    e = discord.Embed(title=f"📊 Tes stats", description=f"Stats de **{ctx.author.display_name}**", color=discord.Color.blue())
    e.add_field(name="💬 Messages", value=f"**{my_messages:,}** msgs\n🏆 Classement: **#{msg_position}**" if msg_position else "Aucun msg", inline=True)
    e.add_field(name="🔊 Vocal", value=f"**{voice_hours}h {voice_minutes}min**", inline=True)
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    
    await ctx.send(embed=e)

@bot.command(name="resetstats")
@commands.has_permissions(administrator=True)
async def resetstats(ctx):
    gid = str(ctx.guild.id)
    confirm_msg = await ctx.send("⚠️ **ATTENTION** : Supprimer TOUTES les stats ?\nRéagis ✅ pour confirmer ou ❌ pour annuler (30s)")
    
    await confirm_msg.add_reaction("✅")
    await confirm_msg.add_reaction("❌")
    
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
    
    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
        
        if str(reaction.emoji) == "✅":
            async with data_lock:
                if gid in data.get("stats", {}):
                    data["stats"][gid] = {"messages": {}, "channels": {}, "daily": {}, "voice_time": {}, "voice_tracking": {}}
                    await asyncio.to_thread(save_data_sync, data)
            await ctx.send("✅ Stats réinitialisées !")
        else:
            await ctx.send("❌ Annulé.")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ Temps écoulé, annulé.")

# ==================== ERREURS ====================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Permissions insuffisantes.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ Je n'ai pas les permissions nécessaires.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant. Utilise `+help`.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        logger.error(f"Command error: {error}")

# ==================== LANCEMENT ====================

# ==================== PANEL INTERNAL API (SECURISEE) ====================
# Requires: pip install flask
from flask import Flask, request, jsonify
import threading as _threading

panel_api = Flask("panel_api")
PANEL_SECRET = os.environ.get("PANEL_SECRET", None)  # set a strong secret in env

def _check_secret(req):
    if not PANEL_SECRET:
        # refuse if no secret configured
        return False
    token = req.headers.get("X-Panel-Token") or req.args.get("token")
    return token == PANEL_SECRET

@panel_api.route("/command", methods=["POST"])
def api_command():
    try:
        if not _check_secret(request):
            return jsonify({"error": "Unauthorized"}), 401

        data_in = request.get_json(force=True)
        if not data_in or "action" not in data_in:
            return jsonify({"error": "Invalid JSON or missing 'action'"}), 400

        action = data_in.get("action")
        guild_id = int(data_in.get("guild_id", 0))
        guild = bot.get_guild(guild_id)
        if not guild:
            return jsonify({"error": "Guild not found"}), 400

        # send a simple message in a channel
        if action == "send_message":
            channel_id = int(data_in.get("channel_id", 0))
            message = data_in.get("message", "")
            channel = guild.get_channel(channel_id)
            if not channel:
                return jsonify({"error": "Channel not found"}), 400
            fut = asyncio.run_coroutine_threadsafe(channel.send(message), bot.loop)
            fut.result(timeout=10)
            return jsonify({"status": "ok", "action": "send_message"}), 200

        # set a configuration key
        if action == "set_config":
            key = data_in.get("key")
            value = data_in.get("value")
            if not key:
                return jsonify({"error": "Missing key"}), 400
            coro = set_conf(guild_id, key, value)
            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            fut.result(timeout=10)
            return jsonify({"status": "ok", "action": "set_config"}), 200

        # get full guild config
        if action == "get_config":
            coro = get_gconf(guild_id)
            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            conf = fut.result(timeout=10)
            return jsonify({"status": "ok", "config": conf}), 200

        # get stats
        if action == "get_stats":
            gid = str(guild_id)
            async def _get():
                async with data_lock:
                    return data.get("stats", {}).get(gid, {})
            fut = asyncio.run_coroutine_threadsafe(_get(), bot.loop)
            stats = fut.result(timeout=10)
            return jsonify({"status": "ok", "stats": stats}), 200

        # create a ticket channel for a user
        if action == "create_ticket":
            user_id = int(data_in.get("user_id", 0))
            user = guild.get_member(user_id)
            if not user:
                return jsonify({"error": "User not found"}), 400
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            coro = guild.create_text_channel(name=f"ticket-{user.name}", overwrites=overwrites)
            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            channel = fut.result(timeout=10)
            coro2 = channel.send(embed=discord.Embed(title="🎫 Ticket créé via panel", description=f"{user.mention}, explique ton problème ici."))
            asyncio.run_coroutine_threadsafe(coro2, bot.loop).result(timeout=10)
            return jsonify({"status": "ok", "channel_id": channel.id}), 200

        return jsonify({"error": "Unknown action"}), 400

    except Exception as e:
        logger.exception("API command error")
        return jsonify({"error": str(e)}), 500

def start_panel_api():
    host = os.environ.get("PANEL_HOST", "127.0.0.1")
    port = int(os.environ.get("PANEL_PORT", 5005))
    # Run in a separate thread so it doesn't block the bot
    panel_api.run(host=host, port=port, debug=False, use_reloader=False)

# Start the API in a daemon thread
_threading.Thread(target=start_panel_api, daemon=True).start()

# ==================== RENDER-SAFE PANEL API & BOT START ====================
# On Render we must listen on 0.0.0.0:$PORT and run only one HTTP server.
# We'll run the Discord bot in a separate thread (asyncio event loop) and keep Flask as the main process.
from flask import Flask, request, jsonify
import threading as _threading

panel_api = Flask("panel_api")
PANEL_SECRET = os.environ.get("PANEL_SECRET", None)  # set a strong secret in Render env

def _check_secret(req):
    if not PANEL_SECRET:
        return False
    token = req.headers.get("X-Panel-Token") or req.args.get("token")
    return token == PANEL_SECRET

@panel_api.route("/command", methods=["POST"])
def api_command():
    try:
        if not _check_secret(request):
            return jsonify({"error": "Unauthorized"}), 401

        data_in = request.get_json(force=True)
        if not data_in or "action" not in data_in:
            return jsonify({"error": "Invalid JSON or missing 'action'"}), 400

        action = data_in.get("action")
        guild_id = int(data_in.get("guild_id", 0))
        guild = bot.get_guild(guild_id)
        if not guild:
            return jsonify({"error": "Guild not found"}), 400

        if action == "send_message":
            channel_id = int(data_in.get("channel_id", 0))
            message = data_in.get("message", "")
            channel = guild.get_channel(channel_id)
            if not channel:
                return jsonify({"error": "Channel not found"}), 400
            fut = asyncio.run_coroutine_threadsafe(channel.send(message), bot.loop)
            fut.result(timeout=10)
            return jsonify({"status": "ok", "action": "send_message"}), 200

        if action == "set_config":
            key = data_in.get("key")
            value = data_in.get("value")
            if not key:
                return jsonify({"error": "Missing key"}), 400
            coro = set_conf(guild_id, key, value)
            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            fut.result(timeout=10)
            return jsonify({"status": "ok", "action": "set_config"}), 200

        if action == "get_config":
            coro = get_gconf(guild_id)
            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            conf = fut.result(timeout=10)
            return jsonify({"status": "ok", "config": conf}), 200

        if action == "get_stats":
            gid = str(guild_id)
            async def _get():
                async with data_lock:
                    return data.get("stats", {}).get(gid, {})
            fut = asyncio.run_coroutine_threadsafe(_get(), bot.loop)
            stats = fut.result(timeout=10)
            return jsonify({"status": "ok", "stats": stats}), 200

        if action == "create_ticket":
            user_id = int(data_in.get("user_id", 0))
            user = guild.get_member(user_id)
            if not user:
                return jsonify({"error": "User not found"}), 400
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            coro = guild.create_text_channel(name=f"ticket-{user.name}", overwrites=overwrites)
            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            channel = fut.result(timeout=10)
            coro2 = channel.send(embed=discord.Embed(title="🎫 Ticket créé via panel", description=f"{user.mention}, explique ton problème ici."))
            asyncio.run_coroutine_threadsafe(coro2, bot.loop).result(timeout=10)
            return jsonify({"status": "ok", "channel_id": channel.id}), 200

        return jsonify({"error": "Unknown action"}), 400

    except Exception as e:
        logger.exception("API command error")
        return jsonify({"error": str(e)}), 500

def _start_bot_thread():
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        logger.error("DISCORD_TOKEN missing; bot will not start")
        return

    # Each thread needs its own event loop
    def _run():
        try:
            import asyncio as _asyncio
            _asyncio.set_event_loop(_asyncio.new_event_loop())
            loop = _asyncio.get_event_loop()
            loop.run_until_complete(bot.start(TOKEN))
        except Exception as exc:
            logger.exception("Discord bot thread error: %s", exc)

    t = _threading.Thread(target=_run, name="discord-bot-thread", daemon=True)
    t.start()
    logger.info("Discord bot thread started")

def start_panel_on_render():
    # Start the bot thread, then run Flask on 0.0.0.0:$PORT (required by Render)
    _start_bot_thread()
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 5000))
    panel_api.run(host=host, port=port, debug=False, use_reloader=False)

# NOTE: Do NOT start anything automatically here; the caller will call start_panel_on_render()


if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    
    if not TOKEN:
        logger.error("DISCORD_TOKEN missing")
        print("❌ DISCORD_TOKEN manquant")
        exit(1)
    
    logger.info("Starting Hoshikuzu bot...")
    print("🚀 Démarrage du bot Hoshikuzu...")
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.error("Invalid Discord token")
        print("❌ Token invalide.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        print(f"❌ Erreur fatale : {e}")
