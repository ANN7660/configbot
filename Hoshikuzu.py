#!/usr/bin/env python3
"""
Discord bot converted from your Node.js bot.
Features: prefix commands, interactive help, welcome/leave, tickets, role reacts,
temp voice channels, moderation (ban/unban/timeout), config storage in JSON.
Ready for hosting on Render as a Web Service (with FastAPI health endpoint).
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import threading

# Web server imports (placed near top per your request - Option A)
from fastapi import FastAPI
import uvicorn

from dotenv import load_dotenv
import discord
from discord import Embed, ButtonStyle, SelectOption
from discord.ext import commands, tasks
from discord.ui import View, Button, Select

# -------------------------
# FastAPI web server (top)
# -------------------------
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "service": "discord-bot"}

def run_webserver():
    # Render will set PORT environment variable; fallback to 10000
    port = int(os.environ.get("PORT", 10000))
    # uvicorn.run is blocking; run it in this thread
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

# We'll start the webserver thread later (after file load) to avoid import-time issues.
# Start it as a daemon so the process exits cleanly with the bot.
web_thread = threading.Thread(target=run_webserver, daemon=True)
web_thread.start()

# -------------------------
# Bot setup
# -------------------------
# Load .env if present
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is required.")

# Constants
DB_FILE = "config.json"
PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# --- Simple JSON storage ---
def load_config():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(cfg):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

config = load_config()

def get_gcfg(guild_id):
    gid = str(guild_id)
    if gid not in config:
        config[gid] = {
            "welcomeEmbed": None,
            "welcomeText": None,
            "leaveEmbed": None,
            "leaveText": None,
            "welcomeChannel": None,
            "leaveChannel": None,
            "ticketCategory": None,
            "ticketRoles": [],
            "ticketCounter": 0,
            "logChannel": None,
            "joinRole": None,
            "tempVocCategory": None,
            "tempVocJoinChannel": None,
            "tempVocChannels": [],
            "roleReacts": {},  # message_id -> {roleId, emoji}
            "statsChannels": []  # ids for stats voice channels
        }
        save_config(config)
    return config[gid]

# --- Utilities ---
def parse_duration(duration: str) -> Optional[int]:
    """
    Parse duration strings like 10s, 5m, 1h, 1d
    Returns seconds (int) or None if invalid.
    """
    if not duration:
        return None
    unit = duration[-1]
    try:
        value = int(duration[:-1])
    except ValueError:
        return None
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if unit not in multipliers:
        return None
    return value * multipliers[unit]

async def send_log(guild: discord.Guild, embed: Embed):
    gcfg = get_gcfg(guild.id)
    log_channel_id = gcfg.get("logChannel")
    if not log_channel_id:
        return
    try:
        ch = guild.get_channel(int(log_channel_id))
        if ch:
            await ch.send(embed=embed)
    except Exception:
        # ignore logging errors
        pass

# --- Help menu view (persistent) ---
class HelpSelect(Select):
    def __init__(self):
        options = [
            SelectOption(label="👋 Bienvenue & Départ", value="welcome"),
            SelectOption(label="🎫 Tickets", value="tickets"),
            SelectOption(label="🛡️ Modération", value="moderation"),
            SelectOption(label="🎭 Rôles & Réactions", value="roles"),
            SelectOption(label="🔊 Vocaux Temporaires", value="voice"),
            SelectOption(label="⚙️ Configuration", value="config")
        ]
        # custom_id is required for persistence
        super().__init__(
            placeholder="Sélectionner une catégorie",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="help_select"
        )

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "welcome":
            embed = Embed(title="👋 Bienvenue & Départ", color=0x2ecc71)
            embed.description = (
                "**!bvntext** `<message>`\n"
                "**!bvnembed** `<description>`\n"
                "**!leavetxt** `<message>`\n"
                "**!leaveembed** `<description>`\n\n"
                "Variables: `{user}` `{server}` `{membercount}`"
            )
        elif val == "tickets":
            embed = Embed(title="🎫 Tickets", color=0x3498db)
            embed.description = "**!ticketpanel** - créer panel\n**!ticketrole** @role - ajouter rôle ticket"
        elif val == "moderation":
            embed = Embed(title="🛡️ Modération", color=0xe74c3c)
            embed.description = "**!ban** `@user [raison]`\n**!unban** `<id>`\n**!mute** `@user <durée> [raison]`\n**!unmute** `@user`"
        elif val == "roles":
            embed = Embed(title="🎭 Rôles & Réactions", color=0x9b59b6)
            embed.description = "**!rolereact** `@role <emoji>`\n**!joinrole** `@role`"
        elif val == "voice":
            embed = Embed(title="🔊 Vocaux Temporaires", color=0xf39c12)
            embed.description = "**!createvoc** - créer système join-to-create"
        else:
            embed = Embed(title="⚙️ Configuration", color=0x95a5a6)
            embed.description = "**!config** - menu interactif"
        # edit the original message that contains the select
        try:
            await interaction.response.edit_message(embed=embed, view=self.view)
        except Exception:
            # fallback: send ephemeral message
            await interaction.response.send_message(embed=embed, ephemeral=True)

class HelpView(View):
    def __init__(self):
        # timeout=None to be persistent
        super().__init__(timeout=None)
        self.add_item(HelpSelect())

# --- Ticket Button View (persistent) ---
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        # We rely on the decorator-defined button below (avoid duplicate add_item)

    @discord.ui.button(label="📩 Créer un Ticket", style=ButtonStyle.primary, custom_id="create_ticket")
    async def create_ticket(self, button: Button, interaction: discord.Interaction):
        gcfg = get_gcfg(interaction.guild.id)
        # Check existing ticket by name
        existing = discord.utils.get(interaction.guild.text_channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing:
            await interaction.response.send_message(f"❌ Vous avez déjà un ticket: {existing.mention}", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            category_id = gcfg.get("ticketCategory")
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            }
            category_obj = interaction.guild.get_channel(int(category_id)) if category_id else None
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                category=category_obj,
                overwrites=overwrites
            )
            # add support roles permissions
            for rid in gcfg.get("ticketRoles", []):
                role = interaction.guild.get_role(int(rid))
                if role:
                    await channel.set_permissions(role, view_channel=True, send_messages=True, read_message_history=True)

            embed = Embed(title="🎫 Nouveau Ticket", description=f"Bonjour {interaction.user.mention}, décris ton problème.", color=0x3498db)
            close_view = View(timeout=None)
            close_view.add_item(Button(label="🔒 Fermer le Ticket", custom_id=f"close_ticket_{channel.id}", style=ButtonStyle.danger))
            mentions = interaction.user.mention + (" " + " ".join(f"<@&{r}>" for r in gcfg.get("ticketRoles", [])) if gcfg.get("ticketRoles") else "")
            await channel.send(content=mentions, embed=embed, view=close_view)
            await interaction.followup.send(f"✅ Ticket créé: {channel.mention}", ephemeral=True)

            log = Embed(title="🎫 Ticket Créé", description=f"**Créé par:** {interaction.user} \n**Salon:** {channel.mention}", color=0x3498db, timestamp=datetime.utcnow())
            await send_log(interaction.guild, log)
        except Exception:
            await interaction.followup.send("❌ Erreur lors de la création du ticket.", ephemeral=True)

# Close ticket buttons are handled in on_interaction
@bot.event
async def on_interaction(interaction: discord.Interaction):
    # Only handle component interactions here
    if interaction.type != discord.InteractionType.component:
        return
    cid = interaction.data.get("custom_id", "")
    if cid.startswith("close_ticket_"):
        confirm = View(timeout=None)
        confirm.add_item(Button(label="✅ Confirmer", custom_id=f"confirm_close_{interaction.channel.id}", style=ButtonStyle.danger))
        confirm.add_item(Button(label="❌ Annuler", custom_id="cancel_close", style=ButtonStyle.secondary))
        await interaction.response.send_message(embed=Embed(title="❓ Confirmer la fermeture", description="Êtes-vous sûr de fermer ce ticket ?"), view=confirm, ephemeral=True)
        return
    if cid.startswith("confirm_close_"):
        try:
            await interaction.response.edit_message(content="🔒 Fermeture du ticket...", embed=None, view=None)
        except Exception:
            pass
        try:
            log = Embed(title="🔒 Ticket Fermé", description=f"**Fermé par:** {interaction.user}\n**Salon:** {interaction.channel.name}", timestamp=datetime.utcnow(), color=0xe74c3c)
            await send_log(interaction.guild, log)
            await asyncio.sleep(1.5)
            await interaction.channel.delete(reason=f"Ticket fermé par {interaction.user}")
        except Exception:
            pass
        return
    if cid == "cancel_close":
        try:
            await interaction.response.edit_message(content="✅ Fermeture annulée.", embed=None, view=None)
        except Exception:
            try:
                await interaction.response.send_message("✅ Fermeture annulée.", ephemeral=True)
            except Exception:
                pass
        return

# === Stats updater task & command ===
_stats_task = None
_stats_task_lock = asyncio.Lock()

async def stats_updater_loop():
    """Background loop that updates stats channels every 60s for guilds with statsChannels configured."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            for guild in bot.guilds:
                gcfg = get_gcfg(guild.id)
                chan_ids = gcfg.get("statsChannels") or []
                # Expecting 4 voice channel ids in order: members, bots, in_voice, total_channels
                if len(chan_ids) < 4:
                    continue
                # fetch channels
                channels = []
                for cid in chan_ids:
                    try:
                        ch = guild.get_channel(int(cid))
                        channels.append(ch)
                    except Exception:
                        channels.append(None)
                members = guild.member_count
                bots = len([m for m in guild.members if m.bot])
                in_voice = len([m for m in guild.members if m.voice and m.voice.channel])
                total_channels = len(guild.channels)
                # update names if channel exists
                try:
                    if channels[0]:
                        await channels[0].edit(name=f"👥 Membres : {members}")
                    if channels[1]:
                        await channels[1].edit(name=f"🤖 Bots : {bots}")
                    if channels[2]:
                        await channels[2].edit(name=f"🔊 En vocal : {in_voice}")
                    if channels[3]:
                        await channels[3].edit(name=f"📁 Salons : {total_channels}")
                except Exception:
                    # ignore per-guild update errors
                    pass
        except Exception:
            # ignore global errors and continue
            pass
        await asyncio.sleep(60)

# --- Events: ready, join/leave, reactions, voice state updates ---
@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user} (id: {bot.user.id})")
    # Ensure persistent views (Select/button custom_id + timeout=None required)
    try:
        bot.add_view(HelpView())
        bot.add_view(TicketView())
    except Exception as e:
        print("Erreur add_view:", e)

    # Start stats updater once
    global _stats_task
    async with _stats_task_lock:
        if _stats_task is None:
            _stats_task = bot.loop.create_task(stats_updater_loop())

@bot.event
async def on_member_join(member: discord.Member):
    gcfg = get_gcfg(member.guild.id)
    # assign join role
    jr = gcfg.get("joinRole")
    if jr:
        role = member.guild.get_role(int(jr))
        if role:
            try:
                await member.add_roles(role)
            except Exception:
                pass
    # welcome messages
    wc = gcfg.get("welcomeChannel")
    if wc:
        ch = member.guild.get_channel(int(wc))
        if ch:
            if gcfg.get("welcomeEmbed"):
                we = gcfg["welcomeEmbed"]
                try:
                    color_val = int(we.get("color", "0x2ecc71").replace("#", "0x"), 16)
                except Exception:
                    color_val = 0x2ecc71
                embed = Embed(
                    title=we.get("title", "Bienvenue!"),
                    description=we.get("description", "").replace("{user}", member.mention).replace("{server}", member.guild.name).replace("{membercount}", str(member.guild.member_count)),
                    color=color_val
                )
                try:
                    embed.set_thumbnail(url=member.display_avatar.url)
                except Exception:
                    pass
                await ch.send(embed=embed)
            if gcfg.get("welcomeText"):
                txt = gcfg["welcomeText"].replace("{user}", member.mention).replace("{server}", member.guild.name).replace("{membercount}", str(member.guild.member_count))
                await ch.send(txt)
    # log
    log = Embed(title="📥 Membre Rejoint", description=f"**Membre:** {member} (`{member.id}`)\n**Compte créé:** <t:{int(member.created_at.timestamp())}:R>", color=0x2ecc71, timestamp=datetime.utcnow())
    try:
        await send_log(member.guild, log)
    except Exception:
        pass

@bot.event
async def on_member_remove(member: discord.Member):
    gcfg = get_gcfg(member.guild.id)
    lc = gcfg.get("leaveChannel")
    if lc:
        ch = member.guild.get_channel(int(lc))
        if ch:
            if gcfg.get("leaveEmbed"):
                le = gcfg["leaveEmbed"]
                try:
                    color_val = int(le.get("color", "0xff0000").replace("#", "0x"), 16)
                except Exception:
                    color_val = 0xff0000
                embed = Embed(
                    title=le.get("title", "Au revoir!"),
                    description=le.get("description", "").replace("{user}", member.name).replace("{server}", member.guild.name).replace("{membercount}", str(member.guild.member_count)),
                    color=color_val
                )
                try:
                    embed.set_thumbnail(url=member.display_avatar.url)
                except Exception:
                    pass
                await ch.send(embed=embed)
            if gcfg.get("leaveText"):
                txt = gcfg["leaveText"].replace("{user}", member.name).replace("{server}", member.guild.name).replace("{membercount}", str(member.guild.member_count))
                await ch.send(txt)
    log = Embed(title="📤 Membre Parti", description=f"**Membre:** {member} (`{member.id}`)", color=0xe74c3c, timestamp=datetime.utcnow())
    try:
        await send_log(member.guild, log)
    except Exception:
        pass

# Reaction role handling (use raw events to work across cache)
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    gcfg = get_gcfg(payload.guild_id)
    rr = gcfg.get("roleReacts", {})
    msgid = str(payload.message_id)
    if msgid not in rr:
        return
    entry = rr[msgid]
    emoji = entry.get("emoji")
    if (payload.emoji.id and str(payload.emoji.id) == str(emoji)) or (payload.emoji.name == emoji):
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(entry["roleId"]))
        if member and role:
            try:
                await member.add_roles(role)
            except Exception:
                pass

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    gcfg = get_gcfg(payload.guild_id)
    rr = gcfg.get("roleReacts", {})
    msgid = str(payload.message_id)
    if msgid not in rr:
        return
    entry = rr[msgid]
    emoji = entry.get("emoji")
    if (payload.emoji.id and str(payload.emoji.id) == str(emoji)) or (payload.emoji.name == emoji):
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(entry["roleId"]))
        if member and role:
            try:
                await member.remove_roles(role)
            except Exception:
                pass

# Temporary voice channels
@bot.event
async def on_voice_state_update(member, before, after):
    # guard
    if member.guild is None:
        return
    gcfg = get_gcfg(member.guild.id)
    join_channel_id = gcfg.get("tempVocJoinChannel")
    temp_list = gcfg.get("tempVocChannels", [])
    # Create
    if after.channel and join_channel_id and str(after.channel.id) == str(join_channel_id) and (not before.channel or before.channel.id != after.channel.id):
        try:
            category = member.guild.get_channel(int(gcfg.get("tempVocCategory"))) if gcfg.get("tempVocCategory") else None
            temp = await member.guild.create_voice_channel(name=f"🎤 {member.name}", category=category)
            gcfg.setdefault("tempVocChannels", []).append(str(temp.id))
            save_config(config)
            await member.move_to(temp)
            # Give manager perms to owner
            await temp.set_permissions(member, manage_channels=True, move_members=True, connect=True)
        except Exception:
            pass
    # Delete empty
    if before.channel and str(before.channel.id) in temp_list:
        chan = before.channel
        if len(chan.members) == 0:
            try:
                await chan.delete()
            except Exception:
                pass
            gcfg["tempVocChannels"] = [x for x in gcfg.get("tempVocChannels", []) if x != str(chan.id)]
            save_config(config)

# --- Commands (prefix style) ---
def admin_required():
    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator
    return commands.check(predicate)

@bot.command(name="help")
async def cmd_help(ctx):
    embed = Embed(title="📚 Menu d'aide du Bot", description="Sélectionnez une catégorie pour voir les commandes", color=0x3498db)
    await ctx.reply(embed=embed, view=HelpView())

@bot.command(name="bvntext")
@admin_required()
async def cmd_bvntext(ctx, *, text: str = None):
    if not text:
        return await ctx.reply("❌ Usage: `!bvntext <message>`\nVariables: `{user}` `{server}` `{membercount}`")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg["welcomeText"] = text
    save_config(config)
    preview = text.replace("{user}", ctx.author.mention).replace("{server}", ctx.guild.name).replace("{membercount}", str(ctx.guild.member_count))
    await ctx.reply(f"✅ Message de bienvenue (texte) configuré!\nExemple: {preview}")

@bot.command(name="bvnembed")
@admin_required()
async def cmd_bvnembed(ctx, *, description: str = None):
    if not description:
        return await ctx.reply("❌ Usage: `!bvnembed <description>`")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg["welcomeEmbed"] = {"title": "👋 Bienvenue!", "description": description, "color": "#00ff00"}
    save_config(config)
    embed = Embed(title="👋 Bienvenue!", description=description.replace("{user}", ctx.author.mention).replace("{server}", ctx.guild.name).replace("{membercount}", str(ctx.guild.member_count)), color=0x00ff00)
    await ctx.reply("✅ Embed de bienvenue configuré! Aperçu:", embed=embed)

@bot.command(name="leavetxt")
@admin_required()
async def cmd_leavetxt(ctx, *, text: str = None):
    if not text:
        return await ctx.reply("❌ Usage: `!leavetxt <message>`")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg["leaveText"] = text
    save_config(config)
    await ctx.reply("✅ Message de départ (texte) configuré!")

@bot.command(name="leaveembed")
@admin_required()
async def cmd_leaveembed(ctx, *, description: str = None):
    if not description:
        return await ctx.reply("❌ Usage: `!leaveembed <description>`")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg["leaveEmbed"] = {"title": "👋 Au revoir!", "description": description, "color": "#ff0000"}
    save_config(config)
    await ctx.reply("✅ Embed de départ configuré!")

@bot.command(name="ticketpanel")
@admin_required()
async def cmd_ticketpanel(ctx):
    embed = Embed(title="🎫 Support Tickets", description="Cliquez ci-dessous pour créer un ticket de support.", color=0x3498db)
    view = TicketView()
    await ctx.send(embed=embed, view=view)
    try:
        await ctx.message.delete()
    except Exception:
        pass

@bot.command(name="ticketrole")
@admin_required()
async def cmd_ticketrole(ctx, role: discord.Role = None):
    if not role:
        return await ctx.reply("❌ Usage: `!ticketrole @role`")
    gcfg = get_gcfg(ctx.guild.id)
    if str(role.id) in gcfg.get("ticketRoles", []):
        return await ctx.reply("❌ Ce rôle est déjà dans la liste des rôles de ticket.")
    gcfg.setdefault("ticketRoles", []).append(str(role.id))
    save_config(config)
    await ctx.reply(f"✅ Le rôle {role.mention} sera mentionné dans les nouveaux tickets.")

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def cmd_ban(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
    if not member:
        return await ctx.reply("❌ Usage: `!ban @utilisateur [raison]`")
    try:
        await ctx.guild.ban(member, reason=reason)
        embed = Embed(title="🔨 Membre Banni", description=f"**Membre:** {member}\n**Raison:** {reason}\n**Modérateur:** {ctx.author}", color=0xe74c3c, timestamp=datetime.utcnow())
        await ctx.reply(embed=embed)
        await send_log(ctx.guild, embed)
    except Exception:
        await ctx.reply("❌ Impossible de bannir cet utilisateur.")

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def cmd_unban(ctx, user_id: int = None):
    if not user_id:
        return await ctx.reply("❌ Usage: `!unban <ID utilisateur>`")
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.reply(f"✅ L'utilisateur avec l'ID `{user_id}` a été débanni.")
    except Exception:
        await ctx.reply("❌ Impossible de débannir cet utilisateur.")

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def cmd_mute(ctx, member: discord.Member = None, duration: str = None, *, reason: str = "Aucune raison fournie"):
    if not member or not duration:
        return await ctx.reply("❌ Usage: `!mute @membre <durée> [raison]` (ex: 10m, 1h)")
    secs = parse_duration(duration)
    if secs is None:
        return await ctx.reply("❌ Durée invalide. Utilisez: 10s, 5m, 1h, 1d")
    until = datetime.utcnow() + timedelta(seconds=secs)
    try:
        await member.edit(communication_disabled_until=until, reason=reason)
        embed = Embed(title="🔇 Membre Mute", description=f"**Membre:** {member}\n**Durée:** {duration}\n**Raison:** {reason}\n**Modérateur:** {ctx.author}", color=0xe67e22, timestamp=datetime.utcnow())
        await ctx.reply(embed=embed)
        await send_log(ctx.guild, embed)
    except Exception:
        await ctx.reply("❌ Impossible de mute ce membre.")

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def cmd_unmute(ctx, member: discord.Member = None):
    if not member:
        return await ctx.reply("❌ Usage: `!unmute @membre`")
    try:
        await member.edit(communication_disabled_until=None)
        await ctx.reply(f"✅ {member} a été unmute.")
    except Exception:
        await ctx.reply("❌ Impossible de unmute ce membre.")

@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def cmd_lock(ctx):
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.reply("🔒 Salon verrouillé! Seuls les modérateurs peuvent écrire.")
    except Exception:
        await ctx.reply("❌ Impossible de verrouiller ce salon.")

@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def cmd_unlock(ctx):
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
        await ctx.reply("🔓 Salon déverrouillé!")
    except Exception:
        await ctx.reply("❌ Impossible de déverrouiller ce salon.")

@bot.command(name="modlent")
@commands.has_permissions(manage_channels=True)
async def cmd_modlent(ctx, seconds: int = 5):
    if seconds < 0 or seconds > 21600:
        return await ctx.reply("❌ Le délai doit être entre 0 et 21600 secondes (6 heures).")
    try:
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.reply(f"🐌 Mode lent activé: {seconds} secondes entre chaque message.")
    except Exception:
        await ctx.reply("❌ Impossible de définir le mode lent.")

@bot.command(name="moderapide")
@commands.has_permissions(manage_channels=True)
async def cmd_moderapide(ctx):
    try:
        await ctx.channel.edit(slowmode_delay=0)
        await ctx.reply("⚡ Mode lent désactivé!")
    except Exception:
        await ctx.reply("❌ Impossible de retirer le mode lent.")

@bot.command(name="rolereact")
@commands.has_permissions(manage_roles=True)
async def cmd_rolereact(ctx, role: discord.Role = None, emoji: str = None, *, description: str = "Réagissez pour obtenir ce rôle!"):
    if not role or not emoji:
        return await ctx.reply("❌ Usage: `!rolereact @role <emoji> [description]`")
    embed = Embed(title="🎭 Rôles Réactifs", description=f"{emoji} - {role.mention}\n\n{description}", color=0x9b59b6)
    msg = await ctx.send(embed=embed)
    try:
        await msg.add_reaction(emoji)
    except Exception:
        pass
    gcfg = get_gcfg(ctx.guild.id)
    gcfg.setdefault("roleReacts", {})[str(msg.id)] = {"roleId": str(role.id), "emoji": emoji}
    save_config(config)
    try:
        await ctx.message.delete()
    except Exception:
        pass

@bot.command(name="createvoc")
@commands.has_permissions(manage_channels=True)
async def cmd_createvoc(ctx):
    try:
        # create category if not exists
        category = discord.utils.get(ctx.guild.categories, name="🔊 Vocaux Temporaires")
        if not category:
            category = await ctx.guild.create_category("🔊 Vocaux Temporaires")
        join = await ctx.guild.create_voice_channel("➕ Rejoindre pour créer", category=category)
        gcfg = get_gcfg(ctx.guild.id)
        gcfg["tempVocCategory"] = str(category.id)
        gcfg["tempVocJoinChannel"] = str(join.id)
        save_config(config)
        await ctx.reply("✅ Système de vocal temporaire créé! Rejoignez le salon pour créer votre propre vocal.")
    except Exception:
        await ctx.reply("❌ Erreur lors de la création du système de vocal temporaire.")

@bot.command(name="joinrole")
@admin_required()
async def cmd_joinrole(ctx, role: discord.Role = None):
    if not role:
        return await ctx.reply("❌ Usage: `!joinrole @role`")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg["joinRole"] = str(role.id)
    save_config(config)
    await ctx.reply(f"✅ Le rôle {role.mention} sera maintenant donné aux nouveaux membres.")

@bot.command(name="config")
@admin_required()
async def cmd_config(ctx):
    embed = Embed(title="⚙️ Configuration du Bot", description="Sélectionnez ce que vous souhaitez configurer", color=0x3498db)
    view = View(timeout=60)
    select = Select(placeholder="Sélectionner une option", min_values=1, max_values=1, options=[
        SelectOption(label="👋 Salon de Bienvenue (channel)", value="welcome_channel"),
        SelectOption(label="✉️ Message de Bienvenue (texte)", value="welcome_text"),
        SelectOption(label="🖼️ Embed de Bienvenue", value="welcome_embed"),
        SelectOption(label="👋 Salon de Départ", value="leave_channel"),
        SelectOption(label="🎫 Catégorie Tickets", value="ticket_category"),
        SelectOption(label="📝 Salon de Logs", value="log_channel"),
        SelectOption(label="👤 Rôle Nouveaux Membres", value="join_role"),
    ])
    async def select_callback(interaction: discord.Interaction):
        if interaction.user.id != ctx.author.id:
            await interaction.response.send_message("❌ Seul l'auteur de la commande peut répondre.", ephemeral=True)
            return
        opt = select.values[0]
        await interaction.response.send_message(f"📝 Mentionnez le salon/role/catégorie/texte pour **{opt}**:", ephemeral=True)
        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Temps écoulé.", ephemeral=True)
            return
        gcfg = get_gcfg(ctx.guild.id)
        # channels
        if opt == "welcome_channel":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if ch:
                gcfg["welcomeChannel"] = str(ch.id)
                save_config(config)
                await msg.reply(f"✅ Salon de bienvenue configuré: {ch.mention}")
                return
        if opt == "leave_channel":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if ch:
                gcfg["leaveChannel"] = str(ch.id)
                save_config(config)
                await msg.reply(f"✅ Salon de départ configuré: {ch.mention}")
                return
        if opt == "log_channel":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if ch:
                gcfg["logChannel"] = str(ch.id)
                save_config(config)
                await msg.reply(f"✅ Salon de logs configuré: {ch.mention}")
                return
        # ticket category
        if opt == "ticket_category":
            cat = msg.channel_mentions[0] if msg.channel_mentions else None
            if cat and isinstance(cat, discord.channel.CategoryChannel):
                gcfg["ticketCategory"] = str(cat.id)
                save_config(config)
                await msg.reply(f"✅ Catégorie tickets configurée: {cat.name}")
                return
        # join role
        if opt == "join_role":
            role = msg.role_mentions[0] if msg.role_mentions else None
            if role:
                gcfg["joinRole"] = str(role.id)
                save_config(config)
                await msg.reply(f"✅ Rôle configuré: {role.mention}")
                return
        # welcome text
        if opt == "welcome_text":
            # take the message content raw as template
            text = msg.content.strip()
            if text:
                gcfg["welcomeText"] = text
                save_config(config)
                await msg.reply("✅ Message de bienvenue (texte) configuré.")
                return
        # welcome embed (simple: title|description|#hexcolor) or accept JSON-ish? Keep simple:
        if opt == "welcome_embed":
            # Expect user to send: title | description | #hexcolor
            parts = [p.strip() for p in msg.content.split("|")]
            if len(parts) >= 2:
                title = parts[0]
                description = parts[1]
                color = parts[2] if len(parts) >= 3 else "#00ff00"
                gcfg["welcomeEmbed"] = {"title": title, "description": description, "color": color}
                save_config(config)
                await msg.reply(f"✅ Embed de bienvenue configuré (titre + description). Exemple de preview envoyé.")
                # send preview
                try:
                    color_val = int(color.replace("#", "0x"), 16)
                except Exception:
                    color_val = 0x00ff00
                preview = Embed(title=title, description=description.replace("{user}", ctx.author.mention).replace("{server}", ctx.guild.name).replace("{membercount}", str(ctx.guild.member_count)), color=color_val)
                await ctx.channel.send(embed=preview)
                return
        await msg.reply("❌ Élément invalide ou non trouvé / format incorrect.")
    select.callback = select_callback
    view.add_item(select)
    await ctx.reply(embed=embed, view=view)

# Command to create stats channels
@bot.command(name="createstats")
@commands.has_permissions(manage_channels=True)
async def cmd_createstats(ctx):
    gcfg = get_gcfg(ctx.guild.id)
    # If already created, refuse
    if gcfg.get("statsChannels"):
        return await ctx.reply("❌ Les salons statistiques existent déjà sur ce serveur.")
    # Create category
    try:
        category = discord.utils.get(ctx.guild.categories, name="📊・Statistiques")
        if not category:
            category = await ctx.guild.create_category("📊・Statistiques")
        # create four voice channels (so they show on sidebar and we can edit their names)
        ch1 = await ctx.guild.create_voice_channel(f"👥 Membres : {ctx.guild.member_count}", category=category)
        ch2 = await ctx.guild.create_voice_channel(f"🤖 Bots : {len([m for m in ctx.guild.members if m.bot])}", category=category)
        ch3 = await ctx.guild.create_voice_channel(f"🔊 En vocal : {len([m for m in ctx.guild.members if m.voice and m.voice.channel])}", category=category)
        ch4 = await ctx.guild.create_voice_channel(f"📁 Salons : {len(ctx.guild.channels)}", category=category)
        gcfg["statsChannels"] = [str(ch1.id), str(ch2.id), str(ch3.id), str(ch4.id)]
        save_config(config)
        await ctx.reply("✅ Salons statistiques créés.")
    except Exception as e:
        await ctx.reply("❌ Impossible de créer les salons statistiques.")
        print("createstats error:", e)

# Simple error handler
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.reply("❌ Vous n'avez pas la permission d'utiliser cette commande.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply("❌ Argument manquant.")
    else:
        # log unexpected errors to console for debugging
        print("Command error:", error)

# Run
if __name__ == "__main__":
    bot.run(TOKEN)
