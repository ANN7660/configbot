#!/usr/bin/env python3
import os, json, threading, http.server, socketserver, traceback
import discord
from discord.ext import commands

# === Keep Alive (Render) ===
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

# === Commandes ===
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🌿 Hoshikuzu — Commandes", color=discord.Color.green())
    e.add_field(name="Config", value="`+config` panneau interactif", inline=False)
    e.add_field(name="Liens", value="`+allowlink #channel` / `+disallowlink #channel`", inline=False)
    e.add_field(name="Vocale", value="`🔊Créer un voc` automatique", inline=False)
    e.add_field(name="Lock", value="`+lock` / `+unlock`", inline=False)
    e.add_field(name="Roles", value="`+role @user @role` / `+rolejoin @role`", inline=False)
    e.add_field(name="Tickets", value="`+ticket`", inline=False)
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
# === Config View ===
class ConfigView(discord.ui.View):
    def __init__(self, guild, author_id, timeout=180):
        super().__init__(timeout=timeout)
        self.guild = guild
        self.author_id = author_id

        opts = [discord.SelectOption(label=c.name, value=str(c.id)) for c in guild.text_channels[:25]]
        if not opts:
            opts = [discord.SelectOption(label="Aucun", value="0")]

        self.add_item(discord.ui.Select(placeholder="Salon logs", options=opts, custom_id="logs", row=0))
        self.add_item(discord.ui.Select(placeholder="Salon bienvenue", options=opts, custom_id="welcome", row=1))
        self.add_item(discord.ui.Select(placeholder="Salon au revoir", options=opts, custom_id="leave", row=2))
        self.add_item(discord.ui.Select(placeholder="Salon des invitations", options=opts, custom_id="invites", row=3))
        self.add_item(discord.ui.Button(label="Définir role join", style=discord.ButtonStyle.blurple, custom_id="set_rolejoin", row=4))
        self.add_item(discord.ui.Button(label="Activer allow_links", style=discord.ButtonStyle.green, custom_id="enable_links", row=4))
        self.add_item(discord.ui.Button(label="Désactiver allow_links", style=discord.ButtonStyle.gray, custom_id="disable_links", row=4))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Tu n'es pas autorisé.", ephemeral=True)
            return False
        return True

    async def on_interaction(self, interaction: discord.Interaction):
        try:
            cid = interaction.data.get("custom_id")
            val = None
            if "values" in interaction.data:
                val = int(interaction.data["values"][0])

            if cid == "logs":
                set_conf(self.guild.id, "logs_channel", val)
                await interaction.response.send_message(f"✅ Salon logs défini : <#{val}>", ephemeral=True)
            elif cid == "welcome":
                set_conf(self.guild.id, "welcome_channel", val)
                await interaction.response.send_message(f"✅ Salon bienvenue défini : <#{val}>", ephemeral=True)
            elif cid == "leave":
                set_conf(self.guild.id, "leave_channel", val)
                await interaction.response.send_message(f"✅ Salon au revoir défini : <#{val}>", ephemeral=True)
            elif cid == "invites":
                set_conf(self.guild.id, "invites_channel", val)
                await interaction.response.send_message(f"✅ Salon des invitations défini : <#{val}>", ephemeral=True)
            elif cid == "enable_links":
                set_conf(self.guild.id, "allow_links_enabled", True)
                await interaction.response.send_message("✅ allow_links activé.", ephemeral=True)
            elif cid == "disable_links":
                set_conf(self.guild.id, "allow_links_enabled", False)
                set_conf(self.guild.id, "allow_links", [])
                await interaction.response.send_message("✅ allow_links désactivé.", ephemeral=True)
            elif cid == "set_rolejoin":
                await interaction.response.send_message("ℹ️ Utilise `+rolejoin @Role` pour définir le rôle d’arrivée.", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await interaction.response.send_message(f"Erreur : {e}", ephemeral=True)

@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config_cmd(ctx):
    try:
        view = ConfigView(ctx.guild, ctx.author.id)
        conf = get_gconf(ctx.guild.id)
        e = discord.Embed(title="⚙️ Panneau de configuration — Hoshikuzu", color=discord.Color.green())
        e.add_field(name="Logs", value=f"<#{conf.get('logs_channel')}>" if conf.get("logs_channel") else "Aucun", inline=True)
        e.add_field(name="Bienvenue", value=f"<#{conf.get('welcome_channel')}>" if conf.get("welcome_channel") else "Aucun", inline=True)
        e.add_field(name="Au revoir", value=f"<#{conf.get('leave_channel')}>" if conf.get("leave_channel") else "Aucun", inline=True)
        e.add_field(name="Invites", value=f"<#{conf.get('invites_channel')}>" if conf.get("invites_channel") else "Aucun", inline=True)
        e.add_field(name="Rolejoin", value=f"<@&{conf.get('auto_role')}>" if conf.get("auto_role") else "Aucun", inline=True)
        await ctx.send(embed=e, view=view)
    except Exception as e:
        traceback.print_exc()
        await ctx.send(f"❌ Erreur : `{type(e).__name__}` — {e}")

# === Messages de bienvenue et au revoir ===
@bot.event
async def on_member_join(member):
    guild_id = member.guild.id
    channel_id = get_conf(guild_id, "welcome_channel")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            total = member.guild.member_count

            embed = discord.Embed(
                title="🌿 Bienvenue !",
                description=f"{member.mention} a rejoint le serveur.",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Tu es le {total}ᵉ membre !")
            await channel.send(embed=embed)

            await channel.send(
                f"{EMOJI} Bienvenue {member.mention} sur le serveur !\n"
                f"{EMOJI} Tu es le **{total}ᵉ** membre !"
            )

            auto_role_id = get_conf(guild_id, "auto_role")
            if auto_role_id:
                role = member.guild.get_role(auto_role_id)
                if role:
                    await member.add_roles(role)

@bot.event
async def on_member_remove(member):
    guild_id = member.guild.id
    channel_id = get_conf(guild_id, "leave_channel")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            total = member.guild.member_count
            embed = discord.Embed(
                title="👋 Au revoir !",
                description=f"{member.name} a quitté le serveur.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Il reste {total} membres.")
            await channel.send(embed=embed)

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

# === Run sécurisé pour Render ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN or TOKEN.strip() == "":
    print("❌ Le token Discord est vide ou non défini. Vérifie les variables d’environnement sur Render.")
    while True:
        pass
else:
    try:
        print("✅ Lancement du bot avec le token depuis Render.")
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Erreur lors du lancement du bot : {e}")
        while True:
            pass
