# Hoshikuzu.py - Full bot with advanced embed editor + tester + persistence
# Requires: disnake==2.9.2, flask, aiohttp (optional), pillow (optional)
# Place this file and run. Ensure DISCORD_TOKEN env var is set.

import os
import json
import asyncio
import random
from datetime import datetime
from threading import Thread
from collections import defaultdict

import disnake as discord
from disnake.ext import commands, tasks
from disnake.ui import Button, View, Select
from disnake import TextInput, Modal, TextInputStyle

from flask import Flask

# ----------------- Config persistence -----------------
DATA_DIR = "data"
CONFIG_PATH = os.path.join(DATA_DIR, "configs.json")

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def load_configs():
    ensure_data_dir()
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
                # Convert keys that are ints back to ints
                return {int(k): v for k, v in raw.items()}
        except Exception:
            return {}
    return {}

def save_configs(configs):
    ensure_data_dir()
    try:
        # Convert guild ids to strings for json
        raw = {str(k): v for k, v in configs.items()}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("❌ Erreur sauvegarde configs:", e)

# ----------------- Bot & data -----------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# In-memory data structures
economy_data = defaultdict(lambda: {"money":0,"bank":0,"rep":0,"daily_claimed":None,"work_claimed":None,"inventory":[]})
warnings_data = defaultdict(list)
stats_data = defaultdict(lambda: {"messages":0,"voice_time":0,"last_message":None})
giveaways_data = []
voice_tracking = {}

# server_config stored in memory and persisted (only embed-related fields persisted)
default_server_config = lambda: {
    "welcome_channel": None,
    "leave_channel": None,
    "welcome_text": None,
    "leave_text": None,
    "welcome_embed": None,   # dict describing embed
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
}

# Load persistent configs for embeds
_persisted = load_configs()  # mapping guild_id -> persisted subset
server_config = defaultdict(default_server_config)

# Merge persisted embed configs into server_config
for gid, pdata in _persisted.items():
    server_config[gid].update(pdata)

# ----------------- Keep-alive Flask -----------------
app = Flask("")
@app.route("/")
def home():
    return "Bot is running!"

def _run_web():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=_run_web, daemon=True)
    t.start()

# ----------------- Helpers -----------------
def persist_guild_config(guild_id):
    # only persist relevant parts (welcome_embed, leave_embed, welcome_text, leave_text)
    to_save = {
        "welcome_embed": server_config[guild_id].get("welcome_embed"),
        "leave_embed": server_config[guild_id].get("leave_embed"),
        "welcome_text": server_config[guild_id].get("welcome_text"),
        "leave_text": server_config[guild_id].get("leave_text")
    }
    # load file, update, write
    cfgs = load_configs()
    cfgs[guild_id] = to_save
    save_configs(cfgs)

async def log_action(guild, log_type, message):
    cfg = server_config[guild.id]
    ch_id = cfg.get("log_channels", {}).get(log_type)
    if not ch_id:
        return
    ch = bot.get_channel(ch_id)
    if ch:
        embed = discord.Embed(description=message, color=discord.Color.blue(), timestamp=datetime.utcnow())
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

def parse_duration(s: str):
    try:
        mapping = {"s":1,"m":60,"h":3600,"d":86400}
        amount = int(s[:-1])
        unit = s[-1]
        return amount * mapping[unit]
    except Exception:
        return None

def build_disnake_embed(embed_dict: dict) -> discord.Embed:
    """Build a discord.Embed from a stored dict"""
    if not embed_dict:
        return None
    title = embed_dict.get("title")
    description = embed_dict.get("description")
    color_val = embed_dict.get("color")
    try:
        color = discord.Color(int(color_val)) if color_val and isinstance(color_val, int) else discord.Color.blue()
    except Exception:
        try:
            color = getattr(discord.Color, color_val)() if color_val else discord.Color.blue()
        except Exception:
            color = discord.Color.blue()
    e = discord.Embed(title=title or discord.Embed.Empty, description=description or discord.Embed.Empty, color=color)
    if embed_dict.get("thumbnail"):
        e.set_thumbnail(url=embed_dict["thumbnail"])
    if embed_dict.get("image"):
        e.set_image(url=embed_dict["image"])
    if embed_dict.get("footer"):
        e.set_footer(text=embed_dict["footer"])
    # fields
    for f in embed_dict.get("fields", []):
        e.add_field(name=f.get("name", "\u200b"), value=f.get("value", "\u200b"), inline=f.get("inline", False))
    return e

# ----------------- Modal classes for editing fields -----------------
# Note: disnake Modal/TextInput in this version expects TextInput as class attributes

class SingleTextModal(discord.ui.Modal):
    """Generic modal with one TextInput that returns value to callback via `on_submit` override"""
    def __init__(self, title: str, label: str, placeholder: str="", style=TextInputStyle.short, max_length: int = None):
        # define the input as attribute on the instance
        # For disnake 2.9.2, define as class attribute is recommended. We'll dynamically create a subclass.
        self._label = label
        self._placeholder = placeholder
        self._style = style
        self._max_length = max_length
        # We'll call super with simple title; define the input field dynamically by setting on self before super callback executed
        super().__init__(title=title)

    # Define the single input using on_submit params approach
    # For compatibility we define an input field at runtime in callback by using `self.children` - but disnake expects TextInput attributes.
    # To be robust, we implement specific modal subclasses below for each field instead.

# Instead create explicit Modal subclasses for each field to avoid compatibility issues:

class TitleModal(discord.ui.Modal):
    title_input = TextInput(label="Titre", placeholder="Titre (max 256)", style=TextInputStyle.short, max_length=256)
    def __init__(self, editor_key: str, state_key: str):
        super().__init__(title="Modifier le titre")
        self.editor_key = editor_key
        self.state_key = state_key

    async def callback(self, interaction: discord.Interaction):
        value = self.title_input.value
        # load editor state from interaction.message or external mapping
        editor_state = interaction.client._embed_editors.get(self.editor_key)
        if editor_state is None:
            await interaction.response.send_message("Éditeur introuvable (expire). Réouvre l'éditeur.", ephemeral=True)
            return
        editor_state[self.state_key] = value
        await interaction.response.send_message("✅ Titre mis à jour.", ephemeral=True)
        # optionally update live preview message in place if exists
        await editor_state_update_preview(interaction, self.editor_key)

class DescriptionModal(discord.ui.Modal):
    desc_input = TextInput(label="Description", placeholder="Description (utilise \\n pour saut de ligne)", style=TextInputStyle.paragraph, max_length=4000)
    def __init__(self, editor_key: str, state_key: str):
        super().__init__(title="Modifier la description")
        self.editor_key = editor_key
        self.state_key = state_key

    async def callback(self, interaction: discord.Interaction):
        value = self.desc_input.value
        editor_state = interaction.client._embed_editors.get(self.editor_key)
        if editor_state is None:
            await interaction.response.send_message("Éditeur introuvable (expire). Réouvre l'éditeur.", ephemeral=True)
            return
        editor_state[self.state_key] = value
        await interaction.response.send_message("✅ Description mise à jour.", ephemeral=True)
        await editor_state_update_preview(interaction, self.editor_key)

class UrlModal(discord.ui.Modal):
    url_input = TextInput(label="URL", placeholder="https://...", style=TextInputStyle.short, max_length=1000)
    def __init__(self, editor_key: str, state_key: str):
        super().__init__(title="Entrer une URL")
        self.editor_key = editor_key
        self.state_key = state_key

    async def callback(self, interaction: discord.Interaction):
        value = self.url_input.value.strip()
        editor_state = interaction.client._embed_editors.get(self.editor_key)
        if editor_state is None:
            await interaction.response.send_message("Éditeur introuvable (expire). Réouvre l'éditeur.", ephemeral=True)
            return
        editor_state[self.state_key] = value
        await interaction.response.send_message("✅ URL enregistrée.", ephemeral=True)
        await editor_state_update_preview(interaction, self.editor_key)

class FooterModal(discord.ui.Modal):
    footer_input = TextInput(label="Footer", placeholder="Texte du footer", style=TextInputStyle.short, max_length=2048)
    def __init__(self, editor_key: str, state_key: str):
        super().__init__(title="Modifier le footer")
        self.editor_key = editor_key
        self.state_key = state_key

    async def callback(self, interaction: discord.Interaction):
        value = self.footer_input.value
        editor_state = interaction.client._embed_editors.get(self.editor_key)
        if editor_state is None:
            await interaction.response.send_message("Éditeur introuvable (expire). Réouvre l'éditeur.", ephemeral=True)
            return
        editor_state[self.state_key] = value
        await interaction.response.send_message("✅ Footer mis à jour.", ephemeral=True)
        await editor_state_update_preview(interaction, self.editor_key)

class ColorModal(discord.ui.Modal):
    color_input = TextInput(label="Couleur (hex sans # ou int)", placeholder="ex: ff8800 ou 16744448", style=TextInputStyle.short, max_length=12)
    def __init__(self, editor_key: str, state_key: str):
        super().__init__(title="Modifier la couleur (hex ou int)")
        self.editor_key = editor_key
        self.state_key = state_key

    async def callback(self, interaction: discord.Interaction):
        v = self.color_input.value.strip()
        editor_state = interaction.client._embed_editors.get(self.editor_key)
        if editor_state is None:
            await interaction.response.send_message("Éditeur introuvable (expire). Réouvre l'éditeur.", ephemeral=True)
            return
        # parse hex or int
        try:
            if v.startswith("#"):
                v = v[1:]
            if all(c in "0123456789abcdefABCDEF" for c in v):
                color_int = int(v, 16)
            else:
                color_int = int(v)
        except Exception:
            await interaction.response.send_message("❌ Format invalide. Utilise hex (ff8800) ou entier.", ephemeral=True)
            return
        editor_state[self.state_key] = color_int
        await interaction.response.send_message("✅ Couleur mise à jour.", ephemeral=True)
        await editor_state_update_preview(interaction, self.editor_key)

class FieldModal(discord.ui.Modal):
    name_input = TextInput(label="Nom du champ", placeholder="Nom", style=TextInputStyle.short, max_length=256)
    value_input = TextInput(label="Valeur du champ", placeholder="Texte", style=TextInputStyle.paragraph, max_length=1024)
    inline_input = TextInput(label="Inline? (true/false)", placeholder="true ou false", style=TextInputStyle.short, max_length=5)
    def __init__(self, editor_key: str, index: int = None):
        super().__init__(title="Ajouter/Modifier un champ")
        self.editor_key = editor_key
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        editor_state = interaction.client._embed_editors.get(self.editor_key)
        if editor_state is None:
            await interaction.response.send_message("Éditeur introuvable (expire). Réouvre l'éditeur.", ephemeral=True)
            return
        name = self.name_input.value.strip() or "\u200b"
        value = self.value_input.value.strip() or "\u200b"
        inline = self.inline_input.value.strip().lower() in ("1","true","t","y","yes")
        if "fields" not in editor_state or editor_state["fields"] is None:
            editor_state["fields"] = []
        if self.index is None:
            editor_state["fields"].append({"name": name, "value": value, "inline": inline})
            await interaction.response.send_message("✅ Champ ajouté.", ephemeral=True)
        else:
            try:
                editor_state["fields"][self.index] = {"name": name, "value": value, "inline": inline}
                await interaction.response.send_message("✅ Champ modifié.", ephemeral=True)
            except Exception:
                await interaction.response.send_message("❌ Index invalide.", ephemeral=True)
        await editor_state_update_preview(interaction, self.editor_key)

# ----------------- Editor state management -----------------
# We'll store ephemeral editor state per message ID / ephemeral key
bot._embed_editors = {}  # mapping editor_key -> dict(state, metadata)

async def editor_state_update_preview(interaction: discord.Interaction, editor_key: str):
    """If preview message exists in editor state, edit it with new embed snapshot."""
    st = bot._embed_editors.get(editor_key)
    if not st:
        return
    embed_dict = st.get("state", {})
    # build embed and edit preview message if present
    embed = build_disnake_embed(embed_dict)
    msg = st.get("preview_message")
    if msg:
        try:
            await msg.edit(embed=embed)
        except Exception:
            # try to fetch channel/message and update
            try:
                channel = interaction.client.get_channel(st.get("preview_channel"))
                if channel:
                    fetched = await channel.fetch_message(st.get("preview_msg_id"))
                    await fetched.edit(embed=embed)
            except Exception:
                pass

# ----------------- Views -----------------
class EmbedEditorView(View):
    def __init__(self, guild_id: int, kind: str, author_id: int, timeout: int = 600):
        """
        kind: "welcome" or "leave"
        """
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.kind = kind
        self.author_id = author_id
        self.editor_key = f"{guild_id}-{kind}-{int(datetime.utcnow().timestamp())}-{random.randint(1000,9999)}"
        # initialize state from server_config
        base = server_config[guild_id].get(f"{kind}_embed") or {}
        state = {
            "title": base.get("title"),
            "description": base.get("description"),
            "color": base.get("color"),
            "thumbnail": base.get("thumbnail"),
            "image": base.get("image"),
            "footer": base.get("footer"),
            "fields": base.get("fields", [])[:] if base.get("fields") else []
        }
        bot._embed_editors[self.editor_key] = {"state": state, "created_by": author_id, "preview_message": None, "preview_channel": None, "preview_msg_id": None}

        # Buttons: Title, Description, Color, Thumbnail URL, Image URL, Footer, Add Field, Remove Field (select), Save, Test, Close
        # Row layout carefully within 0..4 rows
        self.add_item(Button(label="Titre", style=discord.ButtonStyle.primary, row=0, custom_id=f"{self.editor_key}:title"))
        self.add_item(Button(label="Description", style=discord.ButtonStyle.primary, row=0, custom_id=f"{self.editor_key}:description"))
        self.add_item(Button(label="Couleur", style=discord.ButtonStyle.primary, row=1, custom_id=f"{self.editor_key}:color"))
        self.add_item(Button(label="Thumbnail URL", style=discord.ButtonStyle.secondary, row=1, custom_id=f"{self.editor_key}:thumbnail"))
        self.add_item(Button(label="Image URL", style=discord.ButtonStyle.secondary, row=1, custom_id=f"{self.editor_key}:image"))
        self.add_item(Button(label="Footer", style=discord.ButtonStyle.secondary, row=2, custom_id=f"{self.editor_key}:footer"))
        self.add_item(Button(label="Ajouter un champ", style=discord.ButtonStyle.success, row=2, custom_id=f"{self.editor_key}:addfield"))
        self.add_item(Button(label="Supprimer un champ", style=discord.ButtonStyle.danger, row=2, custom_id=f"{self.editor_key}:rmfield"))
        self.add_item(Button(label="Tester", style=discord.ButtonStyle.primary, row=3, custom_id=f"{self.editor_key}:test"))
        self.add_item(Button(label="Sauvegarder", style=discord.ButtonStyle.success, row=3, custom_id=f"{self.editor_key}:save"))
        self.add_item(Button(label="Fermer", style=discord.ButtonStyle.secondary, row=4, custom_id=f"{self.editor_key}:close"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # allow only author or admins to use editor
        st = bot._embed_editors.get(self.editor_key)
        if not st:
            await interaction.response.send_message("Éditeur expiré ou introuvable.", ephemeral=True)
            return False
        if interaction.user.id == st.get("created_by"):
            return True
        # allow guild admins
        if interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("Seul l'auteur de l'édition ou un administrateur peut utiliser cet éditeur.", ephemeral=True)
        return False

    async def on_timeout(self):
        # cleanup editor state
        bot._embed_editors.pop(self.editor_key, None)

    # button callbacks via custom_id routing
    @discord.ui.button(label="noop", style=discord.ButtonStyle.secondary, custom_id="noop", row=4, disabled=True)
    async def noop(self, button: Button, interaction: discord.Interaction):
        pass

    async def _route(self, interaction: discord.Interaction):
        # determine which button pressed by custom_id
        cid = interaction.data.get("custom_id")
        if not cid:
            await interaction.response.send_message("Erreur interne.", ephemeral=True)
            return
        # custom_id format "<editor_key>:action"
        try:
            key, action = cid.split(":", 1)
        except Exception:
            await interaction.response.send_message("Erreur interne (action).", ephemeral=True)
            return
        if key != self.editor_key:
            await interaction.response.send_message("Éditeur mismatch.", ephemeral=True)
            return

        if action == "title":
            # open TitleModal
            modal = TitleModal(editor_key=self.editor_key, state_key="title")
            await interaction.response.send_modal(modal)
        elif action == "description":
            modal = DescriptionModal(editor_key=self.editor_key, state_key="description")
            await interaction.response.send_modal(modal)
        elif action == "color":
            modal = ColorModal(editor_key=self.editor_key, state_key="color")
            await interaction.response.send_modal(modal)
        elif action == "thumbnail":
            modal = UrlModal(editor_key=self.editor_key, state_key="thumbnail")
            await interaction.response.send_modal(modal)
        elif action == "image":
            modal = UrlModal(editor_key=self.editor_key, state_key="image")
            await interaction.response.send_modal(modal)
        elif action == "footer":
            modal = FooterModal(editor_key=self.editor_key, state_key="footer")
            await interaction.response.send_modal(modal)
        elif action == "addfield":
            modal = FieldModal(editor_key=self.editor_key, index=None)
            await interaction.response.send_modal(modal)
        elif action == "rmfield":
            # ask for index via modal
            modal = SingleIndexModal(editor_key=self.editor_key)
            await interaction.response.send_modal(modal)
        elif action == "test":
            await self._action_test(interaction)
        elif action == "save":
            await self._action_save(interaction)
        elif action == "close":
            bot._embed_editors.pop(self.editor_key, None)
            try:
                await interaction.response.edit_message(content="Éditeur fermé.", embed=None, view=None)
            except Exception:
                try:
                    await interaction.response.send_message("Éditeur fermé.", ephemeral=True)
                except Exception:
                    pass
        else:
            await interaction.response.send_message("Action inconnue.", ephemeral=True)

    async def _action_test(self, interaction: discord.Interaction):
        st = bot._embed_editors.get(self.editor_key)
        if not st:
            await interaction.response.send_message("Éditeur expiré.", ephemeral=True)
            return
        embed_dict = st.get("state", {})
        embed = build_disnake_embed(embed_dict)
        try:
            sent = await interaction.channel.send(embed=embed)
            # store preview message reference for live updates
            st["preview_message"] = sent
            st["preview_channel"] = interaction.channel.id
            st["preview_msg_id"] = sent.id
            await interaction.response.send_message("✅ Aperçu envoyé — message de prévisualisation ajouté.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Impossible d'envoyer l'aperçu: {e}", ephemeral=True)

    async def _action_save(self, interaction: discord.Interaction):
        st = bot._embed_editors.get(self.editor_key)
        if not st:
            await interaction.response.send_message("Éditeur expiré.", ephemeral=True)
            return
        ed = st.get("state", {})
        # sanitize fields: ensure lists/strings
        final = {
            "title": ed.get("title"),
            "description": ed.get("description"),
            "color": ed.get("color"),
            "thumbnail": ed.get("thumbnail"),
            "image": ed.get("image"),
            "footer": ed.get("footer"),
            "fields": ed.get("fields", [])
        }
        # store in server_config
        server_config[self.guild_id][f"{self.kind}_embed"] = final
        persist_guild_config(self.guild_id)
        await interaction.response.send_message("✅ Embed sauvegardé.", ephemeral=True)

    # override interaction handling to route by custom_id
    async def on_error(self, error: Exception, item, interaction: discord.Interaction):
        print("Editor view error:", error)
        try:
            await interaction.response.send_message("❌ Erreur interne dans l'éditeur.", ephemeral=True)
        except Exception:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        st = bot._embed_editors.get(self.editor_key)
        if not st:
            await interaction.response.send_message("Éditeur expiré.", ephemeral=True)
            return False
        # allow only original editor user or admin
        if interaction.user.id == st.get("created_by") or interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("Seul l'auteur de l'édition ou un admin peut utiliser cet éditeur.", ephemeral=True)
        return False

# Modal to request index to remove field
class SingleIndexModal(discord.ui.Modal):
    idx = TextInput(label="Index du champ à supprimer (0 = 1er)", placeholder="ex: 0", style=TextInputStyle.short, max_length=4)
    def __init__(self, editor_key: str):
        super().__init__(title="Supprimer champ")
        self.editor_key = editor_key

    async def callback(self, interaction: discord.Interaction):
        st = bot._embed_editors.get(self.editor_key)
        if not st:
            await interaction.response.send_message("Éditeur expiré.", ephemeral=True)
            return
        try:
            i = int(self.idx.value.strip())
            if "fields" not in st["state"] or i < 0 or i >= len(st["state"]["fields"]):
                await interaction.response.send_message("Index invalide.", ephemeral=True)
                return
            st["state"]["fields"].pop(i)
            await interaction.response.send_message("✅ Champ supprimé.", ephemeral=True)
            await editor_state_update_preview(interaction, self.editor_key)
        except Exception:
            await interaction.response.send_message("❌ Index invalide.", ephemeral=True)

# ----------------- Commands to open editor -----------------
@bot.command()
@commands.has_permissions(administrator=True)
async def bvnembed(ctx):
    """Open advanced embed editor for welcome embed"""
    view = EmbedEditorView(guild_id=ctx.guild.id, kind="welcome", author_id=ctx.author.id)
    # create initial preview message (empty) so preview updates can edit it
    st = bot._embed_editors.get(view.editor_key)
    if st:
        embed = build_disnake_embed(st["state"])
        try:
            preview = await ctx.channel.send(embed=embed)
            st["preview_message"] = preview
            st["preview_channel"] = ctx.channel.id
            st["preview_msg_id"] = preview.id
        except Exception:
            pass
    await ctx.send(embed=discord.Embed(title="Éditeur d'embed - Bienvenue (avancé)"), view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def leaveembed(ctx):
    """Open advanced embed editor for leave embed"""
    view = EmbedEditorView(guild_id=ctx.guild.id, kind="leave", author_id=ctx.author.id)
    st = bot._embed_editors.get(view.editor_key)
    if st:
        embed = build_disnake_embed(st["state"])
        try:
            preview = await ctx.channel.send(embed=embed)
            st["preview_message"] = preview
            st["preview_channel"] = ctx.channel.id
            st["preview_msg_id"] = preview.id
        except Exception:
            pass
    await ctx.send(embed=discord.Embed(title="Éditeur d'embed - Départ (avancé)"), view=view)

# ----------------- Other commands + config UI (kept compact) -----------------
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🛡️ Commandes", description="Liste rapide", color=discord.Color.blue())
    embed.add_field(name="Modération", value="!kick !ban !unban !mute !unmute !clear !lock !unlock !warn !warnings", inline=False)
    embed.add_field(name="Configuration", value="!config | !bvntext | !bvnembed | !leavetext | !leaveembed", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def bvntext(ctx, *, message: str):
    s = message.replace("\\n", "\n")
    server_config[ctx.guild.id]["welcome_text"] = s
    server_config[ctx.guild.id]["welcome_embed"] = None
    persist_guild_config(ctx.guild.id)
    preview = s.replace("{user}", ctx.author.mention).replace("{server}", ctx.guild.name).replace("{count}", str(ctx.guild.member_count))
    await ctx.send(f"✅ Message de bienvenue configuré!\n\nAperçu:\n{preview}")

@bot.command()
@commands.has_permissions(administrator=True)
async def leavetext(ctx, *, message: str):
    s = message.replace("\\n", "\n")
    server_config[ctx.guild.id]["leave_text"] = s
    server_config[ctx.guild.id]["leave_embed"] = None
    persist_guild_config(ctx.guild.id)
    preview = s.replace("{user}", ctx.author.name).replace("{server}", ctx.guild.name).replace("{count}", str(ctx.guild.member_count))
    await ctx.send(f"✅ Message de départ configuré!\n\nAperçu:\n{preview}")

# basic config command kept minimal: opens two-page view (selects + page 2 with buttons to open embed editor)
@bot.command()
@commands.has_permissions(administrator=True)
async def config(ctx):
    cfg = server_config[ctx.guild.id]
    embed1 = discord.Embed(title="⚙️ Configuration — Page 1/2", description="Sélectionne salons/roles", color=discord.Color.blue())
    welcome_ch = bot.get_channel(cfg["welcome_channel"]) if cfg["welcome_channel"] else None
    leave_ch = bot.get_channel(cfg["leave_channel"]) if cfg["leave_channel"] else None
    log_ch = bot.get_channel(cfg["log_channels"].get("modération")) if cfg["log_channels"].get("modération") else None
    autorole = ctx.guild.get_role(cfg["autorole"]) if cfg["autorole"] else None
    stat_text = (
        f"👋 Salon bienvenue: {welcome_ch.mention if welcome_ch else '`Non défini`'}\n"
        f"🚪 Salon départ: {leave_ch.mention if leave_ch else '`Non défini`'}\n"
        f"📜 Salon logs: {log_ch.mention if log_ch else '`Non défini`'}\n"
        f"👤 Rôle automatique: {autorole.mention if autorole else '`Non défini`'}\n"
    )
    embed1.add_field(name="Configuration actuelle", value=stat_text, inline=False)

    select_welcome = Select(placeholder="👋 Choisir le salon de bienvenue", options=[discord.SelectOption(label=ch.name, value=str(ch.id)) for ch in ctx.guild.text_channels[:25]], row=0)
    select_leave = Select(placeholder="🚪 Choisir le salon de départ", options=[discord.SelectOption(label=ch.name, value=str(ch.id)) for ch in ctx.guild.text_channels[:25]], row=1)
    select_logs = Select(placeholder="📜 Choisir le salon de logs", options=[discord.SelectOption(label=ch.name, value=str(ch.id)) for ch in ctx.guild.text_channels[:25]], row=2)

    async def sw_cb(i: discord.Interaction):
        try:
            server_config[ctx.guild.id]["welcome_channel"] = int(select_welcome.values[0])
            await i.response.send_message("✅ Salon de bienvenue configuré!", ephemeral=True)
            persist_guild_config(ctx.guild.id)
        except Exception as e:
            await i.response.send_message(f"❌ {e}", ephemeral=True)
    async def sl_cb(i: discord.Interaction):
        try:
            server_config[ctx.guild.id]["leave_channel"] = int(select_leave.values[0])
            await i.response.send_message("✅ Salon de départ configuré!", ephemeral=True)
            persist_guild_config(ctx.guild.id)
        except Exception as e:
            await i.response.send_message(f"❌ {e}", ephemeral=True)
    async def slog_cb(i: discord.Interaction):
        try:
            server_config[ctx.guild.id]["log_channels"]["modération"] = int(select_logs.values[0])
            await i.response.send_message("✅ Salon de logs configuré!", ephemeral=True)
            persist_guild_config(ctx.guild.id)
        except Exception as e:
            await i.response.send_message(f"❌ {e}", ephemeral=True)

    select_welcome.callback = sw_cb
    select_leave.callback = sl_cb
    select_logs.callback = slog_cb

    view = View(timeout=300)
    view.add_item(select_welcome); view.add_item(select_leave); view.add_item(select_logs)
    btn_next = Button(label="▶ Page suivante", style=discord.ButtonStyle.primary, row=4)
    async def next_cb(i: discord.Interaction):
        # page 2: open embed editor buttons
        view2 = View(timeout=300)
        btn_bvnembed = Button(label="Éditeur Bienvenue (B)", style=discord.ButtonStyle.primary)
        btn_leaveembed = Button(label="Éditeur Départ (B)", style=discord.ButtonStyle.primary)
        async def be_cb(inter):
            await bvnembed(ctx)  # reuse command function
            try:
                await inter.response.defer()
            except Exception:
                pass
        async def le_cb(inter):
            await leaveembed(ctx)
            try:
                await inter.response.defer()
            except Exception:
                pass
        btn_bvnembed.callback = be_cb
        btn_leaveembed.callback = le_cb
        view2.add_item(btn_bvnembed); view2.add_item(btn_leaveembed)
        try:
            await i.response.edit_message(embed=discord.Embed(title="⚙️ Configuration — Page 2/2", description="Ouvre l'éditeur avancé d'embed (B)."), view=view2)
        except Exception:
            try:
                await i.response.send_message(embed=discord.Embed(title="⚙️ Configuration — Page 2/2", description="Ouvre l'éditeur avancé d'embed (B)."), ephemeral=True)
            except Exception:
                pass
    btn_next.callback = next_cb
    view.add_item(btn_next)

    await ctx.send(embed=embed1, view=view)

# ----------------- Moderation commands (kept simple) -----------------
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
async def warn(ctx, member: discord.Member, *, reason: str = "Aucune raison"):
    warnings_data[member.id].append({"reason": reason, "moderator": ctx.author.id, "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M")})
    count = len(warnings_data[member.id])
    await ctx.send(f"⚠️ {member.mention} averti ({count}). Raison: {reason}")
    if count == 3:
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if mute_role:
            try:
                await member.add_roles(mute_role)
                await ctx.send(f"🔇 {member.mention} mute (3 warns).")
            except Exception:
                pass
    elif count == 5:
        try:
            await member.kick(reason="5 warns")
            await ctx.send(f"👢 {member.mention} kick (5 warns).")
        except Exception:
            pass

@bot.command()
async def warnings(ctx, member: discord.Member=None):
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

# ----------------- Member join/leave handing using configured embed/text -----------------
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
    channel_id = cfg.get("welcome_channel")
    if channel_id:
        ch = bot.get_channel(channel_id)
        if ch:
            replacements = {"{user}": member.mention, "{server}": member.guild.name, "{count}": str(member.guild.member_count)}
            if cfg.get("welcome_embed"):
                embed = build_disnake_embed(cfg["welcome_embed"])
                # ensure replacements in title/desc/footer etc by string replacement
                # We re-build from dict to string-replaced dict to avoid missing replacements
                ed_copy = json.loads(json.dumps(cfg["welcome_embed"]))  # deep copy
                for key in ("title","description","footer"):
                    if ed_copy.get(key):
                        for k,v in replacements.items():
                            ed_copy[key] = ed_copy[key].replace(k,v)
                if ed_copy.get("fields"):
                    for f in ed_copy["fields"]:
                        for k,v in replacements.items():
                            f["name"]=f["name"].replace(k,v); f["value"]=f["value"].replace(k,v)
                embed = build_disnake_embed(ed_copy)
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass
            elif cfg.get("welcome_text"):
                txt = cfg["welcome_text"]
                for k,v in replacements.items():
                    txt = txt.replace(k,v)
                try:
                    await ch.send(txt)
                except Exception:
                    pass
    await log_action(member.guild, "membres", f"📥 {member.mention} a rejoint le serveur")

@bot.event
async def on_member_remove(member):
    cfg = server_config[member.guild.id]
    channel_id = cfg.get("leave_channel")
    if channel_id:
        ch = bot.get_channel(channel_id)
        if ch:
            replacements = {"{user}": member.name, "{server}": member.guild.name, "{count}": str(member.guild.member_count)}
            if cfg.get("leave_embed"):
                ed_copy = json.loads(json.dumps(cfg["leave_embed"]))
                for key in ("title","description","footer"):
                    if ed_copy.get(key):
                        for k,v in replacements.items():
                            ed_copy[key] = ed_copy[key].replace(k,v)
                if ed_copy.get("fields"):
                    for f in ed_copy["fields"]:
                        for k,v in replacements.items():
                            f["name"]=f["name"].replace(k,v); f["value"]=f["value"].replace(k,v)
                embed = build_disnake_embed(ed_copy)
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass
            elif cfg.get("leave_text"):
                txt = cfg["leave_text"]
                for k,v in replacements.items():
                    txt = txt.replace(k,v)
                try:
                    await ch.send(txt)
                except Exception:
                    pass
    await log_action(member.guild, "membres", f"📤 {member.name} a quitté le serveur")

# ----------------- Startup -----------------
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
