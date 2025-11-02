#!/usr/bin/env python3
import os, json, threading, http.server, socketserver, traceback
import discord
from discord.ext import commands

# === Keep Alive ===
def keep_alive():
    try:
        port = int(os.environ.get("PORT", 8080))
    except Exception:
        port = 8080
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    with socketserver.TCPServer(("", port), QuietHandler) as httpd:
        print(f"[keep-alive] HTTP running on port {port}")
        httpd.serve_forever()
threading.Thread(target=keep_alive, daemon=True).start()

# === Data Management ===
DATA_FILE = "hoshikuzu_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("load_data error:", e)
    return {"config": {}, "tickets": {}}

def save_data(d):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("save_data error:", e)

data = load_data()

def get_conf(gid, key, default=None):
    return data.get("config", {}).get(str(gid), {}).get(key, default)

def set_conf(gid, key, value):
    data.setdefault("config", {}).setdefault(str(gid), {})[key] = value
    save_data(data)

def get_gconf(gid):
    return data.get("config", {}).get(str(gid), {})

# === Bot Init ===
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)
EMOJI = "<a:caarrow:1433143710094196997>"

@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")

# === Commandes Utiles ===
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🌿 Hoshikuzu — Commandes", color=discord.Color.green())
    e.add_field(name="Config", value="`+config` panneau interactif", inline=False)
    e.add_field(name="Liens", value="`+allowlink #channel` / `+disallowlink #channel`", inline=False)
    e.add_field(name="Vocale", value="`🔊Créer un voc` automatique", inline=False)
    e.add_field(name="Lock", value="`+lock` / `+unlock`", inline=False)
    e.add_field(name="Roles", value="`+role @user @role` / `+rolejoin @role`", inline=False)
    e.add_field(name="Tickets", value="`+ticket`", inline=False)
    e.add_field(name="Tests", value="`+testwelcome` / `+testleave`", inline=False)
    await ctx.send(embed=e)

@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 Salon verrouillé.")

@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔓 Salon déverrouillé.")

@bot.command(name="role")
@commands.has_permissions(manage_roles=True)
async def role(ctx, member: discord.Member, role: discord.Role):
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send(f"❌ {role.name} retiré de {member.mention}")
    else:
        await member.add_roles(role)
        await ctx.send(f"✅ {role.name} ajouté à {member.mention}")

@bot.command(name="rolejoin")
@commands.has_permissions(manage_roles=True)
async def rolejoin(ctx, role: discord.Role):
    set_conf(ctx.guild.id, "auto_role", role.id)
    await ctx.send(f"✅ Rôle d’arrivée défini : {role.name}")

@bot.command(name="ticket")
async def ticket(ctx):
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    channel = await ctx.guild.create_text_channel(name=f"ticket-{ctx.author.name}", overwrites=overwrites)
    await channel.send(f"{ctx.author.mention} 🎫 Ton ticket est ouvert ici.")

@bot.command(name="allowlink")
@commands.has_permissions(manage_guild=True)
async def allowlink(ctx, channel: discord.TextChannel):
    links = get_conf(ctx.guild.id, "allow_links", [])
    if channel.id not in links:
        links.append(channel.id)
        set_conf(ctx.guild.id, "allow_links", links)
        await ctx.send(f"✅ Liens autorisés dans {channel.mention}")
    else:
        await ctx.send(f"ℹ️ Les liens sont déjà autorisés ici.")

@bot.command(name="disallowlink")
@commands.has_permissions(manage_guild=True)
async def disallowlink(ctx, channel: discord.TextChannel):
    links = get_conf(ctx.guild.id, "allow_links", [])
    if channel.id in links:
        links.remove(channel.id)
        set_conf(ctx.guild.id, "allow_links", links)
        await ctx.send(f"❌ Liens désactivés dans {channel.mention}")
    else:
        await ctx.send(f"ℹ️ Les liens étaient déjà désactivés ici.")
# === Panneau de configuration ===
class ConfigView(discord.ui.View):
    def __init__(self, guild, author_id, timeout=180):
        super().__init__(timeout=timeout)
        self.guild = guild
        self.author_id = author_id

        opts = [discord.SelectOption(label=c.name, value=str(c.id)) for c in guild.text_channels[:25]]
        if not opts:
            opts = [discord.SelectOption(label="Aucun", value="0")]

        self.add_item(discord.ui.Select(placeholder="Salon logs", options=opts, custom_id="logs", row=0))
        self.add_item(discord.ui.Select(placeholder="Bienvenue embed", options=opts, custom_id="welcome_embed", row=1))
        self.add_item(discord.ui.Select(placeholder="Bienvenue texte", options=opts, custom_id="welcome_text", row=2))
        self.add_item(discord.ui.Select(placeholder="Au revoir embed", options=opts, custom_id="leave_embed", row=3))
        self.add_item(discord.ui.Select(placeholder="Au revoir texte", options=opts, custom_id="leave_text", row=4))

    async def interaction_check(self, interaction):
        return interaction.user.id == self.author_id or interaction.user.guild_permissions.manage_guild

    async def on_interaction(self, interaction: discord.Interaction):
        try:
            cid = interaction.data.get("custom_id")
            values = interaction.data.get("values")
            if not values:
                await interaction.response.send_message("❌ Aucune sélection détectée.", ephemeral=True)
                return

            val = int(values[0])
            gid = self.guild.id

            if cid == "logs":
                set_conf(gid, "logs_channel", val)
                await interaction.response.send_message(f"✅ Salon logs défini : <#{val}>", ephemeral=True)
            elif cid == "welcome_embed":
                set_conf(gid, "welcome_embed_channel", val)
                await interaction.response.send_message(f"✅ Salon embed bienvenue défini : <#{val}>", ephemeral=True)
            elif cid == "welcome_text":
                set_conf(gid, "welcome_text_channel", val)
                await interaction.response.send_message(f"✅ Salon texte bienvenue défini : <#{val}>", ephemeral=True)
            elif cid == "leave_embed":
                set_conf(gid, "leave_embed_channel", val)
                await interaction.response.send_message(f"✅ Salon embed au revoir défini : <#{val}>", ephemeral=True)
            elif cid == "leave_text":
                set_conf(gid, "leave_text_channel", val)
                await interaction.response.send_message(f"✅ Salon texte au revoir défini : <#{val}>", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Erreur : {type(e).__name__} — {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Erreur : {type(e).__name__} — {e}", ephemeral=True)

@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config_cmd(ctx):
    conf = get_gconf(ctx.guild.id)
    e = discord.Embed(title="⚙️ Configuration Hoshikuzu", color=discord.Color.green())
    e.add_field(name="Logs", value=f"<#{conf.get('logs_channel')}>" if conf.get("logs_channel") else "Aucun", inline=True)
    e.add_field(name="Bienvenue (embed)", value=f"<#{conf.get('welcome_embed_channel')}>" if conf.get("welcome_embed_channel") else "Aucun", inline=True)
    e.add_field(name="Bienvenue (texte)", value=f"<#{conf.get('welcome_text_channel')}>" if conf.get("welcome_text_channel") else "Aucun", inline=True)
    e.add_field(name="Au revoir (embed)", value=f"<#{conf.get('leave_embed_channel')}>" if conf.get("leave_embed_channel") else "Aucun", inline=True)
    e.add_field(name="Au revoir (texte)", value=f"<#{conf.get('leave_text_channel')}>" if conf.get("leave_text_channel") else "Aucun", inline=True)
    await ctx.send(embed=e, view=ConfigView(ctx.guild, ctx.author.id))

# === Événements bienvenue / au revoir ===
@bot.event
async def on_member_join(member):
    gid = member.guild.id
    total = member.guild.member_count

    embed_id = get_conf(gid, "welcome_embed_channel")
    if embed_id:
        ch = bot.get_channel(embed_id)
        if ch:
            e = discord.Embed(title="🌿 Bienvenue !", description=f"{member.mention} a rejoint le serveur.", color=discord.Color.green())
            e.set_footer(text=f"Tu es le {total}ᵉ membre !")
            await ch.send(embed=e)

    text_id = get_conf(gid, "welcome_text_channel")
    if text_id:
        ch = bot.get_channel(text_id)
        if ch:
            await ch.send(f"{EMOJI} Bienvenue {member.mention} sur le serveur !\n{EMOJI} Tu es le **{total}ᵉ** membre !")

    role_id = get_conf(gid, "auto_role")
    if role_id:
        role = member.guild.get_role(role_id)
        if role:
            await member.add_roles(role)

@bot.event
async def on_member_remove(member):
    gid = member.guild.id
    total = member.guild.member_count

    embed_id = get_conf(gid, "leave_embed_channel")
    if embed_id:
        ch = bot.get_channel(embed_id)
        if ch:
            e = discord.Embed(title="👋 Au revoir !", description=f"{member.name} a quitté le serveur.", color=discord.Color.red())
            e.set_footer(text=f"Il reste {total} membres.")
            await ch.send(embed=e)

    text_id = get_conf(gid, "leave_text_channel")
    if text_id:
        ch = bot.get_channel(text_id)
        if ch:
            await ch.send(f"{EMOJI} {member.name} a quitté le serveur.\n{EMOJI} Il reste **{total}** membres.")

# === Commandes de test bienvenue / au revoir ===
@bot.command(name="testwelcome")
@commands.has_permissions(manage_guild=True)
async def test_welcome(ctx):
    gid = ctx.guild.id
    total = ctx.guild.member_count

    embed_id = get_conf(gid, "welcome_embed_channel")
    if embed_id:
        ch = bot.get_channel(embed_id)
        if ch:
            e = discord.Embed(title="🌿 Bienvenue (test)", description=f"{ctx.author.mention} a rejoint le serveur.", color=discord.Color.green())
            e.set_footer(text=f"Tu es le {total}ᵉ membre !")
            await ch.send(embed=e)

    text_id = get_conf(gid, "welcome_text_channel")
    if text_id:
        ch = bot.get_channel(text_id)
        if ch:
            await ch.send(f"{EMOJI} Bienvenue {ctx.author.mention} sur le serveur !\n{EMOJI} Tu es le **{total}ᵉ** membre !")

    await ctx.send("✅ Test de bienvenue envoyé.")

@bot.command(name="testleave")
@commands.has_permissions(manage_guild=True)
async def test_leave(ctx):
    gid = ctx.guild.id
    total = ctx.guild.member_count

    embed_id = get_conf(gid, "leave_embed_channel")
    if embed_id:
        ch = bot.get_channel(embed_id)
        if ch:
            e = discord.Embed(
                title="👋 Au revoir (test)",
                description=f"{ctx.author.name} a quitté le serveur.",
                color=discord.Color.red()
            )
            e.set_footer(text=f"Il reste {total} membres.")
            await ch.send(embed=e)

    text_id = get_conf(gid, "leave_text_channel")
    if text_id:
        ch = bot.get_channel(text_id)
        if ch:
            await ch.send(
                f"{EMOJI} {ctx.author.name} a quitté le serveur.\n"
                f"{EMOJI} Il reste **{total}** membres."
            )

    await ctx.send("✅ Test d’au revoir envoyé.")

# === Salon vocal temporaire ===
VOC_TRIGGER_NAME = "🔊Créer un voc"

@bot.event
async def on_voice_state_update(member, before, after):
    try:
        if after.channel and after.channel.name == VOC_TRIGGER_NAME:
            guild = member.guild
            category = after.channel.category
            temp_channel = await guild.create_voice_channel(
                name=f"🎙️ {member.name}",
                category=category,
                user_limit=1
            )
            await member.move_to(temp_channel)

        if before.channel and before.channel != after.channel:
            channel = before.channel
            if channel.name.startswith("🎙️") and len(channel.members) == 0:
                await channel.delete()
    except Exception as e:
        print(f"Erreur voc temporaire : {e}")

# === Lancement sécurisé ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN or TOKEN.strip() == "":
    print("❌ Le token Discord est vide ou non défini. Vérifie les variables d’environnement sur Render.")
    while True:
