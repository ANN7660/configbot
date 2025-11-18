#!/usr/bin/env python3
import os, json, threading, http.server, socketserver, asyncio, datetime, re
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
    return {"config": {}, "tickets": {}, "invites": {}, "roles_invites": {}, "temp_vocs": {}, "user_invites": {}, "allowed_links": {}, "reaction_roles": {}}

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

# === Fonction d'envoi de logs ===
async def send_log(guild, embed_or_file):
    logs_channel_id = get_conf(guild.id, "logs_channel")
    if logs_channel_id:
        channel = guild.get_channel(logs_channel_id)
        if channel:
            try:
                if isinstance(embed_or_file, discord.Embed):
                    await channel.send(embed=embed_or_file)
                else:
                    await channel.send(file=embed_or_file)
            except Exception as e:
                print(f"Erreur envoi log: {e}")

# === BOT READY ===
@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")
    await bot.change_presence(activity=discord.Game(name="hoshikuzu | +help"))
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            data["invites"][str(guild.id)] = {inv.code: inv.uses for inv in invites}
            save_data(data)
        except Exception:
            pass

# === HELP ===
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🌿 Commandes Hoshikuzu", color=discord.Color.green())
    e.add_field(name="📊 Configuration", value=(
        "`+config` - Voir la config actuelle\n"
        "`+setwelcome #channel <embed/text>`\n"
        "`+setleave #channel <embed/text>`\n"
        "`+setlogs #channel`\n"
        "`+setinvitation #channel`"
    ), inline=False)
    e.add_field(name="👥 Invitations", value=(
        "`+roleinvite <nombre> @role`\n"
        "`+invites [@user]`"
    ), inline=False)
    e.add_field(name="🔗 Liens", value="`+allowlink #channel`\n`+disallowlink #channel`", inline=False)
    e.add_field(name="🔒 Modération", value="`+lock`\n`+unlock`", inline=False)
    e.add_field(name="👤 Rôles", value="`+role @user @role`\n`+rolejoin @role`", inline=False)
    e.add_field(name="🎫 Tickets", value="`+ticket`\n`+ticketpanel`\n`+close`", inline=False)
    e.add_field(name="🎭 Rôles Réactions", value="`+reactionrole #channel <message_id> <emoji> @role`\n`+listreactionroles`", inline=False)
    e.add_field(name="💬 Utilitaires", value="`+say <message>`", inline=False)
    e.add_field(name="🧪 Tests", value="`+testwelcome`\n`+testleave`", inline=False)
    e.add_field(name="🔊 Vocaux", value="`+createvoc`\n`+setupvoc #channel`", inline=False)
    await ctx.send(embed=e)

# === CONFIG COMMANDS ===
@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config_cmd(ctx):
    conf = get_gconf(ctx.guild.id)
    e = discord.Embed(title="⚙️ Configuration actuelle", color=discord.Color.green())
    for key in ["logs_channel", "welcome_embed_channel", "welcome_text_channel", "leave_embed_channel",
                "leave_text_channel", "invitation_channel", "ticket_panel", "voc_trigger_channel", "auto_role"]:
        val = conf.get(key)
        if val:
            if "role" in key:
                e.add_field(name=key.replace("_", " ").title(), value=f"<@&{val}>", inline=False)
            else:
                e.add_field(name=key.replace("_channel", "").replace("_", " ").title(), value=f"<#{val}>", inline=False)

    # Rôles par invitations
    roles_inv = data.get("roles_invites", {}).get(str(ctx.guild.id), {})
    if roles_inv:
        roles_text = "\n".join([f"{count} invites → <@&{role_id}>" for count, role_id in roles_inv.items()])
        e.add_field(name="🎯 Rôles par invitations", value=roles_text, inline=False)

    # Salons liens autorisés
    allowed = data.get("allowed_links", {}).get(str(ctx.guild.id), [])
    if allowed:
        links_text = "\n".join([f"<#{cid}>" for cid in allowed])
        e.add_field(name="🔗 Liens autorisés dans", value=links_text, inline=False)

    await ctx.send(embed=e)

# === SET COMMANDS ===
# setwelcome, setleave, setlogs, setinvitation, allowlink, disallowlink...

# === MESSAGE EVENT ===
# on_message: suppression des liens non autorisés + process_commands

# === LOCK/UNLOCK ===
# lock, unlock

# === ROLE MANAGEMENT ===
# role_cmd, role_join

# === SAY COMMAND ===
# say

# === REACTION ROLES ===
# reaction_role, list_reaction_roles, on_raw_reaction_add, on_raw_reaction_remove

# === TICKET SYSTEM ===
# TicketView, CloseButton, ticketpanel, ticket, close_ticket

# === VOC TEMPORAIRE ===
# setupvoc, createvoc, on_voice_state_update

# === MEMBER EVENTS ===
# on_member_join, on_member_remove

# === LOGS EVENTS ===
# message_edit, message_delete, member_update, guild_channel_create/delete/update, member_ban/unban, guild_update, guild_role_create/delete

# === INVITES EVENTS ===
# on_invite_create, on_invite_delete

# === RUN ===
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERREUR: La variable d'environnement DISCORD_TOKEN n'est pas définie!")
        exit(1)
    print("🚀 Démarrage du bot Hoshikuzu...")
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ Token Discord invalide!")
    except Exception as e:
        print(f"❌ Erreur lors du démarrage: {e}")
