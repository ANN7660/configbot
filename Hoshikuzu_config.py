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
    e.add_field(name="🎫 Tickets", value="`+ticket` - Créer un ticket\n`+close` - Fermer un ticket", inline=False)
    e.add_field(name="🧪 Tests", value="`+testwelcome` - Test bienvenue\n`+testleave` - Test au revoir", inline=False)
    e.add_field(name="🔊 Vocaux", value="`+createvoc` - Créer un salon vocal de création temporaire", inline=False)
    await ctx.send(embed=e)

# === Configuration ===
@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config_cmd(ctx):
    conf = get_gconf(ctx.guild.id)
    e = discord.Embed(title="⚙️ Configuration actuelle", color=discord.Color.green())
    for key in ["logs_channel", "welcome_embed_channel", "welcome_text_channel", "leave_embed_channel", "leave_text_channel", "invitation_channel"]:
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

@bot.command(name="roleinvite")
@commands.has_permissions(manage_roles=True)
async def roleinvite(ctx, invites: int, role: discord.Role):
    gid = str(ctx.guild.id)
    data.setdefault("roles_invites", {}).setdefault(gid, {})[str(invites)] = role.id
    save_data(data)
    await ctx.send(f"✅ Le rôle {role.name} sera attribué aux membres ayant **{invites} invitations** !")

# === Modération ===
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

# === Rôles ===
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
    await ctx.send(f"✅ Rôle automatique défini : {role.name}")

# === Tickets ===
@bot.command(name="ticket")
async def ticket(ctx):
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    channel = await ctx.guild.create_text_channel(name=f"ticket-{ctx.author.name}", overwrites=overwrites)
    await channel.send(f"{ctx.author.mention} 🎫 Ton ticket est ouvert ici.")

@bot.command(name="close")
async def close_ticket(ctx):
    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.send("❌ Cette commande fonctionne uniquement dans un ticket.")
    await ctx.send("🔒 Ce ticket sera supprimé dans 5 secondes...")
    await asyncio.sleep(5)
    await ctx.channel.delete()

# === Liens ===
@bot.command(name="allowlink")
@commands.has_permissions(manage_guild=True)
async def allowlink(ctx, channel: discord.TextChannel):
    links = get_conf(ctx.guild.id, "allow_links", [])
    if channel.id not in links:
        links.append(channel.id)
        set_conf(ctx.guild.id, "allow_links", links)
        await ctx.send(f"✅ Liens autorisés dans {channel.mention}")
    else:
        await ctx.send("ℹ️ Déjà autorisé.")

@bot.command(name="disallowlink")
@commands.has_permissions(manage_guild=True)
async def disallowlink(ctx, channel: discord.TextChannel):
    links = get_conf(ctx.guild.id, "allow_links", [])
    if channel.id in links:
        links.remove(channel.id)
        set_conf(ctx.guild.id, "allow_links", links)
        await ctx.send(f"❌ Liens désactivés dans {channel.mention}")
    else:
        await ctx.send("ℹ️ Déjà désactivé.")

# === Bienvenue / Au revoir ===
@bot.event
async def on_member_join(member):
    gid = member.guild.id
    total = member.guild.member_count

    # Embed
    if (ch_id := get_conf(gid, "welcome_embed_channel")):
        if (ch := bot.get_channel(ch_id)):
            e = discord.Embed(title="🌿 Bienvenue !", description=f"{member.mention} a rejoint **{member.guild.name}** 💫", color=discord.Color.green())
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text=f"Tu es le {total}ᵉ membre !")
            await ch.send(embed=e)

    # Texte
    if (ch_id := get_conf(gid, "welcome_text_channel")):
        if (ch := bot.get_channel(ch_id)):
            await ch.send(f"{EMOJI} Bienvenue {member.mention} sur **{member.guild.name}** !\n{EMOJI} Tu es le **{total}ᵉ** membre !")

    # Auto role
    if (role_id := get_conf(gid, "auto_role")):
        if (role := member.guild.get_role(role_id)):
            await member.add_roles(role)

@bot.event
async def on_member_remove(member):
    gid = member.guild.id
    total = member.guild.member_count

    if (ch_id := get_conf(gid, "leave_embed_channel")):
        if (ch := bot.get_channel(ch_id)):
            e = discord.Embed(title="👋 Au revoir !", description=f"{member.name} a quitté le serveur.", color=discord.Color.red())
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text=f"Il reste {total} membres.")
            await ch.send(embed=e)

    if (ch_id := get_conf(gid, "leave_text_channel")):
        if (ch := bot.get_channel(ch_id)):
            await ch.send(f"{EMOJI} {member.name} a quitté le serveur. Il reste **{total}** membres.")

# === Vocaux temporaires ===
@bot.command(name="createvoc")
@commands.has_permissions(manage_guild=True)
async def create_voc(ctx):
    category = ctx.channel.category
    ch = await ctx.guild.create_voice_channel(VOC_TRIGGER_NAME, category=category)
    await ctx.send(f"✅ Salon vocal de création automatique créé : {ch.mention}")
    data.setdefault("voc_triggers", {})[str(ctx.guild.id)] = ch.id
    save_data(data)

@bot.event
async def on_voice_state_update(member, before, after):
    try:
        if after.channel and after.channel.name == VOC_TRIGGER_NAME:
            guild = member.guild
            category = after.channel.category
            temp_channel = await guild.create_voice_channel(name=f"Voc de {member.display_name}", category=category)
            await member.move_to(temp_channel)
            data.setdefault("temp_vocs", {})[str(temp_channel.id)] = member.id
            save_data(data)

        if before.channel and before.channel.id != (after.channel.id if after.channel else None):
            if str(before.channel.id) in data.get("temp_vocs", {}) and len(before.channel.members) == 0:
                await before.channel.delete()
                del data["temp_vocs"][str(before.channel.id)]
                save_data(data)
    except Exception as e:
        print(f"Erreur voc: {e}")

# === Tests ===
@bot.command(name="testwelcome")
@commands.has_permissions(manage_guild=True)
async def testwelcome(ctx):
    await on_member_join(ctx.author)
    await ctx.send("✅ Message de bienvenue testé.")

@bot.command(name="testleave")
@commands.has_permissions(manage_guild=True)
async def testleave(ctx):
    await on_member_remove(ctx.author)
    await ctx.send("✅ Message d'au revoir testé.")

# === Run ===
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN manquant ! Configure-le sur Render.")
        exit(1)
    bot.run(token)
