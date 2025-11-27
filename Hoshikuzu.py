# Hoshikuzu.py - Bot Disnake complet et corrigé
import os
import asyncio
import random
from datetime import datetime
from collections import defaultdict
from threading import Thread
from typing import Dict, Any, Tuple, Optional

import disnake as discord
from disnake.ext import commands, tasks
from disnake.ui import Button, View, Select, Modal, TextInput

from flask import Flask

# ============= CONFIGURATION =============
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ============= DONNÉES EN MÉMOIRE ==========
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

# ============= KEEP-ALIVE (Flask) ==========
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def _run_web():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=_run_web, daemon=True)
    t.start()

# ============= HELPERS ====================
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

def parse_duration(s: str) -> Optional[int]:
    try:
        mapping = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        amount = int(s[:-1])
        unit = s[-1]
        return amount * mapping[unit]
    except Exception:
        return None

# ============= BACKGROUND TASKS ===========
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

# ============= EVENTS: members / messages / voice ==========
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
    # welcome message or embed
    ch_id = cfg.get("welcome_channel")
    if ch_id:
        ch = bot.get_channel(ch_id)
        if ch:
            replacements = {"{user}": member.mention, "{server}": member.guild.name, "{count}": str(member.guild.member_count)}
            if cfg.get("welcome_embed"):
                ed = cfg["welcome_embed"]
                title = ed.get("title", "Bienvenue!")
                desc = ed.get("description", "")
                for k, v in replacements.items():
                    title = title.replace(k, v)
                    desc = desc.replace(k, v)
                try:
                    color = getattr(discord.Color, ed.get("color", "green"))()
                except Exception:
                    color = discord.Color.green()
                embed = discord.Embed(title=title, description=desc, color=color)
                thumb = ed.get("thumbnail")
                if thumb == "member":
                    embed.set_thumbnail(url=member.display_avatar.url)
                elif thumb == "server" and member.guild.icon:
                    embed.set_thumbnail(url=member.guild.icon.url)
                elif thumb:
                    embed.set_thumbnail(url=thumb)
                if ed.get("image"):
                    embed.set_image(url=ed.get("image"))
                if ed.get("footer"):
                    ft = ed.get("footer", "")
                    for k, v in replacements.items():
                        ft = ft.replace(k, v)
                    embed.set_footer(text=ft)
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass
            elif cfg.get("welcome_text"):
                msg = cfg["welcome_text"]
                for k, v in replacements.items():
                    msg = msg.replace(k, v)
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
                title = ed.get("title", "Au revoir!")
                desc = ed.get("description", "")
                for k, v in replacements.items():
                    title = title.replace(k, v)
                    desc = desc.replace(k, v)
                try:
                    color = getattr(discord.Color, ed.get("color", "red"))()
                except Exception:
                    color = discord.Color.red()
                embed = discord.Embed(title=title, description=desc, color=color)
                thumb = ed.get("thumbnail")
                if thumb == "member":
                    embed.set_thumbnail(url=member.display_avatar.url)
                elif thumb == "server" and member.guild.icon:
                    embed.set_thumbnail(url=member.guild.icon.url)
                elif thumb:
                    embed.set_thumbnail(url=thumb)
                if ed.get("image"):
                    embed.set_image(url=ed.get("image"))
                if ed.get("footer"):
                    ft = ed.get("footer", "")
                    for k, v in replacements.items():
                        ft = ft.replace(k, v)
                    embed.set_footer(text=ft)
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass
            elif cfg.get("leave_text"):
                msg = cfg["leave_text"]
                for k, v in replacements.items():
                    msg = msg.replace(k, v)
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
            async for m in message.channel.history(limit=antispam.get("messages", 5)):
                if m.author == message.author and (datetime.utcnow() - m.created_at).total_seconds() < antispam.get("seconds", 5):
                    recent.append(m)
        except Exception:
            recent = []
        if len(recent) >= antispam.get("messages", 5):
            try:
                await message.channel.purge(limit=antispam.get("messages", 5), check=lambda m: m.author == message.author)
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
    # temporary voice channel creation
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

# ============= EDITOR D'EMBED INTERACTIF ==========
# state key: (guild_id, user_id, mode) where mode is "welcome" or "leave"
embed_editors: Dict[Tuple[int, int, str], Dict[str, Any]] = {}

def _default_editor_state(mode: str) -> Dict[str, Any]:
    return {
        "mode": mode,
        "title": "Bienvenue!" if mode == "welcome" else "Au revoir!",
        "description": "",
        "color": "blue",
        "thumbnail": "member",  # 'member' | 'server' | url | None
        "image": None,
        "footer": "",
        "message": None  # preview message reference
    }

def build_preview_embed(state: Dict[str, Any], guild: discord.Guild, sample_user: Optional[discord.Member]):
    title = state.get("title") or ""
    desc = state.get("description") or ""
    color_name = state.get("color", "blue")
    try:
        color = getattr(discord.Color, color_name)()
    except Exception:
        try:
            # allow hex like "#RRGGBB"
            hexv = color_name.lstrip("#")
            color = discord.Color(int(hexv, 16))
        except Exception:
            color = discord.Color.blue()
    embed = discord.Embed(title=title, description=desc, color=color)
    thumb = state.get("thumbnail")
    if thumb == "member" and sample_user:
        embed.set_thumbnail(url=sample_user.display_avatar.url)
    elif thumb == "server" and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    elif thumb:
        try:
            embed.set_thumbnail(url=thumb)
        except Exception:
            pass
    if state.get("image"):
        try:
            embed.set_image(url=state.get("image"))
        except Exception:
            pass
    if state.get("footer"):
        embed.set_footer(text=state.get("footer"))
    return embed

class SingleFieldModal(Modal):
    def __init__(self, title: str, field_name: str, placeholder: str, max_length: int, state_key: str, editor_key: Tuple[int, int, str]):
        super().__init__(title=title)
        self.state_key = state_key
        self.editor_key = editor_key
        style = TextInput.paragraph if max_length > 100 else TextInput.short
        self.add_item(TextInput(label=field_name, placeholder=placeholder, style=style, min_length=0, max_length=max_length))

    async def callback(self, interaction: discord.Interaction):
        guild_id, user_id, mode = self.editor_key
        key = (guild_id, user_id, mode)
        state = embed_editors.get(key)
        if not state:
            await interaction.response.send_message("Éditeur introuvable (expiré). Relance la commande.", ephemeral=True)
            return
        value = self.children[0].value
        state[self.state_key] = value
        # update preview
        msg = state.get("message")
        guild = bot.get_guild(guild_id)
        user = guild.get_member(user_id) if guild else None
        preview = build_preview_embed(state, guild, user)
        view = build_editor_view(guild_id, user_id, mode, page=1)
        try:
            if msg:
                await msg.edit(embed=preview, view=view)
            await interaction.response.send_message("✅ Modifié.", ephemeral=True)
        except Exception:
            try:
                await interaction.response.send_message("✅ Modifié (aperçu non mis à jour).", ephemeral=True)
            except Exception:
                pass

def build_editor_view(guild_id: int, user_id: int, mode: str, page: int = 1) -> View:
    key = (guild_id, user_id, mode)
    state = embed_editors.get(key, _default_editor_state(mode))
    view = View(timeout=600)
    # Page 1: Texte
    if page == 1:
        btn_title = Button(label="Titre", style=discord.ButtonStyle.primary, row=0)
        btn_desc = Button(label="Description", style=discord.ButtonStyle.primary, row=0)
        async def title_cb(i: discord.Interaction):
            modal = SingleFieldModal(title="Modifier le titre", field_name="Titre", placeholder="Titre de l'embed", max_length=256, state_key="title", editor_key=key)
            await i.response.send_modal(modal)
        async def desc_cb(i: discord.Interaction):
            modal = SingleFieldModal(title="Modifier la description", field_name="Description", placeholder="Texte (utilise \\n pour saut)", max_length=2000, state_key="description", editor_key=key)
            await i.response.send_modal(modal)
        btn_title.callback = title_cb
        btn_desc.callback = desc_cb
        view.add_item(btn_title)
        view.add_item(btn_desc)
        btn_next = Button(label="▶ Page suivante", style=discord.ButtonStyle.secondary, row=4)
        async def next_cb(i: discord.Interaction):
            await show_editor_page(i, guild_id, user_id, mode, 2)
        btn_next.callback = next_cb
        view.add_item(btn_next)
    # Page 2: Visuel
    elif page == 2:
        color_select = Select(
            placeholder="Couleur (choisis ou sélectionne 'Personnalisée')",
            options=[
                discord.SelectOption(label="Bleu", value="blue"),
                discord.SelectOption(label="Vert", value="green"),
                discord.SelectOption(label="Rouge", value="red"),
                discord.SelectOption(label="Or", value="gold"),
                discord.SelectOption(label="Gris", value="greyple"),
                discord.SelectOption(label="Noir", value="dark"),
                discord.SelectOption(label="Personnalisée (hex)", value="custom")
            ],
            row=0
        )
        async def color_cb(i: discord.Interaction):
            sel = i.data.get("values", [None])[0]
            if not sel:
                await i.response.send_message("❌ Aucune couleur sélectionnée.", ephemeral=True)
                return
            if sel == "custom":
                modal = SingleFieldModal(title="Couleur hex", field_name="Hex couleur", placeholder="#FF00FF ou FF00FF", max_length=7, state_key="color", editor_key=key)
                await i.response.send_modal(modal)
            else:
                state["color"] = sel
                msg = state.get("message"); guild = bot.get_guild(guild_id); user = guild.get_member(user_id) if guild else None
                try:
                    if msg:
                        await msg.edit(embed=build_preview_embed(state, guild, user), view=build_editor_view(guild_id, user_id, mode, 2))
                    await i.response.send_message("✅ Couleur mise à jour.", ephemeral=True)
                except Exception:
                    await i.response.send_message("✅ Couleur mise à jour.", ephemeral=True)
        color_select.callback = color_cb
        view.add_item(color_select)
        # Thumbnail options
        btn_thumb_member = Button(label="Thumbnail: Membre", style=discord.ButtonStyle.secondary, row=1)
        btn_thumb_server = Button(label="Thumbnail: Serveur", style=discord.ButtonStyle.secondary, row=1)
        btn_thumb_url = Button(label="Thumbnail: URL", style=discord.ButtonStyle.secondary, row=1)
        async def thumb_member_cb(i: discord.Interaction):
            state["thumbnail"] = "member"; msg = state.get("message"); guild = bot.get_guild(guild_id); user = guild.get_member(user_id) if guild else None
            try:
                if msg:
                    await msg.edit(embed=build_preview_embed(state, guild, user), view=build_editor_view(guild_id, user_id, mode, 2))
                await i.response.send_message("✅ Thumbnail réglé sur membre.", ephemeral=True)
            except Exception:
                await i.response.send_message("✅ Thumbnail réglé sur membre.", ephemeral=True)
        async def thumb_server_cb(i: discord.Interaction):
            state["thumbnail"] = "server"; msg = state.get("message"); guild = bot.get_guild(guild_id); user = guild.get_member(user_id) if guild else None
            try:
                if msg:
                    await msg.edit(embed=build_preview_embed(state, guild, user), view=build_editor_view(guild_id, user_id, mode, 2))
                await i.response.send_message("✅ Thumbnail réglé sur serveur.", ephemeral=True)
            except Exception:
                await i.response.send_message("✅ Thumbnail réglé sur serveur.", ephemeral=True)
        async def thumb_url_cb(i: discord.Interaction):
            modal = SingleFieldModal(title="Thumbnail URL", field_name="Thumbnail URL", placeholder="https://...", max_length=300, state_key="thumbnail", editor_key=key)
            await i.response.send_modal(modal)
        btn_thumb_member.callback = thumb_member_cb
        btn_thumb_server.callback = thumb_server_cb
        btn_thumb_url.callback = thumb_url_cb
        view.add_item(btn_thumb_member)
        view.add_item(btn_thumb_server)
        view.add_item(btn_thumb_url)
        # Image URL
        btn_image = Button(label="Image (URL)", style=discord.ButtonStyle.primary, row=2)
        async def image_cb(i: discord.Interaction):
            modal = SingleFieldModal(title="Image URL", field_name="Image URL", placeholder="https://...", max_length=300, state_key="image", editor_key=key)
            await i.response.send_modal(modal)
        btn_image.callback = image_cb
        view.add_item(btn_image)
        # Navigation
        btn_back = Button(label="◀ Page précédente", style=discord.ButtonStyle.secondary, row=4)
        btn_next = Button(label="▶ Page suivante", style=discord.ButtonStyle.secondary, row=4)
        async def back_cb(i: discord.Interaction):
            await show_editor_page(i, guild_id, user_id, mode, 1)
        async def next_cb(i: discord.Interaction):
            await show_editor_page(i, guild_id, user_id, mode, 3)
        btn_back.callback = back_cb
        btn_next.callback = next_cb
        view.add_item(btn_back)
        view.add_item(btn_next)
    # Page 3: Footer & Save & Preview
    elif page == 3:
        btn_footer = Button(label="Footer", style=discord.ButtonStyle.primary, row=0)
        btn_preview = Button(label="Aperçu complet", style=discord.ButtonStyle.secondary, row=0)
        btn_save = Button(label="💾 Sauvegarder", style=discord.ButtonStyle.success, row=0)
        async def footer_cb(i: discord.Interaction):
            modal = SingleFieldModal(title="Footer", field_name="Footer", placeholder="Texte du footer", max_length=2048, state_key="footer", editor_key=key)
            await i.response.send_modal(modal)
        async def preview_cb(i: discord.Interaction):
            guild = bot.get_guild(guild_id); user = guild.get_member(user_id) if guild else None
            await i.response.send_message(embed=build_preview_embed(state, guild, user), ephemeral=True)
        async def save_cb(i: discord.Interaction):
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
        btn_back = Button(label="◀ Page précédente", style=discord.ButtonStyle.secondary, row=4)
        async def back_cb(i: discord.Interaction):
            await show_editor_page(i, guild_id, user_id, mode, 2)
        btn_back.callback = back_cb
        view.add_item(btn_back)
    return view

async def show_editor_page(interaction: discord.Interaction, guild_id: int, user_id: int, mode: str, page: int):
    key = (guild_id, user_id, mode)
    state = embed_editors.get(key)
    if not state:
        state = _default_editor_state(mode)
        embed_editors[key] = state
    guild = bot.get_guild(guild_id)
    user = guild.get_member(user_id) if guild else None
    preview = build_preview_embed(state, guild, user)
    view = build_editor_view(guild_id, user_id, mode, page=page)
    state["message"] = state.get("message") or interaction.message
    try:
        await interaction.response.edit_message(embed=preview, view=view)
    except Exception:
        try:
            await interaction.response.send_message(embed=preview, view=view, ephemeral=True)
        except Exception:
            pass

# Commands to open the editor (admin only)
@bot.command()
@commands.has_permissions(administrator=True)
async def bvnembed(ctx):
    key = (ctx.guild.id, ctx.author.id, "welcome")
    embed_editors[key] = _default_editor_state("welcome")
    preview = build_preview_embed(embed_editors[key], ctx.guild, ctx.author)
    view = build_editor_view(ctx.guild.id, ctx.author.id, "welcome", page=1)
    msg = await ctx.send("🎨 Éditeur d'embed de bienvenue — " + ctx.author.mention, embed=preview, view=view)
    embed_editors[key]["message"] = msg

@bot.command()
@commands.has_permissions(administrator=True)
async def leaveembed(ctx):
    key = (ctx.guild.id, ctx.author.id, "leave")
    embed_editors[key] = _default_editor_state("leave")
    preview = build_preview_embed(embed_editors[key], ctx.guild, ctx.author)
    view = build_editor_view(ctx.guild.id, ctx.author.id, "leave", page=1)
    msg = await ctx.send("🎨 Éditeur d'embed de départ — " + ctx.author.mention, embed=preview, view=view)
    embed_editors[key]["message"] = msg

# ============= COMMANDES: help & config (2 pages) ==========
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🛡️ Commandes", description="Utilise `!config` pour configurer le bot. Utilise `!bvnembed` / `!leaveembed` pour lancer l'éditeur d'embed.", color=discord.Color.blue())
    embed.add_field(name="Prefix", value="`!`", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def config(ctx):
    cfg = server_config[ctx.guild.id]
    # Page 1 embed
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

    # Selects (rows assigned 0..3)
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

    async def sel_welcome_cb(interaction: discord.Interaction):
        try:
            server_config[ctx.guild.id]["welcome_channel"] = int(select_welcome.values[0])
            await interaction.response.send_message("✅ Salon de bienvenue configuré!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    async def sel_leave_cb(interaction: discord.Interaction):
        try:
            server_config[ctx.guild.id]["leave_channel"] = int(select_leave.values[0])
            await interaction.response.send_message("✅ Salon de départ configuré!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    async def sel_logs_cb(interaction: discord.Interaction):
        try:
            server_config[ctx.guild.id]["log_channels"]["modération"] = int(select_logs.values[0])
            await interaction.response.send_message("✅ Salon de logs configuré!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    async def sel_autorole_cb(interaction: discord.Interaction):
        try:
            server_config[ctx.guild.id]["autorole"] = int(select_autorole.values[0])
            await interaction.response.send_message("✅ Rôle automatique configuré!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    select_welcome.callback = sel_welcome_cb
    select_leave.callback = sel_leave_cb
    select_logs.callback = sel_logs_cb
    select_autorole.callback = sel_autorole_cb

    view1 = View(timeout=300)
    view1.add_item(select_welcome)
    view1.add_item(select_leave)
    view1.add_item(select_logs)
    view1.add_item(select_autorole)

    # Next button (row 4)
    btn_next = Button(label="▶ Page suivante", style=discord.ButtonStyle.primary, row=4)
    async def next_cb(interaction: discord.Interaction):
        await show_config_page2(interaction, ctx.guild.id)
    btn_next.callback = next_cb
    view1.add_item(btn_next)

    await ctx.send(embed=embed1, view=view1)

async def show_config_page2(interaction: discord.Interaction, guild_id: int):
    guild = bot.get_guild(guild_id)
    cfg = server_config[guild_id]
    embed2 = discord.Embed(title="⚙️ Configuration — Page 2/2", description="Édition messages & embeds, tests et sauvegarde", color=discord.Color.blue())
    embed2.add_field(name="Actions", value="Configurer message/embeds et tester", inline=False)

    # Buttons: edit text, edit embed, test text, test embed, questionnaire toggle, save
    # Row usage constrained: we'll use rows 0..4
    btn_bvn_text = Button(label="📝 Modifier Bienvenue (texte)", style=discord.ButtonStyle.primary, row=0)
    btn_bvn_embed = Button(label="🎨 Éditer Embed Bienvenue", style=discord.ButtonStyle.primary, row=0)
    btn_test_bvn_text = Button(label="🧪 Tester Bienvenue (texte)", style=discord.ButtonStyle.secondary, row=1)
    btn_test_bvn_embed = Button(label="🧪 Tester Embed Bienvenue", style=discord.ButtonStyle.secondary, row=1)

    btn_leave_text = Button(label="📝 Modifier Départ (texte)", style=discord.ButtonStyle.primary, row=2)
    btn_leave_embed = Button(label="🎨 Éditer Embed Départ", style=discord.ButtonStyle.primary, row=2)
    btn_test_leave_text = Button(label="🧪 Tester Départ (texte)", style=discord.ButtonStyle.secondary, row=3)
    btn_test_leave_embed = Button(label="🧪 Tester Embed Départ", style=discord.ButtonStyle.secondary, row=3)

    btn_questionnaire = Button(label="📝 Questionnaire ON/OFF", style=discord.ButtonStyle.success, row=4)
    btn_save = Button(label="💾 Sauvegarder (en mémoire)", style=discord.ButtonStyle.success, row=4)
    btn_back = Button(label="◀ Page précédente", style=discord.ButtonStyle.secondary, row=4)

    # Callbacks
    async def bvn_text_cb(i: discord.Interaction):
        await i.response.send_message("Utilise la commande `!bvntext <message>` (variables: {user}, {server}, {count}, utilises \\n pour retour à la ligne).", ephemeral=True)

    async def bvn_embed_cb(i: discord.Interaction):
        # open editor by invoking command-like behaviour
        key = (guild_id, i.user.id, "welcome")
        embed_editors[key] = _default_editor_state("welcome")
        preview = build_preview_embed(embed_editors[key], guild, guild.get_member(i.user.id))
        view = build_editor_view(guild_id, i.user.id, "welcome", page=1)
        msg = await i.response.send_message("🎨 Éditeur d'embed de bienvenue (Ouvert)", embed=preview, view=view, ephemeral=False)
        # follow-up to fetch the message object (we store reference via fetch)
        try:
            sent = await i.original_message()
            embed_editors[key]["message"] = sent
        except Exception:
            pass

    async def test_bvn_text_cb(i: discord.Interaction):
        cfg_local = server_config[guild_id]
        text = cfg_local.get("welcome_text")
        if not text:
            await i.response.send_message("❌ Aucun message texte de bienvenue configuré.", ephemeral=True)
            return
        ch_id = cfg_local.get("welcome_channel")
        if not ch_id:
            await i.response.send_message("❌ Aucun salon de bienvenue configuré.", ephemeral=True)
            return
        channel = bot.get_channel(ch_id)
        if not channel:
            await i.response.send_message("❌ Salon de bienvenue introuvable.", ephemeral=True)
            return
        # compose with sample user: the interaction user
        replacements = {"{user}": i.user.mention, "{server}": guild.name, "{count}": str(guild.member_count)}
        msg = text
        for k, v in replacements.items():
            msg = msg.replace(k, v)
        try:
            await channel.send(msg)
            await i.response.send_message(f"✅ Message de bienvenue envoyé dans {channel.mention}.", ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"❌ Erreur en envoyant: {e}", ephemeral=True)

    async def test_bvn_embed_cb(i: discord.Interaction):
        cfg_local = server_config[guild_id]
        ed = cfg_local.get("welcome_embed")
        if not ed:
            await i.response.send_message("❌ Aucun embed de bienvenue configuré.", ephemeral=True)
            return
        ch_id = cfg_local.get("welcome_channel")
        if not ch_id:
            await i.response.send_message("❌ Aucun salon de bienvenue configuré.", ephemeral=True)
            return
        channel = bot.get_channel(ch_id)
        if not channel:
            await i.response.send_message("❌ Salon de bienvenue introuvable.", ephemeral=True)
            return
        # build embed with interaction user as sample
        state = {
            "title": ed.get("title"), "description": ed.get("description"),
            "color": ed.get("color", "blue"), "thumbnail": ed.get("thumbnail"),
            "image": ed.get("image"), "footer": ed.get("footer")
        }
        preview = build_preview_embed(state, guild, guild.get_member(i.user.id))
        try:
            await channel.send(embed=preview)
            await i.response.send_message(f"✅ Embed de bienvenue envoyé dans {channel.mention}.", ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    async def leave_text_cb(i: discord.Interaction):
        await i.response.send_message("Utilise la commande `!leavetext <message>` (variables: {user}, {server}, {count}).", ephemeral=True)

    async def leave_embed_cb(i: discord.Interaction):
        key = (guild_id, i.user.id, "leave")
        embed_editors[key] = _default_editor_state("leave")
        preview = build_preview_embed(embed_editors[key], guild, guild.get_member(i.user.id))
        view = build_editor_view(guild_id, i.user.id, "leave", page=1)
        msg = await i.response.send_message("🎨 Éditeur d'embed de départ (Ouvert)", embed=preview, view=view, ephemeral=False)
        try:
            sent = await i.original_message()
            embed_editors[key]["message"] = sent
        except Exception:
            pass

    async def test_leave_text_cb(i: discord.Interaction):
        cfg_local = server_config[guild_id]
        text = cfg_local.get("leave_text")
        if not text:
            await i.response.send_message("❌ Aucun message texte de départ configuré.", ephemeral=True)
            return
        ch_id = cfg_local.get("leave_channel")
        if not ch_id:
            await i.response.send_message("❌ Aucun salon de départ configuré.", ephemeral=True)
            return
        channel = bot.get_channel(ch_id)
        if not channel:
            await i.response.send_message("❌ Salon de départ introuvable.", ephemeral=True)
            return
        replacements = {"{user}": i.user.mention, "{server}": guild.name, "{count}": str(guild.member_count)}
        msg = text
        for k, v in replacements.items():
            msg = msg.replace(k, v)
        try:
            await channel.send(msg)
            await i.response.send_message(f"✅ Message de départ envoyé dans {channel.mention}.", ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    async def test_leave_embed_cb(i: discord.Interaction):
        cfg_local = server_config[guild_id]
        ed = cfg_local.get("leave_embed")
        if not ed:
            await i.response.send_message("❌ Aucun embed de départ configuré.", ephemeral=True)
            return
        ch_id = cfg_local.get("leave_channel")
        if not ch_id:
            await i.response.send_message("❌ Aucun salon de départ configuré.", ephemeral=True)
            return
        channel = bot.get_channel(ch_id)
        if not channel:
            await i.response.send_message("❌ Salon de départ introuvable.", ephemeral=True)
            return
        state = {
            "title": ed.get("title"), "description": ed.get("description"),
            "color": ed.get("color", "red"), "thumbnail": ed.get("thumbnail"),
            "image": ed.get("image"), "footer": ed.get("footer")
        }
        preview = build_preview_embed(state, guild, guild.get_member(i.user.id))
        try:
            await channel.send(embed=preview)
            await i.response.send_message(f"✅ Embed de départ envoyé dans {channel.mention}.", ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    async def questionnaire_cb(i: discord.Interaction):
        cfg_local = server_config[guild_id]
        cfg_local["questionnaire_active"] = not cfg_local["questionnaire_active"]
        status = "✅ Activé" if cfg_local["questionnaire_active"] else "❌ Désactivé"
        await i.response.send_message(f"📝 Questionnaire: {status}", ephemeral=True)

    async def save_cb(i: discord.Interaction):
        await i.response.send_message("✅ Configuration sauvegardée en mémoire (non persistée).", ephemeral=True)

    async def back_cb(i: discord.Interaction):
        # rebuild page1 and edit message
        await i.response.defer()
        # To go back we reconstruct the selects view - simpler to call /config again for the user
        try:
            await i.followup.send("Retour vers la page précédente : utilise `!config` à nouveau.", ephemeral=True)
        except Exception:
            pass

    btn_bvn_text.callback = bvn_text_cb
    btn_bvn_embed.callback = bvn_embed_cb
    btn_test_bvn_text.callback = test_bvn_text_cb
    btn_test_bvn_embed.callback = test_bvn_embed_cb

    btn_leave_text.callback = leave_text_cb
    btn_leave_embed.callback = leave_embed_cb
    btn_test_leave_text.callback = test_leave_text_cb
    btn_test_leave_embed.callback = test_leave_embed_cb

    btn_questionnaire.callback = questionnaire_cb
    btn_save.callback = save_cb
    btn_back.callback = back_cb

    view2 = View(timeout=300)
    view2.add_item(btn_bvn_text)
    view2.add_item(btn_bvn_embed)
    view2.add_item(btn_test_bvn_text)
    view2.add_item(btn_test_bvn_embed)
    view2.add_item(btn_leave_text)
    view2.add_item(btn_leave_embed)
    view2.add_item(btn_test_leave_text)
    view2.add_item(btn_test_leave_embed)
    view2.add_item(btn_questionnaire)
    view2.add_item(btn_save)
    view2.add_item(btn_back)

    try:
        await interaction.response.edit_message(embed=embed2, view=view2)
    except Exception:
        try:
            await interaction.response.send_message(embed=embed2, view=view2)
        except Exception:
            pass

# ============= MODÉRATION =============
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = "Aucune raison"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"✅ {member.mention} expulsé. Raison: {reason}")
        await log_action(ctx.guild, "modération", f"👢 {member.mention} expulsé par {ctx.author.mention} - {reason}")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = "Aucune raison"):
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
async def mute(ctx, member: discord.Member, duration: str, *, reason: str = "Aucune raison"):
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
        await ctx.channel.purge(limit=amount + 1)
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
async def warn(ctx, member: discord.Member, *, reason: str = "Aucune raison"):
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
async def warnings(ctx, member: discord.Member = None):
    member = member or ctx.author
    warns = warnings_data.get(member.id, [])
    if not warns:
        await ctx.send(f"✅ {member.mention} n'a aucun avertissement.")
        return
    embed = discord.Embed(title=f"Avertissements de {member.name}", color=discord.Color.orange())
    for i, w in enumerate(warns, 1):
        mod = ctx.guild.get_member(w["moderator"])
        mod_name = mod.name if mod else "Inconnu"
        embed.add_field(name=f"Warn #{i}", value=f"**Raison:** {w['reason']}\n**Par:** {mod_name}\n**Date:** {w['time']}", inline=False)
    await ctx.send(embed=embed)

# ============= BIENVENUE / DEPART (texte direct) ==========
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

# ============= STARTUP ===================
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
