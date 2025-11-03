#!/usr/bin/env python3
import os, json, threading, http.server, socketserver, asyncio, datetime
import discord
from discord.ext import commands

# === Keep Alive ===
def keep_alive():
    port = int(os.environ.get("PORT", 8080))
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
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"config": {}, "tickets": {}, "invites": {}, "invite_roles": {}}

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
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.invites = True
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)
EMOJI = "<a:caarrow:1433143710094196997>"

# === READY ===
@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")
    await bot.change_presence(activity=discord.Game("Hoshikuzu | +help"))
    # Sauvegarde des invites
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            data["invites"][str(guild.id)] = {i.code: i.uses for i in invites}
        except:
            pass
    save_data(data)

# === HELP ===
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🌿 Commandes Hoshikuzu", color=discord.Color.green())
    e.add_field(name="📊 Configuration", value=(
        "`+config` - Voir la config actuelle\n"
        "`+setwelcome #channel <embed/text>` - Salon de bienvenue\n"
        "`+setleave #channel <embed/text>` - Salon d'au revoir\n"
        "`+setlogs #channel` - Salon de logs"
    ), inline=False)
    e.add_field(name="👤 Rôles", value=(
        "`+role @user @role` - Ajouter/retirer un rôle\n"
        "`+rolejoin @role` - Rôle auto à l'arrivée"
    ), inline=False)
    e.add_field(name="🎫 Tickets", value=(
        "`+ticket`, `+ticketpanel`, `+close`"
    ), inline=False)
    e.add_field(name="🔒 Modération", value="`+lock`, `+unlock`", inline=False)
    e.add_field(name="📨 Invitations", value=(
        "`+setinvitation #channel` - Salon des arrivées avec infos d'invites\n"
        "`+roleinvite <nb> @role` - Rôle à X invitations\n"
        "`+removeroleinvite <nb>` - Supprimer config\n"
        "`+listrolesinvite` - Liste des rôles d'invites"
    ), inline=False)
    e.add_field(name="🧪 Tests", value="`+testwelcome`, `+testleave`", inline=False)
    await ctx.send(embed=e)

# === CONFIG ===
@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config_cmd(ctx):
    conf = get_gconf(ctx.guild.id)
    e = discord.Embed(title="⚙️ Configuration actuelle", color=discord.Color.green())
    for key in ["logs_channel", "welcome_embed_channel", "welcome_text_channel",
                "leave_embed_channel", "leave_text_channel", "invite_log_channel"]:
        val = conf.get(key)
        e.add_field(name=key.replace("_channel", "").replace("_", " ").title(), 
                    value=f"<#{val}>" if val else "Aucun", inline=False)
    await ctx.send(embed=e)

# === SET INVITATION CHANNEL ===
@bot.command(name="setinvitation")
@commands.has_permissions(manage_guild=True)
async def set_invitation(ctx, channel: discord.TextChannel):
    set_conf(ctx.guild.id, "invite_log_channel", channel.id)
    await ctx.send(f"✅ Salon d'invitation défini : {channel.mention}")

# === ROLE INVITE COMMANDS ===
@bot.command(name="roleinvite")
@commands.has_permissions(manage_guild=True)
async def role_invite(ctx, nombre: int, role: discord.Role):
    gid = str(ctx.guild.id)
    data.setdefault("invite_roles", {}).setdefault(gid, {})[str(nombre)] = role.id
    save_data(data)
    await ctx.send(f"✅ Rôle {role.name} attribué à {nombre} invitations.")

@bot.command(name="removeroleinvite")
@commands.has_permissions(manage_guild=True)
async def remove_role_invite(ctx, nombre: int):
    gid = str(ctx.guild.id)
    roles = data.get("invite_roles", {}).get(gid, {})
    if str(nombre) in roles:
        del roles[str(nombre)]
        save_data(data)
        await ctx.send(f"❌ Configuration du rôle à {nombre} invitations supprimée.")
    else:
        await ctx.send("⚠️ Aucun rôle configuré pour ce nombre d'invitations.")

@bot.command(name="listrolesinvite")
async def list_roles_invite(ctx):
    gid = str(ctx.guild.id)
    roles = data.get("invite_roles", {}).get(gid, {})
    if not roles:
        return await ctx.send("ℹ️ Aucun rôle d'invitation configuré.")
    desc = "\n".join([f"{nombre} invites → <@&{rid}>" for nombre, rid in roles.items()])
    e = discord.Embed(title="🎁 Rôles d'invitations", description=desc, color=discord.Color.green())
    await ctx.send(embed=e)

# === INVITE TRACKING ===
@bot.event
async def on_member_join(member):
    gid = str(member.guild.id)
    invites_before = data["invites"].get(gid, {})
    invites_after = {i.code: i.uses for i in await member.guild.invites()}
    data["invites"][gid] = invites_after
    save_data(data)

    inviter = None
    for code, uses in invites_after.items():
        if code in invites_before and uses > invites_before[code]:
            try:
                invite_obj = await member.guild.fetch_invite(code)
                inviter = invite_obj.inviter
            except:
                pass
            break

    inviter_name = inviter.mention if inviter else "inconnu"
    invite_log = get_conf(member.guild.id, "invite_log_channel")

    if invite_log:
        ch = bot.get_channel(invite_log)
        if ch:
            msg = f"🎉 {member.mention} a rejoint — invité par **{inviter_name}**."
            await ch.send(msg)

    # Compter les invites
    if inviter:
        guild_invites = data.setdefault("invites_count", {}).setdefault(str(member.guild.id), {})
        user_invites = guild_invites.setdefault(str(inviter.id), 0) + 1
        guild_invites[str(inviter.id)] = user_invites
        save_data(data)

        # Vérifier les rôles
        invite_roles = data.get("invite_roles", {}).get(str(member.guild.id), {})
        for nbr, role_id in invite_roles.items():
            if user_invites >= int(nbr):
                role = member.guild.get_role(role_id)
                if role and role not in inviter.roles:
                    try:
                        await inviter.add_roles(role)
                        await ch.send(f"🏅 {inviter.mention} a reçu le rôle {role.mention} pour avoir atteint {nbr} invitations !")
                    except:
                        pass

# === BOT TOKEN ===
if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN manquant ! Configure-le dans les variables Render.")
        exit(1)
    bot.run(token)
