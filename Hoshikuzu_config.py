#!/usr/bin/env python3
import os, json, threading, http.server, socketserver, asyncio, datetime
import discord
from discord.ext import commands

# === Keep Alive (Render) ===
def keep_alive():
    port = int(os.environ.get("PORT", 8080))
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    with socketserver.TCPServer(("", port), QuietHandler) as httpd:
        print(f"[keep-alive] HTTP running on port {port}")
        httpd.serve_forever()
threading.Thread(target=keep_alive, daemon=True).start()

# === Données ===
DATA_FILE = "hoshikuzu_data.json"
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"config": {}, "tickets": {}, "invites": {}, "roles_invites": {}}

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
    e.add_field(name="👥 Invitations", value=(
        "`+roleinvite <nombre> @role` - Rôle attribué à un nombre d’invitations"
    ), inline=False)
    e.add_field(name="🔗 Liens", value=(
        "`+allowlink #channel` - Autoriser les liens\n"
        "`+disallowlink #channel` - Bloquer les liens"
    ), inline=False)
    e.add_field(name="🔒 Modération", value=(
        "`+lock` - Verrouiller le salon\n"
        "`+unlock` - Déverrouiller le salon"
    ), inline=False)
    e.add_field(name="👤 Rôles", value=(
        "`+role @user @role` - Ajouter/retirer un rôle\n"
        "`+rolejoin @role` - Rôle auto à l'arrivée"
    ), inline=False)
    e.add_field(name="🎫 Tickets", value=(
        "`+ticket` - Créer un ticket\n"
        "`+ticketpanel` - Créer le panel 🎫\n"
        "`+close` - Fermer un ticket"
    ), inline=False)
    e.add_field(name="🧪 Tests", value=(
        "`+testwelcome` - Test bienvenue\n"
        "`+testleave` - Test au revoir"
    ), inline=False)
    await ctx.send(embed=e)

# === Config Commands ===
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
    await ctx.send(f"✅ Le rôle {role.name} sera attribué à **{invites} invitations**.")

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

@bot.command(name="ticketpanel")
@commands.has_permissions(manage_guild=True)
async def ticket_panel(ctx):
    embed = discord.Embed(
        title="🎫 Ouvre un Ticket",
        description="Clique sur le bouton ci-dessous pour créer un ticket d’aide !",
        color=discord.Color.green()
    )

    view = discord.ui.View()

    async def open_ticket_button_callback(interaction: discord.Interaction):
        user = interaction.user
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True)
        }

        # Mention automatique des admins/modos
        admin_roles = [r for r in ctx.guild.roles if r.permissions.manage_guild or r.permissions.administrator]
        mention_list = " ".join([r.mention for r in admin_roles]) if admin_roles else "Aucun rôle admin trouvé"

        ticket = await ctx.guild.create_text_channel(name=f"ticket-{user.name}", overwrites=overwrites)
        await ticket.send(f"{mention_list}\n🎫 Nouveau ticket ouvert par {user.mention} !")
        await interaction.response.send_message(f"✅ Ticket créé : {ticket.mention}", ephemeral=True)

    btn = discord.ui.Button(label="🎫 Ouvrir un ticket", style=discord.ButtonStyle.green)
    btn.callback = open_ticket_button_callback
    view.add_item(btn)
    await ctx.send(embed=embed, view=view)

@bot.command(name="close")
async def close(ctx):
    if ctx.channel.name.startswith("ticket-"):
        await ctx.send("🔒 Ticket fermé dans 5 secondes...")
        await asyncio.sleep(5)
        await ctx.channel.delete()
    else:
        await ctx.send("❌ Cette commande ne fonctionne que dans un ticket.")

# === Modération / Rôles ===
@bot.command(name="role")
@commands.has_permissions(manage_roles=True)
async def role(ctx, member: discord.Member, role: discord.Role):
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send(f"❌ Rôle {role.name} retiré de {member.mention}")
    else:
        await member.add_roles(role)
        await ctx.send(f"✅ Rôle {role.name} ajouté à {member.mention}")

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

# === Liens autorisés ===
@bot.command(name="allowlink")
@commands.has_permissions(manage_guild=True)
async def allowlink(ctx, channel: discord.TextChannel):
    links = get_conf(ctx.guild.id, "allow_links", [])
    if channel.id not in links:
        links.append(channel.id)
        set_conf(ctx.guild.id, "allow_links", links)
        await ctx.send(f"✅ Liens autorisés dans {channel.mention}")
    else:
        await ctx.send("ℹ️ Ce salon est déjà autorisé.")

@bot.command(name="disallowlink")
@commands.has_permissions(manage_guild=True)
async def disallowlink(ctx, channel: discord.TextChannel):
    links = get_conf(ctx.guild.id, "allow_links", [])
    if channel.id in links:
        links.remove(channel.id)
        set_conf(ctx.guild.id, "allow_links", links)
        await ctx.send(f"❌ Liens interdits dans {channel.mention}")
    else:
        await ctx.send("ℹ️ Ce salon n'était pas autorisé.")

# === Bienvenue / Leave ===
@bot.event
async def on_member_join(member):
    gid = member.guild.id
    total = member.guild.member_count
    if (ch_id := get_conf(gid, "welcome_embed_channel")):
        if ch := bot.get_channel(ch_id):
            e = discord.Embed(title="🌿 Bienvenue !", description=f"{member.mention} vient de rejoindre **{member.guild.name}** 💫", color=discord.Color.green())
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text=f"Tu es le {total}ᵉ membre !")
            await ch.send(embed=e)
    if (ch_id := get_conf(gid, "welcome_text_channel")):
        if ch := bot.get_channel(ch_id):
            await ch.send(f"{EMOJI} Bienvenue {member.mention} sur **{member.guild.name}** !\n{EMOJI} Tu es le **{total}ᵉ** membre !")

@bot.event
async def on_member_remove(member):
    gid = member.guild.id
    total = member.guild.member_count
    if (ch_id := get_conf(gid, "leave_embed_channel")):
        if ch := bot.get_channel(ch_id):
            e = discord.Embed(title="👋 Au revoir !", description=f"{member.name} a quitté le serveur.", color=discord.Color.red())
            e.set_footer(text=f"Il reste {total} membres.")
            e.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=e)
    if (ch_id := get_conf(gid, "leave_text_channel")):
        if ch := bot.get_channel(ch_id):
            await ch.send(f"{EMOJI} {member.name} a quitté le serveur. Il reste **{total}** membres.")

# === Tests ===
@bot.command(name="testwelcome")
@commands.has_permissions(manage_guild=True)
async def testwelcome(ctx):
    await on_member_join(ctx.author)
    await ctx.send("✅ Test de bienvenue envoyé.")

@bot.command(name="testleave")
@commands.has_permissions(manage_guild=True)
async def testleave(ctx):
    await on_member_remove(ctx.author)
    await ctx.send("✅ Test d'au revoir envoyé.")

# === Run ===
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN manquant !")
        exit(1)
    bot.run(token)
