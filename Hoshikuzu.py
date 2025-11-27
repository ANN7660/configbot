
# Hoshikuzu.py - Cleaned and corrected bot (Disnake) with 2-page !config and full !help
import os
import asyncio
import random
from datetime import datetime
from collections import defaultdict
from threading import Thread

import disnake as discord
from disnake.ext import commands, tasks
from disnake.ui import Button, View, Select

from flask import Flask

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# In-memory data (consider persisting to JSON in future)
economy_data = defaultdict(lambda: {"money":0, "bank":0, "rep":0, "daily_claimed":None, "work_claimed":None, "inventory":[]})
warnings_data = defaultdict(list)
tickets_data = defaultdict(list)
stats_data = defaultdict(lambda: {"messages":0, "voice_time":0, "last_message":None})
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

# Keep-alive Flask app
app = Flask("")
@app.route("/")
def home():
    return "Bot is running!"
def _run_web():
    app.run(host="0.0.0.0", port=8080)
def keep_alive():
    t = Thread(target=_run_web, daemon=True)
    t.start()

# Helpers
async def log_action(guild: discord.Guild, log_type: str, text: str):
    cfg = server_config[guild.id]
    ch_id = cfg.get("log_channels", {}).get(log_type)
    if not ch_id:
        return
    ch = bot.get_channel(ch_id)
    if ch:
        embed = discord.Embed(description=text, color=discord.Color.blue(), timestamp=datetime.utcnow())
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

def parse_duration(s: str):
    try:
        mapping = {"s":1, "m":60, "h":3600, "d":86400}
        amount = int(s[:-1])
        unit = s[-1]
        return amount * mapping[unit]
    except Exception:
        return None

# Background tasks
@bot.event
async def on_ready():
    print(f"✅ {bot.user} connected")
    auto_reboot.start()
    check_giveaways.start()
    try:
        await bot.change_presence(activity=discord.Game(name="!help"))
    except Exception:
        pass

@tasks.loop(hours=23)
async def auto_reboot():
    print("🔄 Auto-reboot check...")

@tasks.loop(seconds=30)
async def check_giveaways():
    now = datetime.utcnow()
    for gw in giveaways_data[:]:
        try:
            if now >= gw.get("end_time"):
                ch = bot.get_channel(gw["channel_id"])
                if ch:
                    try:
                        msg = await ch.fetch_message(gw["message_id"])
                        reaction = discord.utils.get(msg.reactions, emoji="🎉")
                        users = [u async for u in reaction.users()] if reaction else []
                        users = [u for u in users if not u.bot]
                        if users:
                            winner = random.choice(users)
                            await ch.send(f"🎉 Félicitations {winner.mention}! Vous avez gagné **{gw['prize']}**!")
                        else:
                            await ch.send("❌ Aucun participant au giveaway!")
                    except Exception:
                        pass
                try:
                    giveaways_data.remove(gw)
                except ValueError:
                    pass
        except Exception:
            continue

# Events: member join/leave/messages/voice
@bot.event
async def on_member_join(member):
    cfg = server_config[member.guild.id]
    # autorole
    if cfg.get("autorole"):
        role = member.guild.get_role(cfg["autorole"])
        if role:
            try:
                await member.add_roles(role)
            except Exception:
                pass
    # welcome
    ch_id = cfg.get("welcome_channel")
    if ch_id:
        ch = bot.get_channel(ch_id)
        if ch:
            replacements = {"{user}": member.mention, "{server}": member.guild.name, "{count}": str(member.guild.member_count)}
            if cfg.get("welcome_embed"):
                ed = cfg["welcome_embed"]
                title = ed.get("title","Bienvenue!")
                desc = ed.get("description","")
                for k,v in replacements.items():
                    title = title.replace(k,v); desc = desc.replace(k,v)
                try:
                    color_name = ed.get("color","green")
                    color = getattr(discord.Color, color_name)()
                except Exception:
                    color = discord.Color.green()
                embed = discord.Embed(title=title, description=desc, color=color)
                if ed.get("thumbnail") == "member":
                    embed.set_thumbnail(url=member.display_avatar.url)
                elif ed.get("thumbnail") == "server" and member.guild.icon:
                    embed.set_thumbnail(url=member.guild.icon.url)
                elif ed.get("thumbnail"):
                    embed.set_thumbnail(url=ed.get("thumbnail"))
                if ed.get("image"):
                    embed.set_image(url=ed.get("image"))
                if ed.get("footer"):
                    ft = ed.get("footer")
                    for k,v in replacements.items():
                        ft = ft.replace(k,v)
                    embed.set_footer(text=ft)
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass
            elif cfg.get("welcome_text"):
                msg = cfg["welcome_text"]
                for k,v in replacements.items():
                    msg = msg.replace(k,v)
                try:
                    await ch.send(msg)
                except Exception:
                    pass
    await log_action(member.guild, "membres", f"📥 {member.mention} a rejoint le serveur")

@bot.event
async def on_member_remove(member):
    cfg = server_config[member.guild.id]
    ch_id = cfg.get("leave_channel")
    if ch_id:
        ch = bot.get_channel(ch_id)
        if ch:
            replacements = {"{user}": member.name, "{server}": member.guild.name, "{count}": str(member.guild.member_count)}
            if cfg.get("leave_embed"):
                ed = cfg["leave_embed"]
                title = ed.get("title","Au revoir!")
                desc = ed.get("description","")
                for k,v in replacements.items():
                    title = title.replace(k,v); desc = desc.replace(k,v)
                try:
                    color_name = ed.get("color","red")
                    color = getattr(discord.Color, color_name)()
                except Exception:
                    color = discord.Color.red()
                embed = discord.Embed(title=title, description=desc, color=color)
                if ed.get("thumbnail") == "member":
                    embed.set_thumbnail(url=member.display_avatar.url)
                elif ed.get("thumbnail") == "server" and member.guild.icon:
                    embed.set_thumbnail(url=member.guild.icon.url)
                elif ed.get("thumbnail"):
                    embed.set_thumbnail(url=ed.get("thumbnail"))
                if ed.get("image"):
                    embed.set_image(url=ed.get("image"))
                if ed.get("footer"):
                    ft = ed.get("footer")
                    for k,v in replacements.items():
                        ft = ft.replace(k,v)
                    embed.set_footer(text=ft)
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass
            elif cfg.get("leave_text"):
                msg = cfg["leave_text"]
                for k,v in replacements.items():
                    msg = msg.replace(k,v)
                try:
                    await ch.send(msg)
                except Exception:
                    pass
    await log_action(member.guild, "membres", f"📤 {member.name} a quitté le serveur")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if not message.guild:
        return
    cfg = server_config[message.guild.id]
    user_key = f"{message.guild.id}_{message.author.id}"
    stats_data[user_key]["messages"] += 1
    stats_data[user_key]["last_message"] = datetime.utcnow()
    # antispam
    antispam = cfg.get("antispam", {})
    if antispam.get("enabled"):
        recent = []
        try:
            async for m in message.channel.history(limit=antispam.get("messages",5)):
                if m.author == message.author and (datetime.utcnow() - m.created_at).total_seconds() < antispam.get("seconds",5):
                    recent.append(m)
        except Exception:
            recent = []
        if len(recent) >= antispam.get("messages",5):
            try:
                await message.channel.purge(limit=antispam.get("messages",5), check=lambda m: m.author == message.author)
                await message.channel.send(f"{message.author.mention}, stop le spam!", delete_after=5)
            except Exception:
                pass
            return
    # automod words
    for w in cfg.get("automod_words", []):
        if w and w.lower() in message.content.lower():
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.channel.send(f"{message.author.mention}, ce mot est interdit!", delete_after=5)
            except Exception:
                pass
            await log_action(message.guild, "modération", f"🚫 Message supprimé de {message.author.mention}: mot interdit")
            return
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    cfg = server_config[member.guild.id]
    # temp voice channel creation
    try:
        tempvoc = cfg.get("tempvoc_channel")
        if after.channel and tempvoc and after.channel.id == tempvoc:
            category = member.guild.get_channel(cfg.get("tempvoc_category")) if cfg.get("tempvoc_category") else None
            temp_ch = await member.guild.create_voice_channel(name=f"Vocal de {member.name}", category=category, user_limit=10)
            await member.move_to(temp_ch)
            await asyncio.sleep(2)
            while True:
                await asyncio.sleep(5)
                if len(temp_ch.members) == 0:
                    try:
                        await temp_ch.delete()
                    except Exception:
                        pass
                    break
    except Exception:
        pass
    # voice time tracking
    user_key = f"{member.guild.id}_{member.id}"
    if before.channel is None and after.channel:
        voice_tracking[user_key] = datetime.utcnow()
    elif before.channel and after.channel is None:
        if user_key in voice_tracking:
            secs = (datetime.utcnow() - voice_tracking[user_key]).total_seconds()
            stats_data[user_key]["voice_time"] += secs
            del voice_tracking[user_key]

# Commands: help and config (two pages with prev/next)
@bot.command()
async def help(ctx):
    # ==== EMBED PRINCIPAL ====
    embed = discord.Embed(
        title="🛠️ Menu d’aide",
        description="Sélectionne une catégorie ci-dessous pour afficher les commandes.",
        color=discord.Color.blue()
    )
    embed.add_field(name="Préfix :", value="`!`", inline=False)

    # ==== DICTIONNAIRE DES CATÉGORIES ====
    categories = {
        "moderation": (
            "🛡️ Modération",
            [
                ("!kick <@membre> [raison]", "Expulse un membre."),
                ("!ban <@membre> [raison]", "Bannit un membre."),
                ("!unban <ID>", "Débannit un utilisateur."),
                ("!mute <@membre> <durée>", "Mute temporairement."),
                ("!unmute <@membre>", "Retire le mute."),
                ("!clear <nombre>", "Supprime des messages."),
                ("!lock / !unlock", "Verrouille le salon."),
                ("!warn <@membre>", "Avertir un membre."),
                ("!warnings [membre]", "Voir les avertissements.")
            ]
        ),
        "economy": (
            "💰 Économie",
            [
                ("!daily", "Récompense journalière."),
                ("!balance", "Voir ton argent."),
                ("!rep <membre>", "Donner de la réputation."),
                ("!work", "Gagner de l’argent."),
                ("!beg", "Mendier."),
                ("!pay <membre> <montant>", "Payer quelqu’un."),
                ("!rob <membre>", "Tenter de voler.")
            ]
        ),
        "fun": (
            "🎮 Fun",
            [
                ("!8ball <question>", "Pose une question."),
                ("!joke", "Raconte une blague."),
                ("!coinflip", "Pile ou face."),
                ("!dice", "Lancer un dé."),
                ("!rps <pierre/papier/ciseaux>", "Jeu du chifoumi.")
            ]
        ),
        "utility": (
            "🔧 Utilitaires",
            [
                ("!userinfo [membre]", "Voir les infos d’un utilisateur."),
                ("!serverinfo", "Infos serveur."),
                ("!avatar [membre]", "Voir un avatar."),
                ("!poll <question> | <opt1> | <opt2>", "Créer un sondage."),
                ("!remind <durée> <texte>", "Créer un rappel."),
                ("!stats", "Voir tes stats."),
                ("!leaderboard", "Classement.")
            ]
        ),
        "welcome": (
            "👋 Bienvenue / Départ",
            [
                ("!bvntext <message>", "Configurer le message de bienvenue."),
                ("!bvnembed", "Configurer l’embed de bienvenue."),
                ("!leavetext <message>", "Configurer le message de départ."),
                ("!leaveembed", "Configurer l’embed de départ."),
                ("!setwelcome <#salon>", "Définir le salon de bienvenue."),
                ("!setleave <#salon>", "Définir le salon de départ.")
            ]
        ),
        "systems": (
            "⚙️ Systèmes & Config",
            [
                ("!config", "Configurer le bot."),
                ("!ticketsetup", "Configurer les tickets."),
                ("!tempvoc <salon>", "Vocaux temporaires."),
                ("!giveaway <durée> <prix>", "Créer un giveaway."),
                ("!setlog <type> <#salon>", "Configurer les logs."),
                ("!autorole <@role>", "Rôle automatique."),
                ("!antispam <on/off>", "Activer l’antispam.")
            ]
        )
    }

    # ==== MENU DÉROULANT ====
    select = Select(
        placeholder="Choisis une catégorie",
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
        value = select.values[0]
        title, cmds = categories[value]

        new_embed = discord.Embed(
            title=title,
            description="Voici les commandes disponibles :",
            color=discord.Color.blue()
        )

        for cmd, desc in cmds:
            new_embed.add_field(name=cmd, value=desc, inline=False)

        await interaction.response.edit_message(embed=new_embed, view=view)

    select.callback = select_callback

    view = View(timeout=180)
    view.add_item(select)

    await ctx.send(embed=embed, view=view)

# Config command: 2 pages navigation with Prev / Next buttons
@bot.command()
@commands.has_permissions(administrator=True)
async def config(ctx):
    cfg = server_config[ctx.guild.id]

    # Page 1 embed (selects)
    embed1 = discord.Embed(title="⚙️ Configuration — Page 1/2", description="Sélectionne les salons / rôles", color=discord.Color.blue())
    welcome_ch = bot.get_channel(cfg["welcome_channel"]) if cfg["welcome_channel"] else None
    leave_ch = bot.get_channel(cfg["leave_channel"]) if cfg["leave_channel"] else None
    log_ch = bot.get_channel(cfg["log_channels"].get("modération")) if cfg["log_channels"].get("modération") else None
    autorole = ctx.guild.get_role(cfg["autorole"]) if cfg["autorole"] else None
    stat_text = (
        f"👋 Salon bienvenue: {welcome_ch.mention if welcome_ch else '`Non défini`'}\n"
        f"🚪 Salon départ: {leave_ch.mention if leave_ch else '`Non défini`'}\n"
        f"📜 Salon logs: {log_ch.mention if log_ch else '`Non défini`'}\n"
        f"👤 Rôle automatique: {autorole.mention if autorole else '`Non défini`'}\n"
        f"📝 Questionnaire: {'✅' if cfg['questionnaire_active'] else '❌'}"
    )
    embed1.add_field(name="Configuration actuelle", value=stat_text, inline=False)

    # selects (rows 0..3)
    select_welcome = Select(placeholder="👋 Choisir le salon de bienvenue",
                            options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="👋") for ch in ctx.guild.text_channels[:25]],
                            row=0)
    select_leave = Select(placeholder="🚪 Choisir le salon de départ",
                          options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="🚪") for ch in ctx.guild.text_channels[:25]],
                          row=1)
    select_logs = Select(placeholder="📜 Choisir le salon de logs",
                         options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="📜") for ch in ctx.guild.text_channels[:25]],
                         row=2)
    select_autorole = Select(placeholder="👤 Choisir le rôle automatique",
                             options=[discord.SelectOption(label=role.name, value=str(role.id), emoji="👤") for role in ctx.guild.roles[1:26]],
                             row=3)

    async def sel_welcome_cb(interaction):
        try:
            server_config[ctx.guild.id]["welcome_channel"] = int(select_welcome.values[0])
            await interaction.response.send_message("✅ Salon de bienvenue configuré!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    async def sel_leave_cb(interaction):
        try:
            server_config[ctx.guild.id]["leave_channel"] = int(select_leave.values[0])
            await interaction.response.send_message("✅ Salon de départ configuré!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    async def sel_logs_cb(interaction):
        try:
            server_config[ctx.guild.id]["log_channels"]["modération"] = int(select_logs.values[0])
            await interaction.response.send_message("✅ Salon de logs configuré!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    async def sel_autorole_cb(interaction):
        try:
            server_config[ctx.guild.id]["autorole"] = int(select_autorole.values[0])
            await interaction.response.send_message("✅ Rôle automatique configuré!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    select_welcome.callback = sel_welcome_cb
    select_leave.callback = sel_leave_cb
    select_logs.callback = sel_logs_cb
    select_autorole.callback = sel_autorole_cb

    # Page 1 view includes selects and a Next button
    view1 = View(timeout=300)
    view1.add_item(select_welcome)
    view1.add_item(select_leave)
    view1.add_item(select_logs)
    view1.add_item(select_autorole)

    btn_next = Button(label="▶ Page suivante", style=discord.ButtonStyle.primary, row=4)
    async def next_cb(interaction):
        # Build page 2 and edit message
        await show_page2(interaction, ctx.guild.id)
    btn_next.callback = next_cb
    view1.add_item(btn_next)

    # send initial page
    await ctx.send(embed=embed1, view=view1)

async def show_page2(interaction: discord.Interaction, guild_id: int):
    ctx_guild = bot.get_guild(guild_id)
    cfg = server_config[guild_id]
    embed2 = discord.Embed(title="⚙️ Configuration — Page 2/2", description="Réglages Bienvenue/Départ & sauvegarde", color=discord.Color.blue())
    embed2.add_field(name="Actions disponibles", value="📝 Config messages de bienvenue/départ\n💾 Sauvegarder (en mémoire)\n📝 Questionnaire ON/OFF", inline=False)

    # Buttons for page 2 (placed on rows 0 and 1)
    btn_bvn_text = Button(label="📝 Message Bienvenue", style=discord.ButtonStyle.primary, row=0)
    btn_bvn_embed = Button(label="🎨 Embed Bienvenue", style=discord.ButtonStyle.primary, row=0)
    btn_leave_text = Button(label="📝 Message Départ", style=discord.ButtonStyle.secondary, row=0)

    btn_leave_embed = Button(label="🎨 Embed Départ", style=discord.ButtonStyle.secondary, row=1)
    btn_questionnaire = Button(label="📝 Questionnaire", style=discord.ButtonStyle.secondary, row=1)
    btn_save = Button(label="💾 Sauvegarder", style=discord.ButtonStyle.success, row=1)

    async def bvn_text_cb(i: discord.Interaction):
        await i.response.send_message("📝 Utilise `!bvntext <message>` (variables {user},{server},{count}, utilise \\n pour sauts de ligne).", ephemeral=True)
    async def bvn_embed_cb(i: discord.Interaction):
        await i.response.send_message("🎨 Utilise `!bvnembed` (wizard non-implémenté).", ephemeral=True)
    async def leave_text_cb(i: discord.Interaction):
        await i.response.send_message("📝 Utilise `!leavetext <message>` (variables {user},{server},{count}).", ephemeral=True)
    async def leave_embed_cb(i: discord.Interaction):
        await i.response.send_message("🎨 Utilise `!leaveembed` (wizard non-implémenté).", ephemeral=True)
    async def questionnaire_cb(i: discord.Interaction):
        cfg_local = server_config[guild_id]
        cfg_local["questionnaire_active"] = not cfg_local["questionnaire_active"]
        status = "✅ Activé" if cfg_local["questionnaire_active"] else "❌ Désactivé"
        await i.response.send_message(f"📝 Questionnaire: {status}", ephemeral=True)
    async def save_cb(i: discord.Interaction):
        await i.response.send_message("✅ Configuration sauvegardée en mémoire (non persistée).", ephemeral=True)

    btn_bvn_text.callback = bvn_text_cb
    btn_bvn_embed.callback = bvn_embed_cb
    btn_leave_text.callback = leave_text_cb
    btn_leave_embed.callback = leave_embed_cb
    btn_questionnaire.callback = questionnaire_cb
    btn_save.callback = save_cb

    # Navigation back button
    btn_back = Button(label="◀ Page précédente", style=discord.ButtonStyle.secondary, row=4)
    async def back_cb(i: discord.Interaction):
        # Rebuild page1 embed and view and edit original message
        guild = bot.get_guild(guild_id)
        cfg_local = server_config[guild_id]
        embed1 = discord.Embed(title="⚙️ Configuration — Page 1/2", description="Sélectionne les salons / rôles", color=discord.Color.blue())
        welcome_ch = bot.get_channel(cfg_local["welcome_channel"]) if cfg_local["welcome_channel"] else None
        leave_ch = bot.get_channel(cfg_local["leave_channel"]) if cfg_local["leave_channel"] else None
        log_ch = bot.get_channel(cfg_local["log_channels"].get("modération")) if cfg_local["log_channels"].get("modération") else None
        autorole = guild.get_role(cfg_local["autorole"]) if cfg_local["autorole"] else None
        stat_text = (
            f"👋 Salon bienvenue: {welcome_ch.mention if welcome_ch else '`Non défini`'}\n"
            f"🚪 Salon départ: {leave_ch.mention if leave_ch else '`Non défini`'}\n"
            f"📜 Salon logs: {log_ch.mention if log_ch else '`Non défini`'}\n"
            f"👤 Rôle automatique: {autorole.mention if autorole else '`Non défini`'}\n"
            f"📝 Questionnaire: {'✅' if cfg_local['questionnaire_active'] else '❌'}"
        )
        embed1.add_field(name="Configuration actuelle", value=stat_text, inline=False)

        # Recreate selects
        select_welcome = Select(placeholder="👋 Choisir le salon de bienvenue",
                                options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="👋") for ch in guild.text_channels[:25]],
                                row=0)
        select_leave = Select(placeholder="🚪 Choisir le salon de départ",
                              options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="🚪") for ch in guild.text_channels[:25]],
                              row=1)
        select_logs = Select(placeholder="📜 Choisir le salon de logs",
                             options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="📜") for ch in guild.text_channels[:25]],
                             row=2)
        select_autorole = Select(placeholder="👤 Choisir le rôle automatique",
                                 options=[discord.SelectOption(label=role.name, value=str(role.id), emoji="👤") for role in guild.roles[1:26]],
                                 row=3)

        async def sel_welcome_cb2(inter):
            try:
                server_config[guild_id]["welcome_channel"] = int(select_welcome.values[0])
                await inter.response.send_message("✅ Salon de bienvenue configuré!", ephemeral=True)
            except Exception as e:
                await inter.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
        async def sel_leave_cb2(inter):
            try:
                server_config[guild_id]["leave_channel"] = int(select_leave.values[0])
                await inter.response.send_message("✅ Salon de départ configuré!", ephemeral=True)
            except Exception as e:
                await inter.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
        async def sel_logs_cb2(inter):
            try:
                server_config[guild_id]["log_channels"]["modération"] = int(select_logs.values[0])
                await inter.response.send_message("✅ Salon de logs configuré!", ephemeral=True)
            except Exception as e:
                await inter.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
        async def sel_autorole_cb2(inter):
            try:
                server_config[guild_id]["autorole"] = int(select_autorole.values[0])
                await inter.response.send_message("✅ Rôle automatique configuré!", ephemeral=True)
            except Exception as e:
                await inter.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
        select_welcome.callback = sel_welcome_cb2
        select_leave.callback = sel_leave_cb2
        select_logs.callback = sel_logs_cb2
        select_autorole.callback = sel_autorole_cb2

        view1 = View(timeout=300)
        view1.add_item(select_welcome)
        view1.add_item(select_leave)
        view1.add_item(select_logs)
        view1.add_item(select_autorole)
        btn_next = Button(label="▶ Page suivante", style=discord.ButtonStyle.primary, row=4)
        async def next_cb2(inter2):
            await show_page2(inter2, guild_id)
        btn_next.callback = next_cb2
        view1.add_item(btn_next)
        try:
            await i.response.edit_message(embed=embed1, view=view1)
        except Exception:
            try:
                await i.response.send_message("❌ Impossible d'afficher la page 1.", ephemeral=True)
            except Exception:
                pass

    btn_back.callback = back_cb

    view2 = View(timeout=300)
    view2.add_item(btn_bvn_text)
    view2.add_item(btn_bvn_embed)
    view2.add_item(btn_leave_text)
    view2.add_item(btn_leave_embed)
    view2.add_item(btn_questionnaire)
    view2.add_item(btn_save)
    view2.add_item(btn_back)

    try:
        # if interaction came from a message, edit it; otherwise respond
        try:
            await interaction.response.edit_message(embed=embed2, view=view2)
        except Exception:
            await interaction.response.send_message(embed=embed2, view=view2, ephemeral=False)
    except Exception:
        try:
            await interaction.followup.send("❌ Impossible d'afficher la page 2.", ephemeral=True)
        except Exception:
            pass

# Moderation commands (kick, ban, unban, mute, unmute, clear, lock, unlock, warn, warnings)
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str="Aucune raison"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"✅ {member.mention} expulsé. Raison: {reason}")
        await log_action(ctx.guild, "modération", f"👢 {member.mention} expulsé par {ctx.author.mention} - {reason}")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str="Aucune raison"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"✅ {member.mention} banni. Raison: {reason}")
        await log_action(ctx.guild, "modération", f"🔨 {member.mention} banni par {ctx.author.mention} - {reason}")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ {user.mention} débanni.")
        await log_action(ctx.guild, "modération", f"✅ {user.mention} débanni par {ctx.author.mention}")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: str, *, reason: str="Aucune raison"):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role:
        try:
            mute_role = await ctx.guild.create_role(name="Muted", reason="Rôle mute")
            for ch in ctx.guild.channels:
                try:
                    await ch.set_permissions(mute_role, speak=False, send_messages=False)
                except Exception:
                    pass
        except Exception as e:
            await ctx.send(f"❌ Erreur création rôle: {e}")
            return
    try:
        await member.add_roles(mute_role, reason=reason)
        await ctx.send(f"🔇 {member.mention} mute pour {duration}.")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")
        return
    secs = parse_duration(duration)
    if secs is None:
        await ctx.send("❌ Durée invalide. Ex: 10s, 5m, 1h, 1d")
        return
    await asyncio.sleep(secs)
    try:
        await member.remove_roles(mute_role)
        await ctx.send(f"🔊 {member.mention} unmute automatiquement.")
    except Exception:
        pass

@bot.command()
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if mute_role in member.roles:
        try:
            await member.remove_roles(mute_role)
            await ctx.send(f"🔊 {member.mention} unmute.")
        except Exception as e:
            await ctx.send(f"❌ Erreur: {e}")
    else:
        await ctx.send(f"❌ {member.mention} n'est pas mute.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount < 1 or amount > 100:
        await ctx.send("❌ Montant invalide (1-100).")
        return
    try:
        await ctx.channel.purge(limit=amount+1)
        m = await ctx.send(f"✅ {amount} messages supprimés.")
        await asyncio.sleep(3)
        await m.delete()
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send("🔒 Salon verrouillé.")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.send("🔓 Salon déverrouillé.")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")

@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member, *, reason: str="Aucune raison"):
    warnings_data[member.id].append({"reason": reason, "moderator": ctx.author.id, "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M")})
    count = len(warnings_data[member.id])
    await ctx.send(f"⚠️ {member.mention} averti ({count}). Raison: {reason}")
    if count == 3:
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if mute_role:
            await member.add_roles(mute_role)
            await ctx.send(f"🔇 {member.mention} mute (3 warns).")
    elif count == 5:
        await member.kick(reason="5 warns")
        await ctx.send(f"👢 {member.mention} kick (5 warns).")

@bot.command()
async def warnings(ctx, member: discord.Member=None):
    member = member or ctx.author
    warns = warnings_data.get(member.id, [])
    if not warns:
        await ctx.send(f"✅ {member.mention} n'a aucun avertissement.")
        return
    embed = discord.Embed(title=f"Avertissements de {member.name}", color=discord.Color.orange())
    for i,w in enumerate(warns,1):
        mod = ctx.guild.get_member(w["moderator"])
        mod_name = mod.name if mod else "Inconnu"
        embed.add_field(name=f"Warn #{i}", value=f"**Raison:** {w['reason']}\n**Par:** {mod_name}\n**Date:** {w['time']}", inline=False)
    await ctx.send(embed=embed)

# Welcome/leave text commands
@bot.command()
@commands.has_permissions(administrator=True)
async def bvntext(ctx, *, message: str):
    message = message.replace("\\n", "\n")
    server_config[ctx.guild.id]["welcome_text"] = message
    server_config[ctx.guild.id]["welcome_embed"] = None
    preview = message.replace("{user}", ctx.author.mention).replace("{server}", ctx.guild.name).replace("{count}", str(ctx.guild.member_count))
    await ctx.send(f"✅ Message de bienvenue configuré!\n\nAperçu:\n{preview}")

@bot.command()
@commands.has_permissions(administrator=True)
async def leavetext(ctx, *, message: str):
    message = message.replace("\\n", "\n")
    server_config[ctx.guild.id]["leave_text"] = message
    server_config[ctx.guild.id]["leave_embed"] = None
    preview = message.replace("{user}", ctx.author.name).replace("{server}", ctx.guild.name).replace("{count}", str(ctx.guild.member_count))
    await ctx.send(f"✅ Message de départ configuré!\n\nAperçu:\n{preview}")

# Startup
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ ERREUR: DISCORD_TOKEN manquant")
        raise SystemExit(1)
    try:
        print("🚀 Démarrage du bot...")
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Token invalide")
    except Exception as e:
        print("❌ Erreur:", e)


# -------------------------
# Interactive Embed Editor
# Multi-page editor for !bvnembed and !leaveembed (uses Modals + Buttons + Selects)
# -------------------------
from disnake.ui import Modal, TextInput
from typing import Dict, Any, Tuple

# Temporary in-memory editor states: {(guild_id, user_id, mode): state_dict}
embed_editors: Dict[Tuple[int,int,str], Dict[str, Any]] = {}

def _default_editor_state(mode: str):
    # mode is 'welcome' or 'leave'
    return {
        "mode": mode,
        "title": "Bienvenue!" if mode=="welcome" else "Au revoir!",
        "description": "",
        "color": "blue",
        "thumbnail": "member",  # 'member' | 'server' | url | None
        "image": None,
        "footer": "",
    }

def build_preview_embed(state: Dict[str, Any], guild: discord.Guild, sample_user: discord.Member):
    title = state.get("title") or ""
    desc = state.get("description") or ""
    color_name = state.get("color", "blue")
    try:
        color = getattr(discord.Color, color_name)()
    except Exception:
        color = discord.Color.blue()
    embed = discord.Embed(title=title, description=desc, color=color)
    thumb = state.get("thumbnail")
    if thumb == "member" and sample_user:
        embed.set_thumbnail(url=sample_user.display_avatar.url)
    elif thumb == "server" and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    elif thumb:
        embed.set_thumbnail(url=thumb)
    if state.get("image"):
        embed.set_image(url=state.get("image"))
    if state.get("footer"):
        embed.set_footer(text=state.get("footer"))
    return embed

# Generic Modal to edit a single text field
class SingleFieldModal(Modal):
    def __init__(self, title:str, field_name:str, placeholder:str, max_length:int, state_key:str, editor_key: Tuple[int,int,str]):
        self.field_name = field_name
        self.state_key = state_key
        self.editor_key = editor_key
        components = [TextInput(label=field_name, placeholder=placeholder, style=TextInput.paragraph if max_length>100 else TextInput.short, min_length=0, max_length=max_length, custom_id=state_key)]
        super().__init__(title=title, components=components)

    async def callback(self, interaction: discord.Interaction):
        guild_id, user_id, mode = self.editor_key
        key = (guild_id, user_id, mode)
        state = embed_editors.get(key)
        if not state:
            await interaction.response.send_message("Éditeur introuvable (expiré). Relance la commande.", ephemeral=True)
            return
        value = self.children[0].value
        state[self.state_key] = value
        # update preview message if exist
        msg = state.get("message")
        guild = bot.get_guild(guild_id)
        user = guild.get_member(user_id) if guild else None
        preview = build_preview_embed(state, guild, user)
        view = build_editor_view(guild_id, user_id, mode)
        try:
            await msg.edit(embed=preview, view=view)
            await interaction.response.send_message("✅ Modifié.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("✅ Modifié (aperçu non mis à jour).", ephemeral=True)

# Helpers to build views per page
def build_editor_view(guild_id:int, user_id:int, mode:str, page:int=1):
    key = (guild_id, user_id, mode)
    state = embed_editors.get(key, _default_editor_state(mode))
    view = View(timeout=600)
    # Page navigation handled by callbacks; add buttons according to page
    # Common action buttons (page-specific)
    if page == 1:
        # Text settings
        btn_title = Button(label="Titre", style=discord.ButtonStyle.primary)
        btn_desc = Button(label="Description", style=discord.ButtonStyle.primary)
        async def title_cb(i: discord.Interaction):
            modal = SingleFieldModal(title="Modifier le titre", field_name="Titre", placeholder="Titre de l'embed", max_length=256, state_key="title", editor_key=key)
            await i.response.send_modal(modal)
        async def desc_cb(i: discord.Interaction):
            modal = SingleFieldModal(title="Modifier la description", field_name="Description", placeholder="Texte de description (utilise \\n pour saut)", max_length=2000, state_key="description", editor_key=key)
            await i.response.send_modal(modal)
        btn_title.callback = title_cb
        btn_desc.callback = desc_cb
        view.add_item(btn_title)
        view.add_item(btn_desc)
        # Next button
        btn_next = Button(label="▶ Page suivante", style=discord.ButtonStyle.secondary)
        async def next_cb(i: discord.Interaction):
            await show_editor_page(i, guild_id, user_id, mode, 2)
        btn_next.callback = next_cb
        view.add_item(btn_next)
    elif page == 2:
        # Visual settings
        # Color select
        color_select = Select(
            placeholder="Couleur",
            options=[
                discord.SelectOption(label="Bleu", value="blue"),
                discord.SelectOption(label="Vert", value="green"),
                discord.SelectOption(label="Rouge", value="red"),
                discord.SelectOption(label="Or", value="gold"),
                discord.SelectOption(label="Gris", value="greyple"),
                discord.SelectOption(label="Noir", value="dark"),
                discord.SelectOption(label="Personnalisée (hex)", value="custom")
            ]
        )
        async def color_cb(i: discord.Interaction):
            sel = i.data.get("values", [])[0]
            if sel == "custom":
                modal = SingleFieldModal(title="Couleur hex", field_name="Hex couleur", placeholder="#FF00FF ou FF00FF", max_length=7, state_key="color", editor_key=key)
                await i.response.send_modal(modal)
            else:
                state = embed_editors.get(key)
                if state is not None:
                    state["color"] = sel
                # update preview
                msg = state.get("message")
                guild = bot.get_guild(guild_id)
                user = guild.get_member(user_id) if guild else None
                preview = build_preview_embed(state, guild, user)
                view = build_editor_view(guild_id, user_id, mode, page=2)
                try:
                    await msg.edit(embed=preview, view=view)
                    await i.response.send_message("✅ Couleur mise à jour.", ephemeral=True)
                except Exception:
                    await i.response.send_message("✅ Couleur mise à jour.", ephemeral=True)
        color_select.callback = color_cb
        view.add_item(color_select)
        # Thumbnail choice buttons
        btn_thumb_member = Button(label="Thumbnail: Membre", style=discord.ButtonStyle.secondary)
        btn_thumb_server = Button(label="Thumbnail: Serveur", style=discord.ButtonStyle.secondary)
        btn_thumb_url = Button(label="Thumbnail: URL", style=discord.ButtonStyle.secondary)
        async def thumb_member_cb(i: discord.Interaction):
            state = embed_editors.get(key)
            state["thumbnail"] = "member"
            msg = state.get("message"); guild = bot.get_guild(guild_id); user = guild.get_member(user_id) if guild else None
            await msg.edit(embed=build_preview_embed(state, guild, user), view=build_editor_view(guild_id,user_id,mode,2))
            await i.response.send_message("✅ Thumbnail réglé sur membre.", ephemeral=True)
        async def thumb_server_cb(i: discord.Interaction):
            state = embed_editors.get(key)
            state["thumbnail"] = "server"
            msg = state.get("message"); guild = bot.get_guild(guild_id); user = guild.get_member(user_id) if guild else None
            await msg.edit(embed=build_preview_embed(state, guild, user), view=build_editor_view(guild_id,user_id,mode,2))
            await i.response.send_message("✅ Thumbnail réglé sur serveur.", ephemeral=True)
        async def thumb_url_cb(i: discord.Interaction):
            modal = SingleFieldModal(title="Thumbnail URL", field_name="Thumbnail URL", placeholder="https://....", max_length=300, state_key="thumbnail", editor_key=key)
            await i.response.send_modal(modal)
        btn_thumb_member.callback = thumb_member_cb
        btn_thumb_server.callback = thumb_server_cb
        btn_thumb_url.callback = thumb_url_cb
        view.add_item(btn_thumb_member)
        view.add_item(btn_thumb_server)
        view.add_item(btn_thumb_url)
        # Image URL modal
        btn_image = Button(label="Image (URL)", style=discord.ButtonStyle.primary)
        async def image_cb(i: discord.Interaction):
            modal = SingleFieldModal(title="Image URL", field_name="Image URL", placeholder="https://....", max_length=300, state_key="image", editor_key=key)
            await i.response.send_modal(modal)
        btn_image.callback = image_cb
        view.add_item(btn_image)
        # Navigation
        btn_back = Button(label="◀ Page précédente", style=discord.ButtonStyle.secondary)
        btn_next = Button(label="▶ Page suivante", style=discord.ButtonStyle.secondary)
        async def back_cb(i: discord.Interaction):
            await show_editor_page(i, guild_id, user_id, mode, 1)
        async def next_cb(i: discord.Interaction):
            await show_editor_page(i, guild_id, user_id, mode, 3)
        btn_back.callback = back_cb
        btn_next.callback = next_cb
        view.add_item(btn_back)
        view.add_item(btn_next)
    elif page == 3:
        # Footer and save
        btn_footer = Button(label="Footer", style=discord.ButtonStyle.primary)
        btn_preview = Button(label="Aperçu complet", style=discord.ButtonStyle.secondary)
        btn_save = Button(label="💾 Sauvegarder", style=discord.ButtonStyle.success)
        async def footer_cb(i: discord.Interaction):
            modal = SingleFieldModal(title="Footer", field_name="Footer", placeholder="Texte du footer", max_length=2048, state_key="footer", editor_key=key)
            await i.response.send_modal(modal)
        async def preview_cb(i: discord.Interaction):
            state = embed_editors.get(key)
            guild = bot.get_guild(guild_id); user = guild.get_member(user_id) if guild else None
            await i.response.send_message(embed=build_preview_embed(state, guild, user), ephemeral=True)
        async def save_cb(i: discord.Interaction):
            # persist to server_config
            state = embed_editors.get(key)
            if not state:
                await i.response.send_message("Éditeur expiré.", ephemeral=True); return
            mode_local = state.get("mode")
            if mode_local == "welcome":
                server_config[guild_id]["welcome_embed"] = {
                    "title": state.get("title"), "description": state.get("description"),
                    "color": state.get("color"), "thumbnail": state.get("thumbnail"),
                    "image": state.get("image"), "footer": state.get("footer")
                }
                server_config[guild_id]["welcome_text"] = None
            else:
                server_config[guild_id]["leave_embed"] = {
                    "title": state.get("title"), "description": state.get("description"),
                    "color": state.get("color"), "thumbnail": state.get("thumbnail"),
                    "image": state.get("image"), "footer": state.get("footer")
                }
                server_config[guild_id]["leave_text"] = None
            await i.response.send_message("✅ Embed sauvegardé en mémoire.", ephemeral=True)
        btn_footer.callback = footer_cb
        btn_preview.callback = preview_cb
        btn_save.callback = save_cb
        view.add_item(btn_footer)
        view.add_item(btn_preview)
        view.add_item(btn_save)
        btn_back = Button(label="◀ Page précédente", style=discord.ButtonStyle.secondary)
        async def back_cb(i: discord.Interaction):
            await show_editor_page(i, guild_id, user_id, mode, 2)
        btn_back.callback = back_cb
        view.add_item(btn_back)
    return view

async def show_editor_page(interaction: discord.Interaction, guild_id:int, user_id:int, mode:str, page:int):
    key = (guild_id, user_id, mode)
    state = embed_editors.get(key)
    if not state:
        # initialize
        state = _default_editor_state(mode)
        embed_editors[key] = state
    guild = bot.get_guild(guild_id)
    user = guild.get_member(user_id) if guild else None
    preview = build_preview_embed(state, guild, user)
    # create view for page
    view = build_editor_view(guild_id, user_id, mode, page=page)
    state["message"] = state.get("message") or interaction.message
    try:
        await interaction.response.edit_message(embed=preview, view=view)
    except Exception:
        await interaction.response.send_message(embed=preview, view=view, ephemeral=True)

# Commands to open the editor
@bot.command()
@commands.has_permissions(administrator=True)
async def bvnembed(ctx):
    key = (ctx.guild.id, ctx.author.id, "welcome")
    embed_editors[key] = _default_editor_state("welcome")
    guild = ctx.guild
    user = ctx.author
    preview = build_preview_embed(embed_editors[key], guild, user)
    view = build_editor_view(ctx.guild.id, ctx.author.id, "welcome", page=1)
    msg = await ctx.send("🎨 Éditeur d'embed de bienvenue — Utilisateur: " + ctx.author.mention, embed=preview, view=view)
    embed_editors[key]["message"] = msg

@bot.command()
@commands.has_permissions(administrator=True)
async def leaveembed(ctx):
    key = (ctx.guild.id, ctx.author.id, "leave")
    embed_editors[key] = _default_editor_state("leave")
    guild = ctx.guild
    user = ctx.author
    preview = build_preview_embed(embed_editors[key], guild, user)
    view = build_editor_view(ctx.guild.id, ctx.author.id, "leave", page=1)
    msg = await ctx.send("🎨 Éditeur d'embed de départ — Utilisateur: " + ctx.author.mention, embed=preview, view=view)
    embed_editors[key]["message"] = msg
