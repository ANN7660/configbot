#!/usr/bin/env python3
\"\"\"Hoshikuzu.py - Discord bot (Noël mode)
This is the user's original bot code with minor corrections and a "Noël" (Christmas) mode toggle.
Changes made (kept minimal as requested):
 - Added CHRISTMAS_MODE toggle to apply festive titles / channel name prefixes / emojis.
 - Small robustness fixes (safe get for environment vars, minor typing hints).
 - No logic changes besides the Christmas-mode cosmetic adjustments.
\"\"\"

import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import threading

# Web server imports
from fastapi import FastAPI
import uvicorn

from dotenv import load_dotenv
import discord
from discord import Embed, ButtonStyle, SelectOption
from discord.ext import commands
from discord.ui import View, Button, Select

# -------------------------
# Configuration: Noël mode
# -------------------------
CHRISTMAS_MODE = True  # Set to False to disable Noël cosmetics

# -------------------------
# FastAPI web server (top)
# -------------------------
app = FastAPI()

@app.get(\"/\")
async def root():
    return {\"status\": \"ok\", \"service\": \"discord-bot\"}

def run_webserver():
    port = int(os.environ.get(\"PORT\", 10000))
    uvicorn.run(app, host=\"0.0.0.0\", port=port, log_level=\"info\")


web_thread = threading.Thread(target=run_webserver, daemon=True)
web_thread.start()

# -------------------------
# Bot setup
# -------------------------
load_dotenv()

TOKEN = os.getenv(\"DISCORD_TOKEN\")
if not TOKEN:
    raise RuntimeError(\"DISCORD_TOKEN environment variable is required.\")


DB_FILE = \"config.json\"
PREFIX = \"!\"

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
        with open(DB_FILE, \"w\", encoding=\"utf-8\") as f:
            json.dump({}, f, indent=2)
    with open(DB_FILE, \"r\", encoding=\"utf-8\") as f:
        return json.load(f)

def save_config(cfg):
    with open(DB_FILE, \"w\", encoding=\"utf-8\") as f:
        json.dump(cfg, f, indent=2)

config = load_config()

def get_gcfg(guild_id):
    gid = str(guild_id)
    if gid not in config:
        config[gid] = {
            # Welcome: separate channels for text and embed
            \"welcomeEmbed\": None,
            \"welcomeText\": None,
            \"welcomeEmbedChannel\": None,   # channel for embed welcomes
            \"welcomeTextChannel\": None,    # channel for text welcomes
            \"leaveEmbed\": None,
            \"leaveText\": None,
            \"leaveChannel\": None,
            \"ticketCategory\": None,
            \"ticketRoles\": [],
            \"ticketCounter\": 0,
            \"logChannel\": None,
            \"joinRole\": None,
            \"tempVocCategory\": None,
            \"tempVocJoinChannel\": None,
            \"tempVocChannels\": [],
            \"roleReacts\": {},  # message_id -> {roleId, emoji}
            \"statsChannels\": [],  # ids for stats voice channels
            \"openTickets\": {}  # channel_id -> {owner, created}
        }
        save_config(config)
    return config[gid]

# --- Utilities ---
def parse_duration(duration: str) -> Optional[int]:
    if not duration:
        return None
    unit = duration[-1]
    try:
        value = int(duration[:-1])
    except Exception:
        return None
    multipliers = {\"s\": 1, \"m\": 60, \"h\": 3600, \"d\": 86400}
    if unit not in multipliers:
        return None
    return value * multipliers[unit]

async def send_log(guild: discord.Guild, embed: Embed):
    gcfg = get_gcfg(guild.id)
    log_channel_id = gcfg.get(\"logChannel\")
    if not log_channel_id:
        return
    try:
        ch = guild.get_channel(int(log_channel_id))
        if ch:
            await ch.send(embed=embed)
    except Exception:
        pass

def sanitize_name(name: str) -> str:
    # simple sanitize for channel names
    return \"\".join(c for c in name.lower() if c.isalnum() or c in \"-_\").replace(\" \", \"-\")[:90]

def _noel_title(default: str) -> str:
    if CHRISTMAS_MODE:
        return f\"🎄 {default}\"
    return default

def _noel_channel_prefix(default_prefix: str) -> str:
    if CHRISTMAS_MODE:
        return f\"🎁 {default_prefix}\"
    return default_prefix

# --- Help menu view (persistent) ---
class HelpSelect(Select):
    def __init__(self):
        options = [
            SelectOption(label=\"👋 Bienvenue & Départ\", value=\"welcome\"),
            SelectOption(label=\"🎫 Tickets\", value=\"tickets\"),
            SelectOption(label=\"🛡️ Modération\", value=\"moderation\"),
            SelectOption(label=\"🎭 Rôles & Réactions\", value=\"roles\"),
            SelectOption(label=\"🔊 Vocaux Temporaires\", value=\"voice\"),
            SelectOption(label=\"⚙️ Configuration\", value=\"config\")
        ]
        super().__init__(placeholder=\"Sélectionner une catégorie\", min_values=1, max_values=1, options=options, custom_id=\"help_select\")

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == \"welcome\":
            embed = Embed(title=_noel_title(\"Bienvenue & Départ\"), color=0x2ecc71)
            embed.description = (
                \"**!bvntext** `<message>` — configure le message texte de bienvenue\\n\"
                \"**!bvnembed** `<description>` — configure l'embed de bienvenue\\n\"
                \"**!bvntextchannel** `#channel` — salon où envoyer le texte de bienvenue\\n\"
                \"**!bvnembedchannel** `#channel` — salon où envoyer l'embed de bienvenue\\n\\n\"
                \"Variables disponibles: `{user}` `{server}` `{membercount}`\"
            )
        elif val == \"tickets\":
            embed = Embed(title=_noel_title(\"Tickets\"), color=0x3498db)
            embed.description = \"**!ticketpanel** - créer le panel de tickets\\n**!ticketrole** @role - ajouter rôle support\\n**!ticketadmin** - panneau d'administration des tickets\"
        elif val == \"moderation\":
            embed = Embed(title=_noel_title(\"Modération\"), color=0xe74c3c)
            embed.description = \"**!ban** `@user [raison]`  •  **!unban** `<id>`  •  **!mute** `@user <durée>`  •  **!unmute** `@user`\"
        elif val == \"roles\":
            embed = Embed(title=_noel_title(\"Rôles & Réactions\"), color=0x9b59b6)
            embed.description = \"**!rolereact** `@role <emoji>`\\n**!joinrole** `@role`\"
        elif val == \"voice\":
            embed = Embed(title=_noel_title(\"Vocaux Temporaires\"), color=0xf39c12)
            embed.description = \"**!createvoc** - créer système join-to-create\"
        else:
            embed = Embed(title=_noel_title(\"Configuration\"), color=0x95a5a6)
            embed.description = \"**!config** - menu interactif\\n**!createstats** - crée 4 salons vocaux statistiques\"
        try:
            await interaction.response.edit_message(embed=embed, view=self.view)
        except Exception:
            await interaction.response.send_message(embed=embed, ephemeral=True)

class HelpView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(HelpSelect())

# --- Ticket Button View (persistent) ---
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label=\"📩 Créer un Ticket\", style=ButtonStyle.primary, custom_id=\"create_ticket\")
    async def create_ticket(self, button: Button, interaction: discord.Interaction):
        # interaction is the Interaction; button param present due to decorator signature
        try:
            gcfg = get_gcfg(interaction.guild.id)
        except Exception:
            await interaction.response.send_message(\"❌ Impossible de lire la configuration du serveur.\", ephemeral=True)
            return

        # prevent multiple tickets for same owner by checking openTickets
        existing = None
        for ch_id, info in (gcfg.get(\"openTickets\") or {}).items():
            if info.get(\"owner\") == str(interaction.user.id):
                # try to fetch channel
                try:
                    ch = interaction.guild.get_channel(int(ch_id))
                    if ch:
                        existing = ch
                        break
                except Exception:
                    pass
        if existing:
            await interaction.response.send_message(f\"❌ Vous avez déjà un ticket: {existing.mention}\", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            category_id = gcfg.get(\"ticketCategory\")
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            }
            category_obj = interaction.guild.get_channel(int(category_id)) if category_id else None

            # channel name friendly
            prefix = \"ticket-\"
            if CHRISTMAS_MODE:
                prefix = \"cadeau-\"  # french for gift, small cosmetic change
            name = sanitize_name(f\"{prefix}{interaction.user.name}\")
            # ensure uniqueness by appending counter if needed
            base_name = name
            counter = 1
            while discord.utils.get(interaction.guild.text_channels, name=name):
                name = f\"{base_name}-{counter}\"
                counter += 1

            channel = await interaction.guild.create_text_channel(
                name=name,
                category=category_obj,
                overwrites=overwrites
            )

            # add support roles permissions
            for rid in gcfg.get(\"ticketRoles\", []):
                try:
                    role = interaction.guild.get_role(int(rid))
                    if role:
                        await channel.set_permissions(role, view_channel=True, send_messages=True, read_message_history=True)
                except Exception:
                    pass

            # store open ticket
            gcfg.setdefault(\"openTickets\", {})[str(channel.id)] = {
                \"owner\": str(interaction.user.id),
                \"created\": int(datetime.utcnow().timestamp())
            }
            save_config(config)

            t_title = _noel_title(\"Nouveau Ticket\")
            embed = Embed(title=t_title, description=f\"Bonjour {interaction.user.mention}, décris ton problème ici. Un membre du support arrivera bientôt.\", color=0x3498db)
            close_view = View(timeout=None)
            close_view.add_item(Button(label=\"🔒 Fermer le Ticket\", custom_id=f\"close_ticket_{channel.id}\", style=ButtonStyle.danger))
            mentions = interaction.user.mention + (\" \" + \" \".join(f\"<@&{r}>\" for r in gcfg.get(\"ticketRoles\", [])) if gcfg.get(\"ticketRoles\") else \"\")
            await channel.send(content=mentions, embed=embed, view=close_view)

            await interaction.followup.send(f\"✅ Ticket créé: {channel.mention}\", ephemeral=True)

            log = Embed(title=_noel_title(\"Ticket Créé\"), description=f\"**Salon:** {channel.mention}\\n**Créé par:** {interaction.user} (`{interaction.user.id}`)\\n**Heure:** <t:{int(datetime.utcnow().timestamp())}:F>\", color=0x3498db, timestamp=datetime.utcnow())
            await send_log(interaction.guild, log)
        except Exception as e:
            await interaction.followup.send(\"❌ Erreur lors de la création du ticket.\", ephemeral=True)
            print(\"create_ticket error:\", e)

# Close ticket buttons are handled in on_interaction
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    cid = \"\"
    if interaction.data:
        cid = interaction.data.get(\"custom_id\", \"\") or interaction.data.get(\"customId\", \"\")
    if not cid:
        return

    # User clicked the close ticket button inside the ticket channel
    if cid.startswith(\"close_ticket_\"):
        # Show confirmation view (ephemeral)
        confirm = View(timeout=None)
        confirm.add_item(Button(label=\"✅ Confirmer\", custom_id=f\"confirm_close_{cid.split('_')[-1]}\", style=ButtonStyle.danger))
        confirm.add_item(Button(label=\"❌ Annuler\", custom_id=\"cancel_close\", style=ButtonStyle.secondary))
        try:
            await interaction.response.send_message(embed=Embed(title=_noel_title(\"Confirmer la fermeture\"), description=\"Êtes-vous sûr de fermer ce ticket ?\"), view=confirm, ephemeral=True)
        except Exception:
            pass
        return

    # Confirm close
    if cid.startswith(\"confirm_close_\"):
        chan_id = cid.replace(\"confirm_close_\", \"\")
        target_channel = None
        try:
            if interaction.channel and str(interaction.channel.id) == chan_id:
                target_channel = interaction.channel
            else:
                target_channel = interaction.guild.get_channel(int(chan_id)) if interaction.guild else None
        except Exception:
            target_channel = None

        try:
            gcfg = get_gcfg(interaction.guild.id)
            ticket_entry = gcfg.get(\"openTickets\", {}).get(str(chan_id))
            owner_mention = \"Inconnu\"
            if ticket_entry:
                owner_mention = f\"<@{ticket_entry.get('owner')}>\"
            log = Embed(title=_noel_title(\"Ticket Fermé\"), description=f\"**Salon:** {target_channel.mention if target_channel else chan_id}\\n**Fermé par:** {interaction.user} (`{interaction.user.id}`)\\n**Créé par:** {owner_mention}\\n**Heure:** <t:{int(datetime.utcnow().timestamp())}:F>\", color=0xe74c3c, timestamp=datetime.utcnow())
            await send_log(interaction.guild, log)
        except Exception as e:
            print(\"confirm_close logging error:\", e)

        try:
            # Edit ephemeral confirmation if possible
            try:
                await interaction.response.edit_message(content=\"🔒 Fermeture du ticket...\", embed=None, view=None)
            except Exception:
                # maybe already responded; ignore
                pass
            await asyncio.sleep(1.5)
            if target_channel:
                await target_channel.delete(reason=f\"Ticket fermé par {interaction.user}\")
            # remove from config
            try:
                gcfg = get_gcfg(interaction.guild.id)
                if str(chan_id) in gcfg.get(\"openTickets\", {}):
                    del gcfg[\"openTickets\"][str(chan_id)]
                    save_config(config)
            except Exception:
                pass
        except Exception:
            pass
        return

    if cid == \"cancel_close\":
        try:
            await interaction.response.edit_message(content=\"✅ Fermeture annulée.\", embed=None, view=None)
        except Exception:
            try:
                await interaction.response.send_message(\"✅ Fermeture annulée.\", ephemeral=True)
            except Exception:
                pass
        return

# === Admin ticket management view ===
class AdminTicketView(View):
    def __init__(self, gcfg, author_id):
        super().__init__(timeout=120)
        self.gcfg = gcfg
        self.author_id = author_id
        self.selected_channel: Optional[str] = None

        options = []
        for ch_id, info in (gcfg.get(\"openTickets\") or {}).items():
            owner_id = info.get(\"owner\")
            created_ts = info.get(\"created\")
            label_time = datetime.utcfromtimestamp(created_ts).strftime('%Y-%m-%d %H:%M') if created_ts else \"inconnu\"
            label = f\"{ch_id} • {label_time}\"
            desc = f\"Owner: <@{owner_id}>\" if owner_id else \"Owner: inconnu\"
            options.append(SelectOption(label=label[:100], value=str(ch_id), description=desc[:100]))
        if not options:
            options = [SelectOption(label=\"Aucun ticket ouvert\", value=\"none\", description=\"Il n'y a pas de tickets ouverts.\")]

        self.select = Select(placeholder=\"Sélectionnez un ticket\", min_values=1, max_values=1, options=options, custom_id=\"admin_ticket_select\")
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(\"❌ Seul l'auteur peut utiliser ce panneau.\", ephemeral=True)
            return
        self.selected_channel = self.select.values[0]
        await interaction.response.send_message(f\"✅ Ticket sélectionné: {self.selected_channel}\", ephemeral=True)

    @discord.ui.button(label=\"❌ Fermer le Ticket Sélectionné\", style=ButtonStyle.danger, custom_id=\"admin_close_selected\")
    async def close_selected(self, button: Button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(\"❌ Seul l'auteur peut utiliser ce panneau.\", ephemeral=True)
            return
        if not self.selected_channel or self.selected_channel == \"none\":
            await interaction.response.send_message(\"❌ Aucun ticket sélectionné.\", ephemeral=True)
            return
        ch_id = self.selected_channel
        ch = interaction.guild.get_channel(int(ch_id)) if interaction.guild else None
        gcfg = self.gcfg
        ticket_entry = gcfg.get(\"openTickets\", {}).get(str(ch_id))
        owner_mention = f\"<@{ticket_entry.get('owner')}>\" if ticket_entry else \"inconnu\"
        try:
            log = Embed(title=_noel_title(\"Ticket Fermé (Admin)\"), description=f\"**Salon:** {ch.mention if ch else ch_id}\\n**Fermé par:** {interaction.user}\\n**Créé par:** {owner_mention}\\n**Heure:** <t:{int(datetime.utcnow().timestamp())}:F>\", color=0xe74c3c, timestamp=datetime.utcnow())
            await send_log(interaction.guild, log)
        except Exception:
            pass
        try:
            if ch:
                await ch.delete(reason=f\"Ticket fermé par admin {interaction.user}\")
        except Exception as e:
            print(\"admin close_selected delete error:\", e)
        try:
            if str(ch_id) in gcfg.get(\"openTickets\", {}):
                del gcfg[\"openTickets\"][str(ch_id)]
                save_config(config)
        except Exception:
            pass
        await interaction.response.send_message(\"✅ Ticket fermé.\", ephemeral=True)

    @discord.ui.button(label=\"🧹 Fermer Tous les Tickets\", style=ButtonStyle.secondary, custom_id=\"admin_close_all\")
    async def close_all(self, button: Button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(\"❌ Seul l'auteur peut utiliser ce panneau.\", ephemeral=True)
            return
        gcfg = self.gcfg
        tickets = list((gcfg.get(\"openTickets\") or {}).keys())
        failures = 0
        for ch_id in tickets:
            try:
                ch = interaction.guild.get_channel(int(ch_id)) if interaction.guild else None
                ticket_entry = gcfg.get(\"openTickets\", {}).get(str(ch_id))
                owner_mention = f\"<@{ticket_entry.get('owner')}>\" if ticket_entry else \"inconnu\"
                try:
                    log = Embed(title=_noel_title(\"Ticket Fermé (Admin - Batch)\"), description=f\"**Salon:** {ch.mention if ch else ch_id}\\n**Fermé par:** {interaction.user}\\n**Créé par:** {owner_mention}\\n**Heure:** <t:{int(datetime.utcnow().timestamp())}:F>\", color=0xe74c3c, timestamp=datetime.utcnow())
                    await send_log(interaction.guild, log)
                except Exception:
                    pass
                if ch:
                    await ch.delete(reason=f\"Ticket fermé par admin {interaction.user}\")
                if str(ch_id) in gcfg.get(\"openTickets\", {}):
                    del gcfg[\"openTickets\"][str(ch_id)]
            except Exception as e:
                print(\"admin close_all error for\", ch_id, e)
                failures += 1
        save_config(config)
        await interaction.response.send_message(f\"✅ Fermeture terminée. Échecs: {failures}\", ephemeral=True)

    @discord.ui.button(label=\"🔄 Rafraîchir\", style=ButtonStyle.primary, custom_id=\"admin_refresh\")
    async def refresh(self, button: Button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(\"❌ Seul l'auteur peut utiliser ce panneau.\", ephemeral=True)
            return
        entries = self.gcfg.get(\"openTickets\", {}) or {}
        if not entries:
            await interaction.response.send_message(\"Aucun ticket ouvert.\", ephemeral=True)
            return
        text = \"Tickets ouverts:\\n\"
        for ch_id, info in entries.items():
            created = info.get(\"created\")
            owner = info.get(\"owner\")
            created_str = datetime.utcfromtimestamp(created).strftime(\"%Y-%m-%d %H:%M\") if created else \"inconnu\"
            text += f\"- <#{ch_id}> — {created_str} — <@{owner}>\\n\"
        await interaction.response.send_message(text, ephemeral=True)

# === Stats updater task & command ===
_stats_task = None
_stats_task_lock = asyncio.Lock()

async def stats_updater_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            for guild in bot.guilds:
                gcfg = get_gcfg(guild.id)
                chan_ids = gcfg.get(\"statsChannels\") or []
                if len(chan_ids) < 4:
                    continue
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
                try:
                    if channels[0]:
                        name0 = f\"👥 Membres : {members}\"
                        if CHRISTMAS_MODE:
                            name0 = f\"🎄 Membres : {members}\"
                        await channels[0].edit(name=name0)
                    if channels[1]:
                        name1 = f\"🤖 Bots : {bots}\"
                        if CHRISTMAS_MODE:
                            name1 = f\"🎄 Bots : {bots}\"
                        await channels[1].edit(name=name1)
                    if channels[2]:
                        name2 = f\"🔊 En vocal : {in_voice}\"
                        if CHRISTMAS_MODE:
                            name2 = f\"🎄 En vocal : {in_voice}\"
                        await channels[2].edit(name=name2)
                    if channels[3]:
                        name3 = f\"📁 Salons : {total_channels}\"
                        if CHRISTMAS_MODE:
                            name3 = f\"🎄 Salons : {total_channels}\"
                        await channels[3].edit(name=name3)
                except Exception:
                    pass
        except Exception:
            pass
        await asyncio.sleep(60)

# --- Events: ready, join/leave, reactions, voice state updates ---
@bot.event
async def on_ready():
    print(f\"✅ Bot connecté en tant que {bot.user} (id: {bot.user.id})\")
    try:
        bot.add_view(HelpView())
        bot.add_view(TicketView())
    except Exception as e:
        print(\"Erreur add_view:\", e)

    global _stats_task
    async with _stats_task_lock:
        if _stats_task is None:
            _stats_task = bot.loop.create_task(stats_updater_loop())

@bot.event
async def on_member_join(member: discord.Member):
    gcfg = get_gcfg(member.guild.id)
    jr = gcfg.get(\"joinRole\")
    if jr:
        role = member.guild.get_role(int(jr))
        if role:
            try:
                await member.add_roles(role)
            except Exception:
                pass

    # Welcome Embed -> separate channel
    we_ch = gcfg.get(\"welcomeEmbedChannel\")
    if we_ch:
        try:
            ch = member.guild.get_channel(int(we_ch))
            if ch and gcfg.get(\"welcomeEmbed\"):
                we = gcfg[\"welcomeEmbed\"]
                try:
                    color_val = int(we.get(\"color\", \"0x2ecc71\").replace(\"#\", \"0x\"), 16)
                except Exception:
                    color_val = 0x2ecc71
                title = we.get(\"title\", _noel_title(\"Bienvenue!\"))
                embed = Embed(
                    title=title,
                    description=we.get(\"description\", \"\").replace(\"{user}\", member.mention).replace(\"{server}\", member.guild.name).replace(\"{membercount}\", str(member.guild.member_count)),
                    color=color_val
                )
                try:
                    embed.set_thumbnail(url=member.display_avatar.url)
                except Exception:
                    pass
                embed.set_footer(text=f\"Membre #{member.guild.member_count}\")
                await ch.send(embed=embed)
        except Exception:
            pass

    # Welcome Text -> separate channel
    wt_ch = gcfg.get(\"welcomeTextChannel\")
    if wt_ch:
        try:
            ch = member.guild.get_channel(int(wt_ch))
            if ch and gcfg.get(\"welcomeText\"):
                txt = gcfg[\"welcomeText\"].replace(\"{user}\", member.mention).replace(\"{server}\", member.guild.name).replace(\"{membercount}\", str(member.guild.member_count))
                await ch.send(txt)
        except Exception:
            pass

    # log join
    log = Embed(title=_noel_title(\"Membre Rejoint\"), description=f\"**Membre:** {member} (`{member.id}`)\\n**Compte créé:** <t:{int(member.created_at.timestamp())}:R>\", color=0x2ecc71, timestamp=datetime.utcnow())
    try:
        await send_log(member.guild, log)
    except Exception:
        pass

@bot.event
async def on_member_remove(member: discord.Member):
    gcfg = get_gcfg(member.guild.id)
    lc = gcfg.get(\"leaveChannel\")
    if lc:
        ch = member.guild.get_channel(int(lc))
        if ch:
            if gcfg.get(\"leaveEmbed\"):
                le = gcfg[\"leaveEmbed\"]
                try:
                    color_val = int(le.get(\"color\", \"0xff0000\").replace(\"#\", \"0x\"), 16)
                except Exception:
                    color_val = 0xff0000
                title = le.get(\"title\", _noel_title(\"Au revoir!\"))
                embed = Embed(
                    title=title,
                    description=le.get(\"description\", \"\").replace(\"{user}\", member.name).replace(\"{server}\", member.guild.name).replace(\"{membercount}\", str(member.guild.member_count)),
                    color=color_val
                )
                try:
                    embed.set_thumbnail(url=member.display_avatar.url)
                except Exception:
                    pass
                await ch.send(embed=embed)
            if gcfg.get(\"leaveText\"):
                txt = gcfg[\"leaveText\"].replace(\"{user}\", member.name).replace(\"{server}\", member.guild.name).replace(\"{membercount}\", str(member.guild.member_count))
                await ch.send(txt)
    log = Embed(title=_noel_title(\"Membre Parti\"), description=f\"**Membre:** {member} (`{member.id}`)\", color=0xe74c3c, timestamp=datetime.utcnow())
    try:
        await send_log(member.guild, log)
    except Exception:
        pass

# Reaction role handling
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    gcfg = get_gcfg(payload.guild_id)
    rr = gcfg.get(\"roleReacts\", {})
    msgid = str(payload.message_id)
    if msgid not in rr:
        return
    entry = rr[msgid]
    emoji = entry.get(\"emoji\")
    if (getattr(payload.emoji, 'id', None) and str(payload.emoji.id) == str(emoji)) or (getattr(payload.emoji, 'name', None) == emoji):
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(entry[\"roleId\"]))
        if member and role:
            try:
                await member.add_roles(role)
            except Exception:
                pass

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    gcfg = get_gcfg(payload.guild_id)
    rr = gcfg.get(\"roleReacts\", {})
    msgid = str(payload.message_id)
    if msgid not in rr:
        return
    entry = rr[msgid]
    emoji = entry.get(\"emoji\")
    if (getattr(payload.emoji, 'id', None) and str(payload.emoji.id) == str(emoji)) or (getattr(payload.emoji, 'name', None) == emoji):
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(entry[\"roleId\"]))
        if member and role:
            try:
                await member.remove_roles(role)
            except Exception:
                pass

# Temporary voice channels
@bot.event
async def on_voice_state_update(member, before, after):
    if member.guild is None:
        return
    gcfg = get_gcfg(member.guild.id)
    join_channel_id = gcfg.get(\"tempVocJoinChannel\")
    temp_list = gcfg.get(\"tempVocChannels\", [])
    # Create
    if after.channel and join_channel_id and str(after.channel.id) == str(join_channel_id) and (not before.channel or before.channel.id != after.channel.id):
        try:
            category = member.guild.get_channel(int(gcfg.get(\"tempVocCategory\"))) if gcfg.get(\"tempVocCategory\") else None
            name_prefix = \"🎤\" if not CHRISTMAS_MODE else \"❄️\"
            temp = await member.guild.create_voice_channel(name=f\"{name_prefix} {member.name}\", category=category)
            gcfg.setdefault(\"tempVocChannels\", []).append(str(temp.id))
            save_config(config)
            await member.move_to(temp)
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
            gcfg[\"tempVocChannels\"] = [x for x in gcfg.get(\"tempVocChannels\", []) if x != str(chan.id)]
            save_config(config)

# --- Commands (prefix style) ---
def admin_required():
    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator
    return commands.check(predicate)

@bot.command(name=\"help\")
async def cmd_help(ctx):
    embed = Embed(title=_noel_title(\"Menu d'aide du Bot\"), description=\"Sélectionnez une catégorie pour voir les commandes\", color=0x3498db)
    await ctx.reply(embed=embed, view=HelpView())

@bot.command(name=\"bvntext\")
@admin_required()
async def cmd_bvntext(ctx, *, text: str = None):
    if not text:
        return await ctx.reply(\"❌ Usage: `!bvntext <message>`\\nVariables: `{user}` `{server}` `{membercount}`\")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg[\"welcomeText\"] = text
    save_config(config)
    preview = text.replace(\"{user}\", ctx.author.mention).replace(\"{server}\", ctx.guild.name).replace(\"{membercount}\", str(ctx.guild.member_count))
    await ctx.reply(f\"✅ Message de bienvenue (texte) configuré!\\nExemple: {preview}\")

@bot.command(name=\"bvnembed\")
@admin_required()
async def cmd_bvnembed(ctx, *, description: str = None):
    if not description:
        return await ctx.reply(\"❌ Usage: `!bvnembed <description>`\")
    gcfg = get_gcfg(ctx.guild.id)
    default_title = _noel_title(\"Bienvenue!\")
    gcfg[\"welcomeEmbed\"] = {\"title\": default_title, \"description\": description, \"color\": \"#2ecc71\"}
    save_config(config)
    embed = Embed(title=default_title, description=description.replace(\"{user}\", ctx.author.mention).replace(\"{server}\", ctx.guild.name).replace(\"{membercount}\", str(ctx.guild.member_count)), color=0x2ecc71)
    await ctx.reply(\"✅ Embed de bienvenue configuré! Aperçu:\", embed=embed)

@bot.command(name=\"bvntextchannel\")
@admin_required()
async def cmd_bvntextchannel(ctx, channel: discord.TextChannel = None):
    if not channel:
        return await ctx.reply(\"❌ Usage: `!bvntextchannel #channel`\")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg[\"welcomeTextChannel\"] = str(channel.id)
    save_config(config)
    await ctx.reply(f\"✅ Salon de bienvenue (texte) configuré: {channel.mention}\")

@bot.command(name=\"bvnembedchannel\")
@admin_required()
async def cmd_bvnembedchannel(ctx, channel: discord.TextChannel = None):
    if not channel:
        return await ctx.reply(\"❌ Usage: `!bvnembedchannel #channel`\")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg[\"welcomeEmbedChannel\"] = str(channel.id)
    save_config(config)
    await ctx.reply(f\"✅ Salon de bienvenue (embed) configuré: {channel.mention}\")

@bot.command(name=\"leavetxt\")
@admin_required()
async def cmd_leavetxt(ctx, *, text: str = None):
    if not text:
        return await ctx.reply(\"❌ Usage: `!leavetxt <message>`\")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg[\"leaveText\"] = text
    save_config(config)
    await ctx.reply(\"✅ Message de départ (texte) configuré!\")

@bot.command(name=\"leaveembed\")
@admin_required()
async def cmd_leaveembed(ctx, *, description: str = None):
    if not description:
        return await ctx.reply(\"❌ Usage: `!leaveembed <description>`\")
    gcfg = get_gcfg(ctx.guild.id)
    default_leave_title = _noel_title(\"Au revoir!\")
    gcfg[\"leaveEmbed\"] = {\"title\": default_leave_title, \"description\": description, \"color\": \"#ff0000\"}
    save_config(config)
    await ctx.reply(\"✅ Embed de départ configuré!\")

@bot.command(name=\"ticketpanel\")
@admin_required()
async def cmd_ticketpanel(ctx):
    embed = Embed(title=_noel_title(\"Support Tickets\"), description=\"Cliquez ci-dessous pour créer un ticket de support.\", color=0x3498db)
    view = TicketView()
    await ctx.send(embed=embed, view=view)
    try:
        await ctx.message.delete()
    except Exception:
        pass

@bot.command(name=\"ticketrole\")
@admin_required()
async def cmd_ticketrole(ctx, role: discord.Role = None):
    if not role:
        return await ctx.reply(\"❌ Usage: `!ticketrole @role`\")
    gcfg = get_gcfg(ctx.guild.id)
    if str(role.id) in gcfg.get(\"ticketRoles\", []):
        return await ctx.reply(\"❌ Ce rôle est déjà dans la liste des rôles de ticket.\")
    gcfg.setdefault(\"ticketRoles\", []).append(str(role.id))
    save_config(config)
    await ctx.reply(f\"✅ Le rôle {role.mention} sera mentionné dans les nouveaux tickets.\")

@bot.command(name=\"ticketadmin\")
@admin_required()
async def cmd_ticketadmin(ctx):
    gcfg = get_gcfg(ctx.guild.id)
    view = AdminTicketView(gcfg, ctx.author.id)
    embed = Embed(title=_noel_title(\"Panneau Admin - Tickets\"), color=0x95a5a6)
    entries = gcfg.get(\"openTickets\", {})
    if not entries:
        embed.description = \"Aucun ticket ouvert.\"
    else:
        s = \"\"
        for ch_id, info in entries.items():
            created_ts = info.get(\"created\")
            owner = info.get(\"owner\")
            created_str = datetime.utcfromtimestamp(created_ts).strftime(\"%Y-%m-%d %H:%M\") if created_ts else \"inconnu\"
            s += f\"- <#{ch_id}> — {created_str} — <@{owner}>\\n\"
        embed.description = s
    await ctx.reply(embed=embed, view=view, ephemeral=False)

# Moderation commands (ban/unban/mute/unmute/lock/unlock/slowmode) - unchanged logic
@bot.command(name=\"ban\")
@commands.has_permissions(ban_members=True)
async def cmd_ban(ctx, member: discord.Member = None, *, reason: str = \"Aucune raison fournie\"):
    if not member:
        return await ctx.reply(\"❌ Usage: `!ban @utilisateur [raison]`\")
    try:
        await ctx.guild.ban(member, reason=reason)
        embed = Embed(title=_noel_title(\"Membre Banni\"), description=f\"**Membre:** {member}\\n**Raison:** {reason}\\n**Modérateur:** {ctx.author}\", color=0xe74c3c, timestamp=datetime.utcnow())
        await ctx.reply(embed=embed)
        await send_log(ctx.guild, embed)
    except Exception:
        await ctx.reply(\"❌ Impossible de bannir cet utilisateur.\")

@bot.command(name=\"unban\")
@commands.has_permissions(ban_members=True)
async def cmd_unban(ctx, user_id: int = None):
    if not user_id:
        return await ctx.reply(\"❌ Usage: `!unban <ID utilisateur>`\")
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.reply(f\"✅ L'utilisateur avec l'ID `{user_id}` a été débanni.\")
    except Exception:
        await ctx.reply(\"❌ Impossible de débannir cet utilisateur.\")

@bot.command(name=\"mute\")
@commands.has_permissions(moderate_members=True)
async def cmd_mute(ctx, member: discord.Member = None, duration: str = None, *, reason: str = \"Aucune raison fournie\"):
    if not member or not duration:
        return await ctx.reply(\"❌ Usage: `!mute @membre <durée> [raison]` (ex: 10m, 1h)\")
    secs = parse_duration(duration)
    if secs is None:
        return await ctx.reply(\"❌ Durée invalide. Utilisez: 10s, 5m, 1h, 1d\")
    until = datetime.utcnow() + timedelta(seconds=secs)
    try:
        await member.edit(communication_disabled_until=until, reason=reason)
        embed = Embed(title=_noel_title(\"Membre Mute\"), description=f\"**Membre:** {member}\\n**Durée:** {duration}\\n**Raison:** {reason}\\n**Modérateur:** {ctx.author}\", color=0xe67e22, timestamp=datetime.utcnow())
        await ctx.reply(embed=embed)
        await send_log(ctx.guild, embed)
    except Exception:
        await ctx.reply(\"❌ Impossible de mute ce membre.\")

@bot.command(name=\"unmute\")
@commands.has_permissions(moderate_members=True)
async def cmd_unmute(ctx, member: discord.Member = None):
    if not member:
        return await ctx.reply(\"❌ Usage: `!unmute @membre`\")
    try:
        await member.edit(communication_disabled_until=None)
        await ctx.reply(f\"✅ {member} a été unmute.\")
    except Exception:
        await ctx.reply(\"❌ Impossible de unmute ce membre.\")

@bot.command(name=\"lock\")
@commands.has_permissions(manage_channels=True)
async def cmd_lock(ctx):
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.reply(\"🔒 Salon verrouillé! Seuls les modérateurs peuvent écrire.\")
    except Exception:
        await ctx.reply(\"❌ Impossible de verrouiller ce salon.\")

@bot.command(name=\"unlock\")
@commands.has_permissions(manage_channels=True)
async def cmd_unlock(ctx):
    if True:
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
            await ctx.reply(\"🔓 Salon déverrouillé!\")
        except Exception:
            await ctx.reply(\"❌ Impossible de déverrouiller ce salon.\")

@bot.command(name=\"modlent\")
@commands.has_permissions(manage_channels=True)
async def cmd_modlent(ctx, seconds: int = 5):
    if seconds < 0 or seconds > 21600:
        return await ctx.reply(\"❌ Le délai doit être entre 0 et 21600 secondes (6 heures).\" )
    try:
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.reply(f\"🐌 Mode lent activé: {seconds} secondes entre chaque message.\")
    except Exception:
        await ctx.reply(\"❌ Impossible de définir le mode lent.\")

@bot.command(name=\"moderapide\")
@commands.has_permissions(manage_channels=True)
async def cmd_moderapide(ctx):
    try:
        await ctx.channel.edit(slowmode_delay=0)
        await ctx.reply(\"⚡ Mode lent désactivé!\")
    except Exception:
        await ctx.reply(\"❌ Impossible de retirer le mode lent.\")

@bot.command(name=\"rolereact\")
@commands.has_permissions(manage_roles=True)
async def cmd_rolereact(ctx, role: discord.Role = None, emoji: str = None, *, description: str = \"Réagissez pour obtenir ce rôle!\"):
    if not role or not emoji:
        return await ctx.reply(\"❌ Usage: `!rolereact @role <emoji> [description]`\")
    embed = Embed(title=_noel_title(\"Rôles Réactifs\"), description=f\"{emoji} - {role.mention}\\n\\n{description}\", color=0x9b59b6)
    msg = await ctx.send(embed=embed)
    try:
        await msg.add_reaction(emoji)
    except Exception:
        pass
    gcfg = get_gcfg(ctx.guild.id)
    gcfg.setdefault(\"roleReacts\", {})[str(msg.id)] = {\"roleId\": str(role.id), \"emoji\": emoji}
    save_config(config)
    try:
        await ctx.message.delete()
    except Exception:
        pass

@bot.command(name=\"createvoc\")
@commands.has_permissions(manage_channels=True)
async def cmd_createvoc(ctx):
    try:
        cat_name = \"🔊 Vocaux Temporaires\"
        if CHRISTMAS_MODE:
            cat_name = _noel_channel_prefix(\"Vocaux Temporaires\")
        category = discord.utils.get(ctx.guild.categories, name=cat_name)
        if not category:
            category = await ctx.guild.create_category(cat_name)
        join = await ctx.guild.create_voice_channel(\"➕ Rejoindre pour créer\", category=category)
        gcfg = get_gcfg(ctx.guild.id)
        gcfg[\"tempVocCategory\"] = str(category.id)
        gcfg[\"tempVocJoinChannel\"] = str(join.id)
        save_config(config)
        await ctx.reply(\"✅ Système de vocal temporaire créé! Rejoignez le salon pour créer votre propre vocal.\")
    except Exception:
        await ctx.reply(\"❌ Erreur lors de la création du système de vocal temporaire.\")

@bot.command(name=\"joinrole\")
@admin_required()
async def cmd_joinrole(ctx, role: discord.Role = None):
    if not role:
        return await ctx.reply(\"❌ Usage: `!joinrole @role`\")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg[\"joinRole\"] = str(role.id)
    save_config(config)
    await ctx.reply(f\"✅ Le rôle {role.mention} sera maintenant donné aux nouveaux membres.\")

@bot.command(name=\"config\")
@admin_required()
async def cmd_config(ctx):
    embed = Embed(title=_noel_title(\"Configuration du Bot\"), description=\"Sélectionnez ce que vous souhaitez configurer\", color=0x3498db)
    view = View(timeout=60)
    select = Select(placeholder=\"Sélectionner une option\", min_values=1, max_values=1, options=[
        SelectOption(label=\"👋 Salon de Bienvenue (embed)\", value=\"welcome_embed_channel\"),
        SelectOption(label=\"👋 Salon de Bienvenue (texte)\", value=\"welcome_text_channel\"),
        SelectOption(label=\"✉️ Message de Bienvenue (texte)\", value=\"welcome_text\"),
        SelectOption(label=\"🖼️ Embed de Bienvenue (titre|description|#hexcolor)\", value=\"welcome_embed\"),
        SelectOption(label=\"👋 Salon de Départ\", value=\"leave_channel\"),
        SelectOption(label=\"🎫 Catégorie Tickets\", value=\"ticket_category\"),
        SelectOption(label=\"📝 Salon de Logs\", value=\"log_channel\"),
        SelectOption(label=\"👤 Rôle Nouveaux Membres\", value=\"join_role\"),
    ])
    async def select_callback(interaction: discord.Interaction):
        if interaction.user.id != ctx.author.id:
            await interaction.response.send_message(\"❌ Seul l'auteur de la commande peut répondre.\", ephemeral=True)
            return
        opt = select.values[0]
        await interaction.response.send_message(f\"📝 Envoyez maintenant la mention / le texte pour **{opt}**:\", ephemeral=True)
        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
        try:
            msg = await bot.wait_for(\"message\", check=check, timeout=60)
        except asyncio.TimeoutError:
            await interaction.followup.send(\"❌ Temps écoulé.\", ephemeral=True)
            return
        gcfg = get_gcfg(ctx.guild.id)
        if opt == \"welcome_embed_channel\":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if ch:
                gcfg[\"welcomeEmbedChannel\"] = str(ch.id)
                save_config(config)
                await msg.reply(f\"✅ Salon de bienvenue (embed) configuré: {ch.mention}\")
                return
        if opt == \"welcome_text_channel\":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if ch:
                gcfg[\"welcomeTextChannel\"] = str(ch.id)
                save_config(config)
                await msg.reply(f\"✅ Salon de bienvenue (texte) configuré: {ch.mention}\")
                return
        if opt == \"welcome_text\":
            text = msg.content.strip()
            if text:
                gcfg[\"welcomeText\"] = text
                save_config(config)
                await msg.reply(\"✅ Message de bienvenue (texte) configuré.\")
                return
        if opt == \"welcome_embed\":
            parts = [p.strip() for p in msg.content.split(\"|\")]
            if len(parts) >= 2:
                title = parts[0]
                description = parts[1]
                color = parts[2] if len(parts) >= 3 else \"#2ecc71\"
                gcfg[\"welcomeEmbed\"] = {\"title\": title, \"description\": description, \"color\": color}
                save_config(config)
                await msg.reply(\"✅ Embed de bienvenue configuré. Aperçu:\")
                try:
                    color_val = int(color.replace(\"#\", \"0x\"), 16)
                except Exception:
                    color_val = 0x2ecc71
                preview = Embed(title=title, description=description.replace(\"{user}\", ctx.author.mention).replace(\"{server}\", ctx.guild.name).replace(\"{membercount}\", str(ctx.guild.member_count)), color=color_val)
                await ctx.channel.send(embed=preview)
                return
        if opt == \"leave_channel\":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if ch:
                gcfg[\"leaveChannel\"] = str(ch.id)
                save_config(config)
                await msg.reply(f\"✅ Salon de départ configuré: {ch.mention}\")
                return
        if opt == \"ticket_category\":
            cat = msg.channel_mentions[0] if msg.channel_mentions else None
            if cat and isinstance(cat, discord.channel.CategoryChannel):
                gcfg[\"ticketCategory\"] = str(cat.id)
                save_config(config)
                await msg.reply(f\"✅ Catégorie tickets configurée: {cat.name}\")
                return
        if opt == \"log_channel\":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if ch:
                gcfg[\"logChannel\"] = str(ch.id)
                save_config(config)
                await msg.reply(f\"✅ Salon de logs configuré: {ch.mention}\")
                return
        if opt == \"join_role\":
            role = msg.role_mentions[0] if msg.role_mentions else None
            if role:
                gcfg[\"joinRole\"] = str(role.id)
                save_config(config)
                await msg.reply(f\"✅ Rôle configuré: {role.mention}\")
                return
        await msg.reply(\"❌ Élément invalide ou format incorrect.\")
    select.callback = select_callback
    view.add_item(select)
    await ctx.reply(embed=embed, view=view)

# Command to create stats channels
@bot.command(name=\"createstats\")
@commands.has_permissions(manage_channels=True)
async def cmd_createstats(ctx):
    gcfg = get_gcfg(ctx.guild.id)
    if gcfg.get(\"statsChannels\"):
        return await ctx.reply(\"❌ Les salons statistiques existent déjà sur ce serveur.\")
    try:
        category_name = \"📊・Statistiques\"
        if CHRISTMAS_MODE:
            category_name = _noel_channel_prefix(\"Statistiques\")
        category = discord.utils.get(ctx.guild.categories, name=category_name)
        if not category:
            category = await ctx.guild.create_category(category_name)
        ch1 = await ctx.guild.create_voice_channel((\"🎄 Membres : \" if CHRISTMAS_MODE else f\"👥 Membres : {ctx.guild.member_count}\"), category=category) if CHRISTMAS_MODE else await ctx.guild.create_voice_channel(f\"👥 Membres : {ctx.guild.member_count}\", category=category)
        # create non-festive names but will be updated by stats_updater_loop on next tick
        ch1 = await ctx.guild.create_voice_channel(f\"👥 Membres : {ctx.guild.member_count}\", category=category)
        ch2 = await ctx.guild.create_voice_channel(f\"🤖 Bots : {len([m for m in ctx.guild.members if m.bot])}\", category=category)
        ch3 = await ctx.guild.create_voice_channel(f\"🔊 En vocal : {len([m for m in ctx.guild.members if m.voice and m.voice.channel])}\", category=category)
        ch4 = await ctx.guild.create_voice_channel(f\"📁 Salons : {len(ctx.guild.channels)}\", category=category)
        gcfg[\"statsChannels\"] = [str(ch1.id), str(ch2.id), str(ch3.id), str(ch4.id)]
        save_config(config)
        await ctx.reply(\"✅ Salons statistiques créés.\")
    except Exception as e:
        await ctx.reply(\"❌ Impossible de créer les salons statistiques.\")
        print(\"createstats error:\", e)

# Simple error handler
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.reply(\"❌ Vous n'avez pas la permission d'utiliser cette commande.\")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(\"❌ Argument manquant.\")
    else:
        print(\"Command error:\", error)

# Run
if __name__ == \"__main__\":
    bot.run(TOKEN)
