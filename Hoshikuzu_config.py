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
    return {"config": {}, "tickets": {}, "invites": {}, "roles_invites": {}, "temp_vocs": {}, "user_invites": {}, "allowed_links": {}}

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
    # Charger les invitations au démarrage
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            data["invites"][str(guild.id)] = {inv.code: inv.uses for inv in invites}
            save_data(data)
        except:
            pass

# === HELP ===
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🌿 Commandes Hoshikuzu", color=discord.Color.green())
    e.add_field(name="📊 Configuration", value=(
        "`+config` - Voir la config actuelle\n"
        "`+setwelcome #channel <embed/text>` - Salon de bienvenue\n"
        "`+setleave #channel <embed/text>` - Salon d'au revoir\n"
        "`+setlogs #channel` - Salon de logs\n"
        "`+setinvitation #channel` - Salon pour les logs d'invitations"
    ), inline=False)
    e.add_field(name="👥 Invitations", value=(
        "`+roleinvite <nombre> @role` - Rôle attribué à un nombre d'invitations\n"
        "`+invites [@user]` - Voir les invitations d'un membre"
    ), inline=False)
    e.add_field(name="🔗 Liens", value="`+allowlink #channel` - Autoriser les liens\n`+disallowlink #channel` - Bloquer les liens", inline=False)
    e.add_field(name="🔒 Modération", value="`+lock` - Verrouiller le salon\n`+unlock` - Déverrouiller le salon", inline=False)
    e.add_field(name="👤 Rôles", value="`+role @user @role` - Ajouter/retirer un rôle\n`+rolejoin @role` - Rôle auto à l'arrivée", inline=False)
    e.add_field(name="🎫 Tickets", value="`+ticket` - Créer un ticket\n`+ticketpanel` - Crée un panel de tickets\n`+close` - Fermer un ticket", inline=False)
    e.add_field(name="🧪 Tests", value="`+testwelcome` - Test bienvenue\n`+testleave` - Test au revoir", inline=False)
    e.add_field(name="🔊 Vocaux", value="`+createvoc` - Créer un salon vocal trigger\n`+setupvoc #channel` - Configurer un vocal existant comme trigger", inline=False)
    await ctx.send(embed=e)

# === Config ===
@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config_cmd(ctx):
    conf = get_gconf(ctx.guild.id)
    e = discord.Embed(title="⚙️ Configuration actuelle", color=discord.Color.green())
    for key in ["logs_channel", "welcome_embed_channel", "welcome_text_channel", "leave_embed_channel", "leave_text_channel", "invitation_channel", "ticket_panel", "voc_trigger_channel", "auto_role"]:
        val = conf.get(key)
        if "role" in key and val:
            e.add_field(name=key.replace("_", " ").title(), value=f"<@&{val}>", inline=False)
        elif val:
            e.add_field(name=key.replace("_channel", "").replace("_", " ").title(), value=f"<#{val}>", inline=False)
    
    # Afficher les rôles invitations
    roles_inv = data.get("roles_invites", {}).get(str(ctx.guild.id), {})
    if roles_inv:
        roles_text = "\n".join([f"{count} invites → <@&{role_id}>" for count, role_id in roles_inv.items()])
        e.add_field(name="🎯 Rôles par invitations", value=roles_text, inline=False)
    
    # Afficher les salons avec liens autorisés
    allowed = data.get("allowed_links", {}).get(str(ctx.guild.id), [])
    if allowed:
        links_text = "\n".join([f"<#{cid}>" for cid in allowed])
        e.add_field(name="🔗 Liens autorisés dans", value=links_text, inline=False)
    
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
    await ctx.send(f"✅ Salon des logs d'invitations défini sur {channel.mention}")

# === Link Management ===
@bot.command(name="allowlink")
@commands.has_permissions(manage_guild=True)
async def allow_link(ctx, channel: discord.TextChannel):
    """Autoriser les liens dans un salon"""
    gid = str(ctx.guild.id)
    data.setdefault("allowed_links", {}).setdefault(gid, [])
    if channel.id not in data["allowed_links"][gid]:
        data["allowed_links"][gid].append(channel.id)
        save_data(data)
        await ctx.send(f"✅ Liens autorisés dans {channel.mention}")
    else:
        await ctx.send(f"ℹ️ Les liens sont déjà autorisés dans {channel.mention}")

@bot.command(name="disallowlink")
@commands.has_permissions(manage_guild=True)
async def disallow_link(ctx, channel: discord.TextChannel):
    """Bloquer les liens dans un salon"""
    gid = str(ctx.guild.id)
    if gid in data.get("allowed_links", {}) and channel.id in data["allowed_links"][gid]:
        data["allowed_links"][gid].remove(channel.id)
        save_data(data)
        await ctx.send(f"✅ Liens bloqués dans {channel.mention}")
    else:
        await ctx.send(f"ℹ️ Les liens sont déjà bloqués dans {channel.mention}")

@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    
    # Vérifier les liens
    gid = str(message.guild.id) if message.guild else None
    if gid:
        allowed_channels = data.get("allowed_links", {}).get(gid, [])
        if message.channel.id not in allowed_channels:
            # Regex pour détecter les URLs
            url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
            if re.search(url_pattern, message.content):
                await message.delete()
                await message.channel.send(f"❌ {message.author.mention}, les liens ne sont pas autorisés ici !", delete_after=5)
                return
    
    await bot.process_commands(message)

# === Lock/Unlock ===
@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    """Verrouiller le salon actuel"""
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Salon verrouillé ! Seuls les modérateurs peuvent écrire.")

@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    """Déverrouiller le salon actuel"""
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 Salon déverrouillé ! Tout le monde peut écrire.")

# === Role Management ===
@bot.command(name="role")
@commands.has_permissions(manage_roles=True)
async def role_cmd(ctx, member: discord.Member, role: discord.Role):
    """Ajouter ou retirer un rôle à un membre"""
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send(f"➖ Rôle {role.mention} retiré à {member.mention}")
    else:
        await member.add_roles(role)
        await ctx.send(f"➕ Rôle {role.mention} ajouté à {member.mention}")

@bot.command(name="rolejoin")
@commands.has_permissions(manage_guild=True)
async def role_join(ctx, role: discord.Role):
    """Définir un rôle automatique à l'arrivée"""
    set_conf(ctx.guild.id, "auto_role", role.id)
    await ctx.send(f"✅ Les nouveaux membres recevront automatiquement le rôle {role.mention}")

# === Test Commands ===
@bot.command(name="testwelcome")
@commands.has_permissions(manage_guild=True)
async def test_welcome(ctx):
    """Tester le message de bienvenue"""
    # Test embed
    embed_channel_id = get_conf(ctx.guild.id, "welcome_embed_channel")
    if embed_channel_id:
        channel = ctx.guild.get_channel(embed_channel_id)
        if channel:
            e = discord.Embed(
                title="🎉 Bienvenue !",
                description=f"**{ctx.author.mention}** vient de rejoindre **{ctx.guild.name}** ! (TEST)",
                color=discord.Color.green()
            )
            e.set_thumbnail(url=ctx.author.display_avatar.url)
            e.set_footer(text=f"Nous sommes maintenant {ctx.guild.member_count} membres !")
            await channel.send(embed=e)
    
    # Test text
    text_channel_id = get_conf(ctx.guild.id, "welcome_text_channel")
    if text_channel_id:
        channel = ctx.guild.get_channel(text_channel_id)
        if channel:
            await channel.send(f"<a:caarrow:1433143710094196997> Bienvenue {ctx.author.mention} sur **Hoshikuzu** (TEST)\n<a:caarrow:1433143710094196997> Nous sommes maintenant **{ctx.guild.member_count}** membres sur le serveur !")
    
    if not embed_channel_id and not text_channel_id:
        await ctx.send("❌ Aucun salon de bienvenue configuré. Utilise `+setwelcome #channel <embed/text>`")
    else:
        await ctx.send("✅ Test envoyé !")

@bot.command(name="testleave")
@commands.has_permissions(manage_guild=True)
async def test_leave(ctx):
    """Tester le message d'au revoir"""
    # Test embed
    embed_channel_id = get_conf(ctx.guild.id, "leave_embed_channel")
    if embed_channel_id:
        channel = ctx.guild.get_channel(embed_channel_id)
        if channel:
            e = discord.Embed(
                title="👋 Au revoir",
                description=f"**{ctx.author.display_name}** a quitté le serveur. (TEST)",
                color=discord.Color.red()
            )
            e.set_thumbnail(url=ctx.author.display_avatar.url)
            await channel.send(embed=e)
    
    # Test text
    text_channel_id = get_conf(ctx.guild.id, "leave_text_channel")
    if text_channel_id:
        channel = ctx.guild.get_channel(text_channel_id)
        if channel:
            await channel.send(f"😢 **{ctx.author.display_name}** a quitté le serveur. (TEST)")
    
    if not embed_channel_id and not text_channel_id:
        await ctx.send("❌ Aucun salon d'au revoir configuré. Utilise `+setleave #channel <embed/text>`")
    else:
        await ctx.send("✅ Test envoyé !")

# === Invitation System ===
@bot.command(name="roleinvite")
@commands.has_permissions(manage_guild=True)
async def role_invite(ctx, nombre: int, role: discord.Role):
    """Définir un rôle à attribuer après X invitations"""
    gid = str(ctx.guild.id)
    data.setdefault("roles_invites", {}).setdefault(gid, {})[str(nombre)] = role.id
    save_data(data)
    await ctx.send(f"✅ Les membres ayant **{nombre}** invitations recevront le rôle {role.mention}")

@bot.command(name="invites")
async def invites_cmd(ctx, member: discord.Member = None):
    """Voir le nombre d'invitations d'un membre"""
    member = member or ctx.author
    gid = str(ctx.guild.id)
    invites_count = data.get("user_invites", {}).get(gid, {}).get(str(member.id), 0)
    
    e = discord.Embed(title=f"📊 Invitations de {member.display_name}", color=discord.Color.blue())
    e.add_field(name="Total", value=f"**{invites_count}** invitation(s)", inline=False)
    e.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=e)

@bot.event
async def on_member_join(member):
    guild = member.guild
    gid = str(guild.id)
    
    # Rôle automatique
    auto_role_id = get_conf(guild.id, "auto_role")
    if auto_role_id:
        role = guild.get_role(auto_role_id)
        if role:
            try:
                await member.add_roles(role)
            except:
                pass
    
    # Messages de bienvenue - Embed
    embed_channel_id = get_conf(guild.id, "welcome_embed_channel")
    if embed_channel_id:
        channel = guild.get_channel(embed_channel_id)
        if channel:
            e = discord.Embed(
                title="🎉 Bienvenue !",
                description=f"**{member.mention}** vient de rejoindre **{guild.name}** !",
                color=discord.Color.green()
            )
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text=f"Nous sommes maintenant {guild.member_count} membres !")
            await channel.send(embed=e)
    
    # Messages de bienvenue - Text
    text_channel_id = get_conf(guild.id, "welcome_text_channel")
    if text_channel_id:
        channel = guild.get_channel(text_channel_id)
        if channel:
            await channel.send(f"<a:caarrow:1433143710094196997> Bienvenue {member.mention} sur **Hoshikuzu**\n<a:caarrow:1433143710094196997> Nous sommes maintenant **{guild.member_count}** membres sur le serveur !")
    
    # Trouver qui a invité
    try:
        new_invites = {inv.code: inv.uses for inv in await guild.invites()}
        old_invites = data.get("invites", {}).get(gid, {})
        
        inviter = None
        for code, uses in new_invites.items():
            if old_invites.get(code, 0) < uses:
                inviter_inv = discord.utils.get(await guild.invites(), code=code)
                if inviter_inv and inviter_inv.inviter:
                    inviter = inviter_inv.inviter
                break
        
        # Mettre à jour les invitations
        data["invites"][gid] = new_invites
        
        # Incrémenter le compteur de l'inviteur
        if inviter:
            data.setdefault("user_invites", {}).setdefault(gid, {})
            user_id = str(inviter.id)
            data["user_invites"][gid][user_id] = data["user_invites"][gid].get(user_id, 0) + 1
            invite_count = data["user_invites"][gid][user_id]
            save_data(data)
            
            # Log d'invitation
            inv_channel_id = get_conf(guild.id, "invitation_channel")
            if inv_channel_id:
                inv_channel = guild.get_channel(inv_channel_id)
                if inv_channel:
                    e = discord.Embed(title="🎉 Nouvelle invitation", color=discord.Color.gold())
                    e.add_field(name="Nouveau membre", value=member.mention, inline=True)
                    e.add_field(name="Invité par", value=inviter.mention, inline=True)
                    e.add_field(name="Total invitations", value=f"**{invite_count}**", inline=False)
                    await inv_channel.send(embed=e)
            
            # Vérifier les rôles à attribuer
            roles_invites = data.get("roles_invites", {}).get(gid, {})
            for count_str, role_id in roles_invites.items():
                if invite_count >= int(count_str):
                    role = guild.get_role(role_id)
                    if role and role not in inviter.roles:
                        await inviter.add_roles(role)
        
        save_data(data)
    except Exception as e:
        print(f"Erreur tracking invitation: {e}")

@bot.event
async def on_member_remove(member):
    guild = member.guild
    
    # Messages d'au revoir
    # Embed
    embed_channel_id = get_conf(guild.id, "leave_embed_channel")
    if embed_channel_id:
        channel = guild.get_channel(embed_channel_id)
        if channel:
            e = discord.Embed(
                title="👋 Au revoir",
                description=f"**{member.display_name}** a quitté le serveur.",
                color=discord.Color.red()
            )
            e.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=e)
    
    # Text
    text_channel_id = get_conf(guild.id, "leave_text_channel")
    if text_channel_id:
        channel = guild.get_channel(text_channel_id)
        if channel:
            await channel.send(f"😢 **{member.display_name}** a quitté le serveur.")

@bot.event
async def on_invite_create(invite):
    """Mettre à jour le cache quand une invitation est créée"""
    gid = str(invite.guild.id)
    data.setdefault("invites", {}).setdefault(gid, {})[invite.code] = invite.uses
    save_data(data)

@bot.event
async def on_invite_delete(invite):
    """Mettre à jour le cache quand une invitation est supprimée"""
    gid = str(invite.guild.id)
    if gid in data.get("invites", {}) and invite.code in data["invites"][gid]:
        del data["invites"][gid][invite.code]
        save_data(data)

# === Vocal Temporaire ===
@bot.command(name="setupvoc")
@commands.has_permissions(manage_guild=True)
async def setup_voc(ctx, channel: discord.VoiceChannel):
    """Définir le salon vocal qui servira de trigger pour créer des vocaux temporaires"""
    set_conf(ctx.guild.id, "voc_trigger_channel", channel.id)
    await channel.edit(name=VOC_TRIGGER_NAME)
    await ctx.send(f"✅ Salon vocal trigger configuré : {channel.mention}\nLes membres qui rejoindront ce salon auront leur propre vocal temporaire.")

@bot.command(name="createvoc")
@commands.has_permissions(manage_guild=True)
async def create_voc(ctx):
    """Créer un salon vocal trigger pour les vocaux temporaires"""
    category = ctx.channel.category
    
    # Créer le salon trigger
    voc_trigger = await ctx.guild.create_voice_channel(
        name=VOC_TRIGGER_NAME,
        category=category
    )
    
    # Sauvegarder comme salon trigger
    set_conf(ctx.guild.id, "voc_trigger_channel", voc_trigger.id)
    
    await ctx.send(f"✅ Salon vocal trigger créé : {voc_trigger.mention}\n💡 Quand quelqu'un rejoint ce salon, un vocal temporaire lui sera créé automatiquement !")

@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild
    gid = str(guild.id)
    
    # Système de création automatique de vocal
    trigger_channel_id = get_conf(guild.id, "voc_trigger_channel")
    if trigger_channel_id and after.channel and after.channel.id == trigger_channel_id:
        # Créer un vocal temporaire
        category = after.channel.category
        voc = await guild.create_voice_channel(
            name=f"🔊 {member.display_name}",
            category=category
        )
        
        data.setdefault("temp_vocs", {})[str(voc.id)] = {
            "owner": member.id,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        save_data(data)
        
        await member.move_to(voc)
    
    # Supprimer les vocaux temporaires vides
    if before.channel:
        channel_id = str(before.channel.id)
        if channel_id in data.get("temp_vocs", {}):
            if len(before.channel.members) == 0:
                await before.channel.delete()
                del data["temp_vocs"][channel_id]
                save_data(data)

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
    await ctx.send(f"✅ Ticket créé : {channel.mention}", delete_after=5)

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

@bot.command(name="close")
async def close_ticket(ctx):
    """Fermer un ticket"""
    if ctx.channel.name.startswith("ticket-"):
        await ctx.send("🔒 Ce ticket sera supprimé dans 5 secondes...")
        await asyncio.sleep(5)
        await ctx.channel.delete()
    else:
        await ctx.send("❌ Cette commande ne fonctionne que dans un salon ticket.")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    panel_id = get_conf(guild.id, "ticket_panel")

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
        print("❌ ERREUR: La variable d'environnement DISCORD_TOKEN n'est pas définie!")
        print("💡 Configure-la dans les Environment Variables de Render")
        exit(1)
    
    print("🚀 Démarrage du bot Hoshikuzu...")
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ Token Discord invalide!")
    except Exception as e:
        print(f"❌ Erreur lors du démarrage: {e}")
