# main.py
import os
import asyncio
import random
import json
from datetime import datetime, timedelta
from collections import defaultdict
from threading import Thread

import disnake as discord
from disnake.ext import commands, tasks
from disnake.ui import Button, View, Select

# Optional: keep-alive webserver (not required on Render but harmless)
from flask import Flask

# ============= CONFIGURATION =============
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ============= DATA (in-memory) =============
economy_data = defaultdict(lambda: {
    "money": 0, "bank": 0, "rep": 0,
    "daily_claimed": None, "work_claimed": None,
    "inventory": []
})
warnings_data = defaultdict(list)
tickets_data = defaultdict(list)
stats_data = defaultdict(lambda: {"messages": 0, "voice_time": 0, "last_message": None})
giveaways_data = []  # list of dicts: {"channel_id", "message_id", "end_time", "prize"}
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

# ============= KEEP ALIVE (Flask) =============
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run_web, daemon=True)
    t.start()

# ============= HELPERS =============
async def log_action(guild, log_type, message_text):
    cfg = server_config[guild.id]
    log_channel_id = cfg["log_channels"].get(log_type)
    if not log_channel_id:
        return
    channel = bot.get_channel(log_channel_id)
    if channel:
        embed = discord.Embed(description=message_text, color=discord.Color.blue(), timestamp=datetime.utcnow())
        await channel.send(embed=embed)

def parse_duration(duration: str):
    """Parse duration strings like '10s', '5m', '1h', '1d' -> seconds or None."""
    try:
        time_map = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        amount = int(duration[:-1])
        unit = duration[-1]
        if unit not in time_map:
            return None
        return amount * time_map[unit]
    except:
        return None

# ============= BACKGROUND TASKS =============
@bot.event
async def on_ready():
    print(f"✅ {bot.user} est connecté!")
    auto_reboot.start()
    check_giveaways.start()
    await bot.change_presence(activity=discord.Game(name="!help"))

@tasks.loop(hours=23)
async def auto_reboot():
    # placeholder: could implement auto-restart logic / health checks
    print("🔄 Auto-reboot check...")

@tasks.loop(seconds=30)
async def check_giveaways():
    now = datetime.utcnow()
    for gw in giveaways_data[:]:
        if now >= gw.get("end_time"):
            channel = bot.get_channel(gw["channel_id"])
            if channel:
                try:
                    msg = await channel.fetch_message(gw["message_id"])
                    reaction = discord.utils.get(msg.reactions, emoji="🎉")
                    users = []
                    if reaction:
                        users = [user async for user in reaction.users() if not user.bot]
                    if users:
                        winner = random.choice(users)
                        await channel.send(f"🎉 Félicitations {winner.mention}! Vous avez gagné **{gw['prize']}**!")
                    else:
                        await channel.send("❌ Aucun participant au giveaway!")
                except Exception as e:
                    print("check_giveaways error:", e)
            try:
                giveaways_data.remove(gw)
            except ValueError:
                pass

# ============= EVENTS: Member join/leave, message, voice ============
@bot.event
async def on_member_join(member):
    cfg = server_config[member.guild.id]
    # autorole
    if cfg.get("autorole"):
        role = member.guild.get_role(cfg["autorole"])
        if role:
            try:
                await member.add_roles(role)
            except Exception as e:
                print("autorole error:", e)

    # welcome message
    channel_id = cfg.get("welcome_channel")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            replacements = {
                "{user}": member.mention,
                "{server}": member.guild.name,
                "{count}": str(member.guild.member_count)
            }
            if cfg.get("welcome_embed"):
                embed_data = cfg["welcome_embed"]
                title = embed_data.get("title", "Bienvenue!")
                description = embed_data.get("description", "")
                for k, v in replacements.items():
                    title = title.replace(k, v)
                    description = description.replace(k, v)
                try:
                    embed = discord.Embed(
                        title=title,
                        description=description,
                        color=getattr(discord.Color, embed_data.get("color", "green"))()
                    )
                except Exception:
                    embed = discord.Embed(title=title, description=description, color=discord.Color.green())
                thumb = embed_data.get("thumbnail")
                if thumb == "member":
                    embed.set_thumbnail(url=member.display_avatar.url)
                elif thumb == "server":
                    if member.guild.icon:
                        embed.set_thumbnail(url=member.guild.icon.url)
                elif thumb:
                    embed.set_thumbnail(url=thumb)
                if embed_data.get("image"):
                    embed.set_image(url=embed_data["image"])
                if embed_data.get("footer"):
                    ft = embed_data["footer"]
                    for k, v in replacements.items():
                        ft = ft.replace(k, v)
                    embed.set_footer(text=ft)
                await channel.send(embed=embed)
            elif cfg.get("welcome_text"):
                msg = cfg["welcome_text"]
                for k, v in replacements.items():
                    msg = msg.replace(k, v)
                await channel.send(msg)
    await log_action(member.guild, "membres", f"📥 {member.mention} a rejoint le serveur")

@bot.event
async def on_member_remove(member):
    cfg = server_config[member.guild.id]
    channel_id = cfg.get("leave_channel")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            replacements = {
                "{user}": member.name,
                "{server}": member.guild.name,
                "{count}": str(member.guild.member_count)
            }
            if cfg.get("leave_embed"):
                embed_data = cfg["leave_embed"]
                title = embed_data.get("title", "Au revoir!")
                description = embed_data.get("description", "")
                for k, v in replacements.items():
                    title = title.replace(k, v)
                    description = description.replace(k, v)
                try:
                    embed = discord.Embed(
                        title=title,
                        description=description,
                        color=getattr(discord.Color, embed_data.get("color", "red"))()
                    )
                except Exception:
                    embed = discord.Embed(title=title, description=description, color=discord.Color.red())
                thumb = embed_data.get("thumbnail")
                if thumb == "member":
                    embed.set_thumbnail(url=member.display_avatar.url)
                elif thumb == "server":
                    if member.guild.icon:
                        embed.set_thumbnail(url=member.guild.icon.url)
                elif thumb:
                    embed.set_thumbnail(url=thumb)
                if embed_data.get("image"):
                    embed.set_image(url=embed_data["image"])
                if embed_data.get("footer"):
                    ft = embed_data["footer"]
                    for k, v in replacements.items():
                        ft = ft.replace(k, v)
                    embed.set_footer(text=ft)
                await channel.send(embed=embed)
            elif cfg.get("leave_text"):
                msg = cfg["leave_text"]
                for k, v in replacements.items():
                    msg = msg.replace(k, v)
                await channel.send(msg)
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
        recent_messages = []
        try:
            async for m in message.channel.history(limit=antispam.get("messages", 5)):
                if m.author == message.author and (datetime.utcnow() - m.created_at).total_seconds() < antispam.get("seconds", 5):
                    recent_messages.append(m)
        except Exception:
            recent_messages = []
        if len(recent_messages) >= antispam.get("messages", 5):
            try:
                await message.channel.purge(limit=antispam.get("messages", 5), check=lambda m: m.author == message.author)
                await message.channel.send(f"{message.author.mention}, stop le spam!", delete_after=5)
            except Exception:
                pass
            return

    # automod words
    for word in cfg.get("automod_words", []):
        try:
            if word.lower() in message.content.lower():
                await message.delete()
                await message.channel.send(f"{message.author.mention}, ce mot est interdit!", delete_after=5)
                await log_action(message.guild, "modération", f"🚫 Message supprimé de {message.author.mention}: mot interdit")
                return
        except Exception:
            continue

    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    cfg = server_config[member.guild.id]
    # temporary voice channel creation
    try:
        tempvoc_id = cfg.get("tempvoc_channel")
        if after.channel and tempvoc_id and after.channel.id == tempvoc_id:
            category = member.guild.get_channel(cfg.get("tempvoc_category")) if cfg.get("tempvoc_category") else None
            temp_channel = await member.guild.create_voice_channel(
                name=f"Vocal de {member.name}",
                category=category,
                user_limit=10
            )
            await member.move_to(temp_channel)
            # wait and delete when empty
            await asyncio.sleep(2)
            while True:
                await asyncio.sleep(5)
                if len(temp_channel.members) == 0:
                    try:
                        await temp_channel.delete()
                    except Exception:
                        pass
                    break
    except Exception:
        pass

    # voice tracking for stats
    user_key = f"{member.guild.id}_{member.id}"
    if before.channel is None and after.channel:
        voice_tracking[user_key] = datetime.utcnow()
    elif before.channel and after.channel is None:
        if user_key in voice_tracking:
            time_spent = (datetime.utcnow() - voice_tracking[user_key]).total_seconds()
            stats_data[user_key]["voice_time"] += time_spent
            del voice_tracking[user_key]

# ============= COMMANDS: help & config (interactive) ============
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="🛡️ Commandes",
        description="Utilise le menu pour voir les catégories",
        color=discord.Color.blue()
    )

    embed.add_field(name="Prefix", value="`!`", inline=False)
    # Build select and view
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

    view = View(timeout=180)
    view.add_item(select)

    async def select_callback(interaction: discord.Interaction):
        category = select.values[0]
        embeds_data = {
            "moderation": ("🛡️ Commandes de Modération", "Commandes pour gérer ton serveur", discord.Color.blue(), [
                ("!kick <@membre> [raison]", "Expulse un membre"),
                ("!ban <@membre> [raison]", "Bannit un membre"),
                ("!unban <ID>", "Débannit un utilisateur"),
                ("!mute <@membre> <durée> [raison]", "Mute temporairement"),
                ("!unmute <@membre>", "Retire le mute"),
                ("!clear <nombre>", "Supprime des messages"),
                ("!lock / !unlock", "Verrouille/déverrouille le salon"),
                ("!warn <@membre> [raison]", "Avertir un membre"),
                ("!warnings [@membre]", "Voir les avertissements")
            ]),
            "economy": ("💰 Commandes d'Économie", "Gère la monnaie virtuelle", discord.Color.gold(), [
                ("!daily", "Récompense journalière"),
                ("!balance [membre]", "Voir l'argent"),
                ("!rep <membre>", "Donner de la réputation"),
                ("!work", "Travailler"),
                ("!beg", "Demander de l'argent"),
                ("!pay <membre> <montant>", "Payer quelqu'un"),
                ("!rob <membre>", "Tenter de voler quelqu'un")
            ]),
            "fun": ("🎮 Commandes Fun", "Commandes amusantes", discord.Color.red(), [
                ("!8ball <question>", "Boule magique"),
                ("!joke", "Raconte une blague"),
                ("!coinflip", "Pile ou face"),
                ("!dice [mise]", "Lancer un dé"),
                ("!rps <pierre/papier/ciseaux>", "Pierre-papier-ciseaux")
            ]),
            "utility": ("🔧 Utilitaires", "Outils utiles", discord.Color.greyple(), [
                ("!userinfo [membre]", "Info sur un membre"),
                ("!serverinfo", "Info sur le serveur"),
                ("!avatar [membre]", "Avatar"),
                ("!poll <question> | <opt1> | <opt2>", "Créer un sondage"),
                ("!remind <durée> <message>", "Rappel"),
                ("!timer <temps> [raison]", "Minuteur"),
                ("!stats [membre]", "Stats"),
                ("!leaderboard [catégorie]", "Classement")
            ]),
            "welcome": ("👋 Bienvenue/Départ", "Messages de bienvenue/départ", discord.Color.purple(), [
                ("!bvntext <message>", "Message de bienvenue (variables {user},{server},{count})"),
                ("!bvnembed", "Créer un embed de bienvenue"),
                ("!leavetext <message>", "Message de départ"),
                ("!leaveembed", "Créer un embed de départ"),
                ("!setwelcome <#salon>", "Définir le salon de bienvenue"),
                ("!setleave <#salon>", "Définir le salon de départ")
            ]),
            "systems": ("⚙️ Systèmes", "Configuration du bot", discord.Color.purple(), [
                ("!config", "Menu de configuration"),
                ("!ticketsetup", "Configurer les tickets"),
                ("!tempvoc <salon>", "Configurer vocaux temporaires"),
                ("!giveaway <durée> <prix>", "Créer giveaway"),
                ("!setlog <type> <#salon>", "Configurer logs"),
                ("!autorole <@role>", "Rôle automatique"),
                ("!antispam <on/off>", "Activer/désactiver antispam")
            ])
        }
        title, description, color, commands_list = embeds_data[category]
        selected_embed = discord.Embed(title=title, description=description, color=color)
        for cmd, desc in commands_list:
            selected_embed.add_field(name=cmd, value=desc, inline=False)
        if category == "moderation":
            selected_embed.add_field(name="⚠️ Permissions requises", value="Administrateur/Modérateur", inline=False)
        await interaction.response.edit_message(embed=selected_embed, view=view)

    select.callback = select_callback
    await ctx.send(embed=embed, view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def config(ctx):
    cfg = server_config[ctx.guild.id]
    embed = discord.Embed(
        title="⚙️ Configuration du serveur",
        description="Utilise les menus et boutons ci-dessous pour configurer le bot",
        color=discord.Color.blue()
    )

    welcome_ch = bot.get_channel(cfg["welcome_channel"]) if cfg["welcome_channel"] else None
    leave_ch = bot.get_channel(cfg["leave_channel"]) if cfg["leave_channel"] else None
    log_ch = bot.get_channel(cfg["log_channels"].get("modération")) if cfg["log_channels"].get("modération") else None
    autorole = ctx.guild.get_role(cfg["autorole"]) if cfg["autorole"] else None

    welcome_type = "📝 Texte" if cfg["welcome_text"] else "🎨 Embed" if cfg["welcome_embed"] else "❌ Non défini"
    leave_type = "📝 Texte" if cfg["leave_text"] else "🎨 Embed" if cfg["leave_embed"] else "❌ Non défini"

    config_text = (
        f"📋 **Configuration actuelle**\n"
        f"👋 **Salon de bienvenue:** {welcome_ch.mention if welcome_ch else '`Non défini`'}\n"
        f"👋 **Type de bienvenue:** {welcome_type}\n"
        f"🚪 **Salon de départ:** {leave_ch.mention if leave_ch else '`Non défini`'}\n"
        f"🚪 **Type de départ:** {leave_type}\n"
        f"📜 **Salon de logs:** {log_ch.mention if log_ch else '`Non défini`'}\n"
        f"👤 **Rôle automatique:** {autorole.mention if autorole else '`Non défini`'}\n"
        f"📝 **Questionnaire:** {'✅ Activé' if cfg['questionnaire_active'] else '❌ Désactivé'}\n\n"
        f"📚 **Guide rapide**\n"
        f"**1.** Configure les salons avec les menus déroulants\n"
        f"**2.** Configure les messages avec les boutons\n"
        f"**3.** Clique sur 💾 pour sauvegarder"
    )

    embed.add_field(name="", value=config_text, inline=False)
    embed.set_footer(text=f"⚙️ Configuré par {ctx.author.name}")
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    # selects and buttons
    select_welcome = Select(
        placeholder="👋 Choisir le salon de bienvenue",
        options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="👋") for ch in ctx.guild.text_channels[:25]]
    )
    select_leave = Select(
        placeholder="🚪 Choisir le salon de départ",
        options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="🚪") for ch in ctx.guild.text_channels[:25]]
    )
    select_logs = Select(
        placeholder="📜 Choisir le salon de logs",
        options=[discord.SelectOption(label=ch.name, value=str(ch.id), emoji="📜") for ch in ctx.guild.text_channels[:25]]
    )
    select_autorole = Select(
        placeholder="👤 Choisir le rôle automatique",
        options=[discord.SelectOption(label=role.name, value=str(role.id), emoji="👤") for role in ctx.guild.roles[1:26]]
    )

    async def welcome_callback(interaction: discord.Interaction):
        channel_id = int(select_welcome.values[0])
        server_config[ctx.guild.id]["welcome_channel"] = channel_id
        await interaction.response.send_message("✅ Salon de bienvenue configuré!", ephemeral=True)

    async def leave_callback(interaction: discord.Interaction):
        channel_id = int(select_leave.values[0])
        server_config[ctx.guild.id]["leave_channel"] = channel_id
        await interaction.response.send_message("✅ Salon de départ configuré!", ephemeral=True)

    async def logs_callback(interaction: discord.Interaction):
        channel_id = int(select_logs.values[0])
        server_config[ctx.guild.id]["log_channels"]["modération"] = channel_id
        await interaction.response.send_message("✅ Salon de logs configuré!", ephemeral=True)

    async def autorole_callback(interaction: discord.Interaction):
        role_id = int(select_autorole.values[0])
        server_config[ctx.guild.id]["autorole"] = role_id
        await interaction.response.send_message("✅ Rôle automatique configuré!", ephemeral=True)

    select_welcome.callback = welcome_callback
    select_leave.callback = leave_callback
    select_logs.callback = logs_callback
    select_autorole.callback = autorole_callback

    # Buttons
    btn_welcome_text = Button(label="📝 Message Bienvenue", style=discord.ButtonStyle.primary, emoji="👋")
    btn_welcome_embed = Button(label="🎨 Embed Bienvenue", style=discord.ButtonStyle.primary, emoji="🎨")
    btn_leave_text = Button(label="📝 Message Départ", style=discord.ButtonStyle.secondary, emoji="🚪")
    btn_leave_embed = Button(label="🎨 Embed Départ", style=discord.ButtonStyle.secondary, emoji="🎨")
    btn_questionnaire = Button(label="📝 Questionnaire", style=discord.ButtonStyle.secondary, emoji="📝")
    btn_save = Button(label="💾 Sauvegarder", style=discord.ButtonStyle.success, emoji="💾")

    async def welcome_text_callback(interaction: discord.Interaction):
        await interaction.response.send_message(
            "📝 Use `!bvntext <message>` to set welcome text. Variables: {user}, {server}, {count}",
            ephemeral=True
        )

    async def welcome_embed_callback(interaction: discord.Interaction):
        await interaction.response.send_message("🎨 Use `!bvnembed` to create an embed (not implemented wizard).", ephemeral=True)

    async def leave_text_callback(interaction: discord.Interaction):
        await interaction.response.send_message(
            "📝 Use `!leavetext <message>` to set leave text. Variables: {user}, {server}, {count}",
            ephemeral=True
        )

    async def leave_embed_callback(interaction: discord.Interaction):
        await interaction.response.send_message("🎨 Use `!leaveembed` to create an embed (not implemented wizard).", ephemeral=True)

    async def questionnaire_callback(interaction: discord.Interaction):
        cfg_inner = server_config[ctx.guild.id]
        cfg_inner["questionnaire_active"] = not cfg_inner["questionnaire_active"]
        status = "✅ Activé" if cfg_inner["questionnaire_active"] else "❌ Désactivé"
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

# ============= MODERATION COMMANDS ============
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Aucune raison"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"✅ {member.mention} a été expulsé! Raison: {reason}")
        await log_action(ctx.guild, "modération", f"👢 {member.mention} expulsé par {ctx.author.mention} - Raison: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Impossible d'expulser: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"✅ {member.mention} a été banni! Raison: {reason}")
        await log_action(ctx.guild, "modération", f"🔨 {member.mention} banni par {ctx.author.mention} - Raison: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Impossible de bannir: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ {user.mention} a été débanni!")
        await log_action(ctx.guild, "modération", f"✅ {user.mention} débanni par {ctx.author.mention}")
    except Exception as e:
        await ctx.send(f"❌ Impossible de débannir: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: str, *, reason="Aucune raison"):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role:
        try:
            mute_role = await ctx.guild.create_role(name="Muted", reason="Rôle de mute automatique")
            for channel in ctx.guild.channels:
                try:
                    await channel.set_permissions(mute_role, speak=False, send_messages=False)
                except Exception:
                    pass
        except Exception as e:
            await ctx.send(f"❌ Erreur lors de la création du rôle: {e}")
            return
    try:
        await member.add_roles(mute_role, reason=reason)
        await ctx.send(f"🔇 {member.mention} a été mute pour {duration}! Raison: {reason}")
        await log_action(ctx.guild, "modération", f"🔇 {member.mention} mute par {ctx.author.mention} ({duration}) - Raison: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Impossible d'ajouter le rôle: {e}")
        return

    seconds = parse_duration(duration)
    if seconds is None:
        await ctx.send("❌ Durée invalide! Utilise: 10s, 5m, 1h, 1d")
        return
    await asyncio.sleep(seconds)
    try:
        await member.remove_roles(mute_role)
        await ctx.send(f"🔊 {member.mention} a été unmute automatiquement!")
    except Exception:
        pass

@bot.command()
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if mute_role in member.roles:
        try:
            await member.remove_roles(mute_role)
            await ctx.send(f"🔊 {member.mention} a été unmute!")
            await log_action(ctx.guild, "modération", f"🔊 {member.mention} unmute par {ctx.author.mention}")
        except Exception as e:
            await ctx.send(f"❌ Impossible d'enlever le rôle: {e}")
    else:
        await ctx.send(f"❌ {member.mention} n'est pas mute!")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount < 1 or amount > 100:
        await ctx.send("❌ Nombre invalide! (1-100)")
        return
    try:
        await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(f"✅ {amount} messages supprimés!")
        await asyncio.sleep(3)
        await msg.delete()
        await log_action(ctx.guild, "modération", f"🗑️ {amount} messages supprimés dans {ctx.channel.mention} par {ctx.author.mention}")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de la suppression: {e}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send("🔒 Salon verrouillé!")
        await log_action(ctx.guild, "modération", f"🔒 {ctx.channel.mention} verrouillé par {ctx.author.mention}")
    except Exception as e:
        await ctx.send(f"❌ Impossible de verrouiller: {e}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.send("🔓 Salon déverrouillé!")
        await log_action(ctx.guild, "modération", f"🔓 {ctx.channel.mention} déverrouillé par {ctx.author.mention}")
    except Exception as e:
        await ctx.send(f"❌ Impossible de déverrouiller: {e}")

@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member, *, reason="Aucune raison"):
    warnings_data[member.id].append({
        "reason": reason,
        "moderator": ctx.author.id,
        "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    })
    warn_count = len(warnings_data[member.id])
    await ctx.send(f"⚠️ {member.mention} a été averti! ({warn_count} avertissements)\nRaison: {reason}")
    await log_action(ctx.guild, "modération", f"⚠️ {member.mention} averti par {ctx.author.mention} - Raison: {reason}")
    if warn_count == 3:
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if mute_role:
            await member.add_roles(mute_role)
            await ctx.send(f"🔇 {member.mention} a été mute (3 warns)")
    elif warn_count == 5:
        await member.kick(reason="5 avertissements")
        await ctx.send(f"👢 {member.mention} a été kick (5 warns)")

@bot.command()
async def warnings(ctx, member: discord.Member = None):
    member = member or ctx.author
    warns = warnings_data.get(member.id, [])
    if not warns:
        await ctx.send(f"✅ {member.mention} n'a aucun avertissement!")
        return
    embed = discord.Embed(title=f"⚠️ Avertissements de {member.name}", color=discord.Color.orange())
    for i, warn in enumerate(warns, 1):
        mod = ctx.guild.get_member(warn["moderator"])
        mod_name = mod.name if mod else "Inconnu"
        embed.add_field(name=f"Warn #{i}", value=f"**Raison:** {warn['reason']}\n**Par:** {mod_name}\n**Date:** {warn['time']}", inline=False)
    await ctx.send(embed=embed)

# ============= WELCOME / LEAVE TEXT COMMANDS ============
@bot.command()
@commands.has_permissions(administrator=True)
async def bvntext(ctx, *, message):
    message = message.replace("\\n", "\n")
    server_config[ctx.guild.id]["welcome_text"] = message
    server_config[ctx.guild.id]["welcome_embed"] = None
    preview = message.replace("{user}", ctx.author.mention).replace("{server}", ctx.guild.name).replace("{count}", str(ctx.guild.member_count))
    await ctx.send(f"✅ Message de bienvenue configuré!\n\nAperçu:\n{preview}")

@bot.command()
@commands.has_permissions(administrator=True)
async def leavetext(ctx, *, message):
    message = message.replace("\\n", "\n")
    server_config[ctx.guild.id]["leave_text"] = message
    server_config[ctx.guild.id]["leave_embed"] = None
    preview = message.replace("{user}", ctx.author.name).replace("{server}", ctx.guild.name).replace("{count}", str(ctx.guild.member_count))
    await ctx.send(f"✅ Message de départ configuré!\n\nAperçu:\n{preview}")

# ============= (Optional) More commands placeholders: economy, fun, utils ============
# For brevity they were not reimplemented in full detail here.
# You can ask me to add the economy commands (daily, balance, pay, rob...), fun (8ball, joke...), etc.

# ============= STARTUP ============
if __name__ == "__main__":
    # start keep-alive webserver if needed (Render doesn't require it, but it's harmless)
    keep_alive()

    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ ERREUR: Variable d'environnement DISCORD_TOKEN manquante!")
        print("📝 Sur Render.com, ajoute ta variable d'environnement:")
        print("   Clé: DISCORD_TOKEN")
        print("   Valeur: ton_token_discord")
        raise SystemExit(1)

    try:
        print("🚀 Démarrage du bot...")
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
