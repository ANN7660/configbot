#!/usr/bin/env python3
import os, json, threading, http.server, socketserver, asyncio, datetime
import discord
from discord.ext import commands
from discord.ui import View, Button

# === Keep Alive ===
def keep_alive():
    port = int(os.environ.get("PORT", 8080))
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    with socketserver.TCPServer(("", port), QuietHandler) as httpd:
        print(f"[keep-alive] HTTP running on port {port}")
        httpd.serve_forever()
threading.Thread(target=keep_alive, daemon=True).start()

# === Data ===
DATA_FILE = "hoshikuzu_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"config": {}, "tickets": {}, "invites": {}, "roles_invites": {}, "temp_vocs": {}}

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

data = load_data()

def get_conf(gid, key, default=None):
    return data.get("config", {}).get(str(gid), {}).get(key, default)

def set_conf(gid, key, value):
    data.setdefault("config", {}).setdefault(str(gid), {})[key] = value
    save_data(data)

def get_gconf(gid):
    return data.get("config", {}).get(str(gid), {})

# === Bot Init ===
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)
EMOJI = "<a:caarrow:1433143710094196997>"
VOC_TRIGGER_NAME = "🔊Créer un voc"

@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")
    await bot.change_presence(activity=discord.Game(name="hoshikuzu | +help"))

# === HELP ===
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🌿 Commandes Hoshikuzu", color=discord.Color.green())
    e.add_field(name="📊 Configuration", value=(
        "`+config` - Voir la config actuelle\n"
        "`+setwelcome #channel <embed/text>` - Salon de bienvenue\n"
        "`+setleave #channel <embed/text>` - Salon d'au revoir\n"
        "`+setlogs #channel` - Salon de logs\n"
        "`+setinvitation #channel` - Salon pour les logs d’invitations"
    ), inline=False)
    e.add_field(name="👥 Invitations", value="`+roleinvite <nombre> @role` - Rôle attribué à un nombre d’invitations", inline=False)
    e.add_field(name="🔗 Liens", value="`+allowlink #channel` - Autoriser les liens\n`+disallowlink #channel` - Bloquer les liens", inline=False)
    e.add_field(name="🔒 Modération", value="`+lock` - Verrouiller le salon\n`+unlock` - Déverrouiller le salon", inline=False)
    e.add_field(name="👤 Rôles", value="`+role @user @role` - Ajouter/retirer un rôle\n`+rolejoin @role` - Rôle auto à l'arrivée", inline=False)
    e.add_field(name="🎫 Tickets", value="`+ticket` - Créer un ticket\n`+ticketpanel` - Crée un panel de tickets\n`+close` - Fermer un ticket", inline=False)
    e.add_field(name="🧪 Tests", value="`+testwelcome` - Test bienvenue\n`+testleave` - Test au revoir", inline=False)
    e.add_field(name="🔊 Vocaux", value="`+createvoc` - Créer un salon vocal temporaire", inline=False)
    await ctx.send(embed=e)

# === Config ===
@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config_cmd(ctx):
    conf = get_gconf(ctx.guild.id)
    e = discord.Embed(title="⚙️ Configuration actuelle", color=discord.Color.green())
    for key in ["logs_channel", "welcome_embed_channel", "welcome_text_channel", "leave_embed_channel", "leave_text_channel", "invitation_channel", "ticket_panel"]:
        val = conf.get(key)
        e.add_field(name=key.replace("_channel", "").replace("_", " ").title(), value=f"<#{val}>" if val else "Aucun", inline=False)
    await ctx.send(embed=e)

# === Set Commands ===
@bot.command(name="setwelcome")
@commands.has_permissions(manage_guild=True)
async def set_welcome(ctx, channel: discord.TextChannel, type: str = "embed"):
    if type.lower() == "embed":
        set_conf(ctx.guild.id, "welcome_embed_channel", channel.id)
        await ctx.send(f"✅ Messages de bienvenue (embed) dans {channel.mention}")
    elif type.lower() == "text":
        set_conf(ctx.guild.id, "welcome_text_channel", channel.id)
        await ctx.send(f"✅ Messages de bienvenue (texte) dans {channel.mention}")
    else:
        await ctx.send("❌ Type invalide (embed/text)")

@bot.command(name="setleave")
@commands.has_permissions(manage_guild=True)
async def set_leave(ctx, channel: discord.TextChannel, type: str = "embed"):
    if type.lower() == "embed":
        set_conf(ctx.guild.id, "leave_embed_channel", channel.id)
        await ctx.send(f"✅ Messages d'au revoir (embed) dans {channel.mention}")
    elif type.lower() == "text":
        set_conf(ctx.guild.id, "leave_text_channel", channel.id)
        await ctx.send(f"✅ Messages d'au revoir (texte) dans {channel.mention}")
    else:
        await ctx.send("❌ Type invalide (embed/text)")

@bot.command(name="setlogs")
@commands.has_permissions(manage_guild=True)
async def set_logs(ctx, channel: discord.TextChannel):
    set_conf(ctx.guild.id, "logs_channel", channel.id)
    await ctx.send(f"✅ Salon de logs défini : {channel.mention}")

@bot.command(name="setinvitation")
@commands.has_permissions(manage_guild=True)
async def set_invitation(ctx, channel: discord.TextChannel):
    set_conf(ctx.guild.id, "invitation_channel", channel.id)
    await ctx.send(f"✅ Salon des logs d’invitations défini sur {channel.mention}")

# === Ticket System ===
class CloseButton(Button):
    def __init__(self):
        super().__init__(label="Fermer le ticket", style=discord.ButtonStyle.red, emoji="🔒")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔒 Ce ticket sera supprimé dans 5 secondes...", ephemeral=True)
        await asyncio.sleep(5)
        await interaction.channel.delete()

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseButton())

@bot.command(name="ticket")
async def ticket(ctx):
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    channel = await ctx.guild.create_text_channel(name=f"ticket-{ctx.author.name}", overwrites=overwrites)
    embed = discord.Embed(title="🎫 Ticket ouvert", description=f"{ctx.author.mention}, explique ton problème ici.", color=discord.Color.green())
    await channel.send(embed=embed, view=TicketView())

@bot.command(name="ticketpanel")
@commands.has_permissions(manage_guild=True)
async def ticket_panel(ctx):
    """Crée un panel avec réaction 🎫 pour ouvrir un ticket"""
    embed = discord.Embed(
        title="🎫 Ouvre un ticket !",
        description="Besoin d'aide ? Clique sur 🎫 pour créer un ticket privé !",
        color=discord.Color.green()
    )
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎫")
    set_conf(ctx.guild.id, "ticket_panel", msg.id)
    set_conf(ctx.guild.id, "ticket_panel_channel", ctx.channel.id)
    await ctx.send("✅ Panel de tickets créé avec succès !")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    panel_id = get_conf(guild.id, "ticket_panel")
    panel_channel_id = get_conf(guild.id, "ticket_panel_channel")

    if panel_id and payload.message_id == panel_id and str(payload.emoji) == "🎫":
        member = guild.get_member(payload.user_id)
        if not member:
            return

        existing = discord.utils.get(guild.text_channels, name=f"ticket-{member.name}")
        if existing:
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }

        ticket_channel = await guild.create_text_channel(f"ticket-{member.name}", overwrites=overwrites)
        embed = discord.Embed(title="🎫 Ticket créé !", description=f"{member.mention}, explique ton problème ici.", color=discord.Color.green())
        await ticket_channel.send(embed=embed, view=TicketView())

# === Run ===
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN manquant ! Configure-le sur Render.")
        exit(1)
    bot.run(token)
