import discord
from discord.ext import commands
from discord.ui import View, Button, ButtonStyle, Select, SelectOption
import asyncio
from datetime import datetime, timedelta
from typing import Optional

# ==============================================================================
# ⚠️ AJOUT ESSENTIEL : DÉFINITION DU BOT ET DES INTENTS
# Vous devez définir 'bot' AVANT d'utiliser @bot.event ou @bot.command.
# Assurez-vous d'avoir l'intent 'message_content' activé pour les commandes.
# Remplacez '!' par votre préfixe de commande souhaité.
# ==============================================================================
intents = discord.Intents.default()
intents.message_content = True  # Nécessaire pour traiter les commandes et les messages
intents.members = True          # Nécessaire pour les événements on_member_join/remove
intents.presences = True        # Nécessaire pour avoir une information complète sur les membres
bot = commands.Bot(command_prefix='!', intents=intents)

# ⚠️ PLACEHOLDER/SIMULATION des fonctions et variables manquantes
# Vous DEVEZ remplacer ces lignes par vos implémentations réelles.
def get_gcfg(guild_id):
    # Simule la récupération de la configuration de la guilde
    return {"openTickets": {}, "roleReacts": {}, "statsChannels": []}

def save_config(cfg):
    # Simule la sauvegarde de la configuration
    pass

async def send_log(guild, embed):
    # Simule l'envoi d'un journal de bord
    pass

def _noel_title(text):
    # Simule la décoration de Noël pour le titre
    return text

def _noel_channel_prefix(text):
    # Simule la décoration de Noël pour le nom de salon
    return text

def parse_duration(duration):
    # Simule l'analyse de durée pour la commande mute (ex: 10m -> 600)
    return 600

config = {} # Variable globale pour votre configuration
CHRISTMAS_MODE = False # Variable globale

# ⚠️ Vous devez définir les classes HelpView et TicketView ici ou les importer
class HelpView(View):
    def __init__(self):
        super().__init__(timeout=None)
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
# ==============================================================================

# Close ticket buttons are handled in on_interaction
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    cid = ""
    if interaction.data:
        cid = interaction.data.get("custom_id", "") or interaction.data.get("customId", "")
    if not cid:
        return

    # User clicked the close ticket button inside the ticket channel
    if cid.startswith("close_ticket_"):
        # Show confirmation view (ephemeral)
        confirm = View(timeout=None)
        confirm.add_item(Button(label="✅ Confirmer", custom_id=f"confirm_close_{cid.split('_')[-1]}", style=ButtonStyle.danger))
        confirm.add_item(Button(label="❌ Annuler", custom_id="cancel_close", style=ButtonStyle.secondary))
        try:
            await interaction.response.send_message(embed=Embed(title=_noel_title("Confirmer la fermeture"), description="Êtes-vous sûr de fermer ce ticket ?"), view=confirm, ephemeral=True)
        except Exception:
            pass
        return

    # Confirm close
    if cid.startswith("confirm_close_"):
        chan_id = cid.replace("confirm_close_", "")
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
            ticket_entry = gcfg.get("openTickets", {}).get(str(chan_id))
            owner_mention = "Inconnu"
            if ticket_entry:
                owner_mention = f"<@{ticket_entry.get('owner')}>"
            log = discord.Embed(title=_noel_title("Ticket Fermé"), description=f"**Salon:** {target_channel.mention if target_channel else chan_id}\n**Fermé par:** {interaction.user} (`{interaction.user.id}`)\n**Créé par:** {owner_mention}\n**Heure:** <t:{int(datetime.utcnow().timestamp())}:F>", color=0xe74c3c, timestamp=datetime.utcnow())
            await send_log(interaction.guild, log)
        except Exception as e:
            print("confirm_close logging error:", e)

        try:
            # Edit ephemeral confirmation if possible
            try:
                await interaction.response.edit_message(content="🔒 Fermeture du ticket...", embed=None, view=None)
            except Exception:
                # maybe already responded; ignore
                pass
            await asyncio.sleep(1.5)
            if target_channel:
                await target_channel.delete(reason=f"Ticket fermé par {interaction.user}")
            # remove from config
            try:
                gcfg = get_gcfg(interaction.guild.id)
                if str(chan_id) in gcfg.get("openTickets", {}):
                    del gcfg["openTickets"][str(chan_id)]
                    save_config(config)
            except Exception:
                pass
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

# === Admin ticket management view ===
class AdminTicketView(View):
    def __init__(self, gcfg, author_id):
        super().__init__(timeout=120)
        self.gcfg = gcfg
        self.author_id = author_id
        self.selected_channel: Optional[str] = None

        options = []
        for ch_id, info in (gcfg.get("openTickets") or {}).items():
            owner_id = info.get("owner")
            created_ts = info.get("created")
            label_time = datetime.utcfromtimestamp(created_ts).strftime('%Y-%m-%d %H:%M') if created_ts else "inconnu"
            label = f"{ch_id} • {label_time}"
            desc = f"Owner: <@{owner_id}>" if owner_id else "Owner: inconnu"
            options.append(SelectOption(label=label[:100], value=str(ch_id), description=desc[:100]))
        if not options:
            options = [SelectOption(label="Aucun ticket ouvert", value="none", description="Il n'y a pas de tickets ouverts.")]

        self.select = Select(placeholder="Sélectionnez un ticket", min_values=1, max_values=1, options=options, custom_id="admin_ticket_select")
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce panneau.", ephemeral=True)
            return
        self.selected_channel = self.select.values[0]
        await interaction.response.send_message(f"✅ Ticket sélectionné: {self.selected_channel}", ephemeral=True)

    @discord.ui.button(label="❌ Fermer le Ticket Sélectionné", style=ButtonStyle.danger, custom_id="admin_close_selected")
    async def close_selected(self, button: Button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce panneau.", ephemeral=True)
            return
        if not self.selected_channel or self.selected_channel == "none":
            await interaction.response.send_message("❌ Aucun ticket sélectionné.", ephemeral=True)
            return
        ch_id = self.selected_channel
        ch = interaction.guild.get_channel(int(ch_id)) if interaction.guild else None
        gcfg = self.gcfg
        ticket_entry = gcfg.get("openTickets", {}).get(str(ch_id))
        owner_mention = f"<@{ticket_entry.get('owner')}>" if ticket_entry else "inconnu"
        try:
            log = discord.Embed(title=_noel_title("Ticket Fermé (Admin)"), description=f"**Salon:** {ch.mention if ch else ch_id}\n**Fermé par:** {interaction.user}\n**Créé par:** {owner_mention}\n**Heure:** <t:{int(datetime.utcnow().timestamp())}:F>", color=0xe74c3c, timestamp=datetime.utcnow())
            await send_log(interaction.guild, log)
        except Exception:
            pass
        try:
            if ch:
                await ch.delete(reason=f"Ticket fermé par admin {interaction.user}")
        except Exception as e:
            print("admin close_selected delete error:", e)
        try:
            if str(ch_id) in gcfg.get("openTickets", {}):
                del gcfg["openTickets"][str(ch_id)]
                save_config(config)
        except Exception:
            pass
        await interaction.response.send_message("✅ Ticket fermé.", ephemeral=True)

    @discord.ui.button(label="🧹 Fermer Tous les Tickets", style=ButtonStyle.secondary, custom_id="admin_close_all")
    async def close_all(self, button: Button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce panneau.", ephemeral=True)
            return
        gcfg = self.gcfg
        tickets = list((gcfg.get("openTickets") or {}).keys())
        failures = 0
        for ch_id in tickets:
            try:
                ch = interaction.guild.get_channel(int(ch_id)) if interaction.guild else None
                ticket_entry = gcfg.get("openTickets", {}).get(str(ch_id))
                owner_mention = f"<@{ticket_entry.get('owner')}>" if ticket_entry else "inconnu"
                try:
                    log = discord.Embed(title=_noel_title("Ticket Fermé (Admin - Batch)"), description=f"**Salon:** {ch.mention if ch else ch_id}\n**Fermé par:** {interaction.user}\n**Créé par:** {owner_mention}\n**Heure:** <t:{int(datetime.utcnow().timestamp())}:F>", color=0xe74c3c, timestamp=datetime.utcnow())
                    await send_log(interaction.guild, log)
                except Exception:
                    pass
                if ch:
                    await ch.delete(reason=f"Ticket fermé par admin {interaction.user}")
                if str(ch_id) in gcfg.get("openTickets", {}):
                    del gcfg["openTickets"][str(ch_id)]
            except Exception as e:
                print("admin close_all error for", ch_id, e)
                failures += 1
        save_config(config)
        await interaction.response.send_message(f"✅ Fermeture terminée. Échecs: {failures}", ephemeral=True)

    @discord.ui.button(label="🔄 Rafraîchir", style=ButtonStyle.primary, custom_id="admin_refresh")
    async def refresh(self, button: Button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce panneau.", ephemeral=True)
            return
        entries = self.gcfg.get("openTickets", {}) or {}
        if not entries:
            await interaction.response.send_message("Aucun ticket ouvert.", ephemeral=True)
            return
        text = "Tickets ouverts:\n"
        for ch_id, info in entries.items():
            created = info.get("created")
            owner = info.get("owner")
            created_str = datetime.utcfromtimestamp(created).strftime("%Y-%m-%d %H:%M") if created else "inconnu"
            text += f"- <#{ch_id}> — {created_str} — <@{owner}>\n"
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
                chan_ids = gcfg.get("statsChannels") or []
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
                        name0 = f"👥 Membres : {members}"
                        if CHRISTMAS_MODE:
                            name0 = f"🎄 Membres : {members}"
                        await channels[0].edit(name=name0)
                    if channels[1]:
                        name1 = f"🤖 Bots : {bots}"
                        if CHRISTMAS_MODE:
                            name1 = f"🎄 Bots : {bots}"
                        await channels[1].edit(name=name1)
                    if channels[2]:
                        name2 = f"🔊 En vocal : {in_voice}"
                        if CHRISTMAS_MODE:
                            name2 = f"🎄 En vocal : {in_voice}"
                        await channels[2].edit(name=name2)
                    if channels[3]:
                        name3 = f"📁 Salons : {total_channels}"
                        if CHRISTMAS_MODE:
                            name3 = f"🎄 Salons : {total_channels}"
                        await channels[3].edit(name=name3)
                except Exception:
                    pass
        except Exception:
            pass
        await asyncio.sleep(60)

# --- Events: ready, join/leave, reactions, voice state updates ---
@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user} (id: {bot.user.id})")
    try:
        # Assurez-vous que HelpView et TicketView sont définies
        bot.add_view(HelpView())
        bot.add_view(TicketView())
    except Exception as e:
        print("Erreur add_view:", e)

    global _stats_task
    async with _stats_task_lock:
        if _stats_task is None:
            _stats_task = bot.loop.create_task(stats_updater_loop())

@bot.event
async def on_member_join(member: discord.Member):
    gcfg = get_gcfg(member.guild.id)
    jr = gcfg.get("joinRole")
    if jr:
        role = member.guild.get_role(int(jr))
        if role:
            try:
                await member.add_roles(role)
            except Exception:
                pass

    # Welcome Embed -> separate channel
    we_ch = gcfg.get("welcomeEmbedChannel")
    if we_ch:
        try:
            ch = member.guild.get_channel(int(we_ch))
            if ch and gcfg.get("welcomeEmbed"):
                we = gcfg["welcomeEmbed"]
                try:
                    color_val = int(we.get("color", "0x2ecc71").replace("#", "0x"), 16)
                except Exception:
                    color_val = 0x2ecc71
                title = we.get("title", _noel_title("Bienvenue!"))
                embed = discord.Embed(
                    title=title,
                    description=we.get("description", "").replace("{user}", member.mention).replace("{server}", member.guild.name).replace("{membercount}", str(member.guild.member_count)),
                    color=color_val
                )
                try:
                    embed.set_thumbnail(url=member.display_avatar.url)
                except Exception:
                    pass
                embed.set_footer(text=f"Membre #{member.guild.member_count}")
                await ch.send(embed=embed)
        except Exception:
            pass

    # Welcome Text -> separate channel
    wt_ch = gcfg.get("welcomeTextChannel")
    if wt_ch:
        try:
            ch = member.guild.get_channel(int(wt_ch))
            if ch and gcfg.get("welcomeText"):
                txt = gcfg["welcomeText"].replace("{user}", member.mention).replace("{server}", member.guild.name).replace("{membercount}", str(member.guild.member_count))
                await ch.send(txt)
        except Exception:
            pass

    # log join
    log = discord.Embed(title=_noel_title("Membre Rejoint"), description=f"**Membre:** {member} (`{member.id}`)\n**Compte créé:** <t:{int(member.created_at.timestamp())}:R>", color=0x2ecc71, timestamp=datetime.utcnow())
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
                title = le.get("title", _noel_title("Au revoir!"))
                embed = discord.Embed(
                    title=title,
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
    log = discord.Embed(title=_noel_title("Membre Parti"), description=f"**Membre:** {member} (`{member.id}`)", color=0xe74c3c, timestamp=datetime.utcnow())
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
    rr = gcfg.get("roleReacts", {})
    msgid = str(payload.message_id)
    if msgid not in rr:
        return
    entry = rr[msgid]
    emoji = entry.get("emoji")
    if (getattr(payload.emoji, 'id', None) and str(payload.emoji.id) == str(emoji)) or (getattr(payload.emoji, 'name', None) == emoji):
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
    if (getattr(payload.emoji, 'id', None) and str(payload.emoji.id) == str(emoji)) or (getattr(payload.emoji, 'name', None) == emoji):
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
    if member.guild is None:
        return
    gcfg = get_gcfg(member.guild.id)
    join_channel_id = gcfg.get("tempVocJoinChannel")
    temp_list = gcfg.get("tempVocChannels", [])
    # Create
    if after.channel and join_channel_id and str(after.channel.id) == str(join_channel_id) and (not before.channel or before.channel.id != after.channel.id):
        try:
            category = member.guild.get_channel(int(gcfg.get("tempVocCategory"))) if gcfg.get("tempVocCategory") else None
            name_prefix = "🎤" if not CHRISTMAS_MODE else "❄️"
            temp = await member.guild.create_voice_channel(name=f"{name_prefix} {member.name}", category=category)
            gcfg.setdefault("tempVocChannels", []).append(str(temp.id))
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
            gcfg["tempVocChannels"] = [x for x in gcfg.get("tempVocChannels", []) if x != str(chan.id)]
            save_config(config)

# --- Commands (prefix style) ---
def admin_required():
    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator
    return commands.check(predicate)

@bot.command(name="help")
async def cmd_help(ctx):
    embed = discord.Embed(title=_noel_title("Menu d'aide du Bot"), description="Sélectionnez une catégorie pour voir les commandes", color=0x3498db)
    # Assurez-vous que HelpView est définie
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
    default_title = _noel_title("Bienvenue!")
    gcfg["welcomeEmbed"] = {"title": default_title, "description": description, "color": "#2ecc71"}
    save_config(config)
    embed = discord.Embed(title=default_title, description=description.replace("{user}", ctx.author.mention).replace("{server}", ctx.guild.name).replace("{membercount}", str(ctx.guild.member_count)), color=0x2ecc71)
    await ctx.reply("✅ Embed de bienvenue configuré! Aperçu:", embed=embed)

@bot.command(name="bvntextchannel")
@admin_required()
async def cmd_bvntextchannel(ctx, channel: discord.TextChannel = None):
    if not channel:
        return await ctx.reply("❌ Usage: `!bvntextchannel #channel`")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg["welcomeTextChannel"] = str(channel.id)
    save_config(config)
    await ctx.reply(f"✅ Salon de bienvenue (texte) configuré: {channel.mention}")

@bot.command(name="bvnembedchannel")
@admin_required()
async def cmd_bvnembedchannel(ctx, channel: discord.TextChannel = None):
    if not channel:
        return await ctx.reply("❌ Usage: `!bvnembedchannel #channel`")
    gcfg = get_gcfg(ctx.guild.id)
    gcfg["welcomeEmbedChannel"] = str(channel.id)
    save_config(config)
    await ctx.reply(f"✅ Salon de bienvenue (embed) configuré: {channel.mention}")

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
    default_leave_title = _noel_title("Au revoir!")
    gcfg["leaveEmbed"] = {"title": default_leave_title, "description": description, "color": "#ff0000"}
    save_config(config)
    await ctx.reply("✅ Embed de départ configuré!")

@bot.command(name="ticketpanel")
@admin_required()
async def cmd_ticketpanel(ctx):
    embed = discord.Embed(title=_noel_title("Support Tickets"), description="Cliquez ci-dessous pour créer un ticket de support.", color=0x3498db)
    # Assurez-vous que TicketView est définie
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

@bot.command(name="ticketadmin")
@admin_required()
async def cmd_ticketadmin(ctx):
    gcfg = get_gcfg(ctx.guild.id)
    view = AdminTicketView(gcfg, ctx.author.id)
    embed = discord.Embed(title=_noel_title("Panneau Admin - Tickets"), color=0x95a5a6)
    entries = gcfg.get("openTickets", {})
    if not entries:
        embed.description = "Aucun ticket ouvert."
    else:
        s = ""
        for ch_id, info in entries.items():
            created_ts = info.get("created")
            owner = info.get("owner")
            created_str = datetime.utcfromtimestamp(created_ts).strftime("%Y-%m-%d %H:%M") if created_ts else "inconnu"
            s += f"- <#{ch_id}> — {created_str} — <@{owner}>\n"
        embed.description = s
    await ctx.reply(embed=embed, view=view, ephemeral=False)

# Moderation commands (ban/unban/mute/unmute/lock/unlock/slowmode)
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def cmd_ban(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
    if not member:
        return await ctx.reply("❌ Usage: `!ban @utilisateur [raison]`")
    try:
        await ctx.guild.ban(member, reason=reason)
        embed = discord.Embed(title=_noel_title("Membre Banni"), description=f"**Membre:** {member}\n**Raison:** {reason}\n**Modérateur:** {ctx.author}", color=0xe74c3c, timestamp=datetime.utcnow())
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
        embed = discord.Embed(title=_noel_title("Membre Mute"), description=f"**Membre:** {member}\n**Durée:** {duration}\n**Raison:** {reason}\n**Modérateur:** {ctx.author}", color=0xe67e22, timestamp=datetime.utcnow())
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
    embed = discord.Embed(title=_noel_title("Rôles Réactifs"), description=f"{emoji} - {role.mention}\n\n{description}", color=0x9b59b6)
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
        cat_name = "🔊 Vocaux Temporaires"
        if CHRISTMAS_MODE:
            cat_name = _noel_channel_prefix("Vocaux Temporaires")
        category = discord.utils.get(ctx.guild.categories, name=cat_name)
        if not category:
            category = await ctx.guild.create_category(cat_name)
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
    embed = discord.Embed(title=_noel_title("Configuration du Bot"), description="Sélectionnez ce que vous souhaitez configurer", color=0x3498db)
    view = View(timeout=60)
    select = Select(placeholder="Sélectionner une option", min_values=1, max_values=1, options=[
        SelectOption(label="👋 Salon de Bienvenue (embed)", value="welcome_embed_channel"),
        SelectOption(label="👋 Salon de Bienvenue (texte)", value="welcome_text_channel"),
        SelectOption(label="✉️ Message de Bienvenue (texte)", value="welcome_text"),
        SelectOption(label="🖼️ Embed de Bienvenue (titre|description|#hexcolor)", value="welcome_embed"),
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
        # Suppression de l'ancienne interaction pour éviter "Interaction Failed"
        await interaction.response.edit_message(content=f"📝 Envoyez maintenant la mention / le texte pour **{opt}**:", embed=None, view=None)
        
        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
        
        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            await ctx.followup.send("❌ Temps écoulé.", ephemeral=True) # Utiliser ctx.followup car interaction a déjà répondu
            return
        
        gcfg = get_gcfg(ctx.guild.id)
        
        # ⚠️ Début du bloc de code tronqué, maintenant corrigé:
        success = False
        response_msg = "✅ Configuration enregistrée!"

        if opt == "welcome_embed_channel":
            # Gère les mentions de canal
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if ch and isinstance(ch, discord.TextChannel):
                gcfg["welcomeEmbedChannel"] = str(ch.id)
                success = True
            else:
                response_msg = "❌ Veuillez mentionner un salon de texte valide."

        elif opt == "welcome_text_channel":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if ch and isinstance(ch, discord.TextChannel):
                gcfg["welcomeTextChannel"] = str(ch.id)
                success = True
            else:
                response_msg = "❌ Veuillez mentionner un salon de texte valide."

        elif opt == "welcome_text":
            gcfg["welcomeText"] = msg.content
            success = True

        elif opt == "welcome_embed":
            parts = msg.content.split("|")
            if len(parts) == 3:
                title, desc, color_hex = [p.strip() for p in parts]
                try:
                    # Tente de convertir la couleur hexadécimale
                    int(color_hex.replace("#", "0x"), 16)
                    gcfg["welcomeEmbed"] = {"title": title, "description": desc, "color": color_hex}
                    success = True
                except ValueError:
                    response_msg = "❌ Format de couleur invalide. Utilisez un code hexadécimal (#RRGGBB)."
            else:
                response_msg = "❌ Format invalide. Utilisez: `Titre | Description | #couleur_hex`"

        elif opt == "leave_channel":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if ch and isinstance(ch, discord.TextChannel):
                gcfg["leaveChannel"] = str(ch.id)
                success = True
            else:
                response_msg = "❌ Veuillez mentionner un salon de texte valide."

        elif opt == "ticket_category":
            cat = msg.channel_mentions[0] if msg.channel_mentions and isinstance(msg.channel_mentions[0], discord.CategoryChannel) else None
            if not cat:
                # Tente de chercher par ID si c'est un ID de catégorie
                try:
                    cat = ctx.guild.get_channel(int(msg.content))
                    if not isinstance(cat, discord.CategoryChannel): cat = None
                except: pass
            
            if cat:
                gcfg["ticketCategory"] = str(cat.id)
                success = True
            else:
                response_msg = "❌ Veuillez mentionner une catégorie valide (ex: #catégorie)."

        elif opt == "log_channel":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if ch and isinstance(ch, discord.TextChannel):
                gcfg["logChannel"] = str(ch.id)
                success = True
            else:
                response_msg = "❌ Veuillez mentionner un salon de texte valide."

        elif opt == "join_role":
            role = msg.role_mentions[0] if msg.role_mentions else None
            if not role:
                # Tente de chercher par ID
                try:
                    role = ctx.guild.get_role(int(msg.content))
                except: pass
            
            if role:
                gcfg["joinRole"] = str(role.id)
                success = True
            else:
                response_msg = "❌ Veuillez mentionner un rôle valide (ex: @Membre)."
        
        # Enregistrer la configuration si réussie
        if success:
            save_config(config)
            
        await ctx.followup.send(response_msg, ephemeral=True)
        # ⚠️ Fin du bloc de code tronqué
    
    select.callback = select_callback
    view.add_item(select)
    await ctx.reply(embed=embed, view=view)


# ==============================================================================
# ⚠️ AJOUT ESSENTIEL : Bloc d'exécution principal
# Ceci est nécessaire pour démarrer le bot. Remplacez 'VOTRE_TOKEN' par le token réel de votre bot.
# ==============================================================================
if __name__ == '__main__':
    # Simulez ici le chargement de la configuration avant de démarrer
    print("Tentative de démarrage du bot...")
    try:
        # Remplacez 'VOTRE_TOKEN_ICI' par le token de votre bot.
        bot.run('VOTRE_TOKEN_ICI')
    except discord.errors.LoginFailure:
        print("ERREUR: Le token du bot est invalide. Veuillez le vérifier.")
    except Exception as e:
        print(f"Une erreur inattendue s'est produite lors du démarrage: {e}")
