#!/usr/bin/env python3
import os, json, threading, http.server, socketserver, asyncio, datetime, re
import discord
from discord.ext import commands
from discord.ui import View, Button

# ==================== KEEP ALIVE ====================
def keep_alive():
    port = int(os.environ.get("PORT", 8080))
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    with socketserver.TCPServer(("", port), QuietHandler) as httpd:
        print(f"[keep-alive] HTTP running on port {port}")
        httpd.serve_forever()
threading.Thread(target=keep_alive, daemon=True).start()

# ==================== DATA ====================
DATA_FILE = "hoshikuzu_data.json"
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"config": {}, "tickets": {}, "temp_vocs": {}, "allowed_links": {}, "reaction_roles": {}, "invites": {}}

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

# ==================== BOT INIT ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)
EMOJI = "<a:caarrow:1433143710094196997>"
VOC_TRIGGER_NAME = "🔊Créer un voc"

# ==================== LOG HELPER ====================
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

# ==================== READY ====================
@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")
    await bot.change_presence(activity=discord.Game(name="hoshikuzu | +help"))

# ==================== HELP ====================
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🌿 Commandes Hoshikuzu", color=discord.Color.green())
    e.add_field(name="📊 Configuration",
                value="+config\n+setwelcome #channel embed/text\n+setleave #channel embed/text\n+setjoinrole @role\n+setlogs #channel", inline=False)
    e.add_field(name="👥 Invitations",
                value="+roleinvite <nombre> @role\n+invites [@user]", inline=False)
    e.add_field(name="🔗 Liens",
                value="+allowlink #channel / +disallowlink #channel", inline=False)
    e.add_field(name="🔒 Modération",
                value="+lock / +unlock / +ban @user <raison> / +unban <id> / +mute @user <minutes> <raison> / +unmute @user", inline=False)
    e.add_field(name="👤 Rôles",
                value="+role @user @role / +rolejoin @role", inline=False)
    e.add_field(name="🎫 Tickets",
                value="+ticket / +ticketpanel / +close / +ticketrole @role", inline=False)
    e.add_field(name="🎭 Rôles Réactions",
                value="+reactionrole #channel emoji @role", inline=False)
    e.add_field(name="💬 Utilitaires",
                value="+say <message>", inline=False)
    e.add_field(name="🔊 Vocaux",
                value="+createvoc / +setupvoc #salon", inline=False)
    await ctx.send(embed=e)

# ==================== CONFIG ====================
@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config(ctx):
    conf = get_gconf(ctx.guild.id)
    e = discord.Embed(title="⚙️ Configuration du serveur", color=discord.Color.blue())
    
    # Bienvenue
    welcome_embed = conf.get("welcome_embed_channel")
    welcome_text = conf.get("welcome_text_channel")
    if welcome_embed:
        e.add_field(name="Bienvenue (Embed)", value=f"<#{welcome_embed}>", inline=False)
    if welcome_text:
        e.add_field(name="Bienvenue (Texte)", value=f"<#{welcome_text}>", inline=False)
    
    # Départ
    leave_embed = conf.get("leave_embed_channel")
    leave_text = conf.get("leave_text_channel")
    if leave_embed:
        e.add_field(name="Départ (Embed)", value=f"<#{leave_embed}>", inline=False)
    if leave_text:
        e.add_field(name="Départ (Texte)", value=f"<#{leave_text}>", inline=False)
    
    # Rôle auto
    role_join = conf.get("role_join")
    if role_join:
        e.add_field(name="Rôle automatique", value=f"<@&{role_join}>", inline=False)
    
    # Logs
    logs_channel = conf.get("logs_channel")
    if logs_channel:
        e.add_field(name="Salon logs", value=f"<#{logs_channel}>", inline=False)
    
    # Vocaux
    voc_trigger = conf.get("voc_trigger_channel")
    if voc_trigger:
        e.add_field(name="Salon vocal trigger", value=f"<#{voc_trigger}>", inline=False)
    
    # Tickets
    ticket_roles = conf.get("ticket_roles", [])
    if ticket_roles:
        roles_mentions = ", ".join([f"<@&{r}>" for r in ticket_roles])
        e.add_field(name="Rôles tickets", value=roles_mentions, inline=False)
    
    if not conf:
        e.description = "Aucune configuration définie pour le moment."
    
    await ctx.send(embed=e)

# ==================== SETWELCOME ====================
@bot.command(name="setwelcome")
@commands.has_permissions(manage_guild=True)
async def setwelcome(ctx, channel: discord.TextChannel = None, mode: str = None):
    if not channel or not mode or mode.lower() not in ["embed", "text"]:
        return await ctx.send("❌ Usage : `+setwelcome #channel embed/text`")
    
    if mode.lower() == "embed":
        set_conf(ctx.guild.id, "welcome_embed_channel", channel.id)
        await ctx.send(f"✅ Messages de bienvenue (embed) configurés dans {channel.mention}")
    else:
        set_conf(ctx.guild.id, "welcome_text_channel", channel.id)
        await ctx.send(f"✅ Messages de bienvenue (texte) configurés dans {channel.mention}")

# ==================== SETLEAVE ====================
@bot.command(name="setleave")
@commands.has_permissions(manage_guild=True)
async def setleave(ctx, channel: discord.TextChannel = None, mode: str = None):
    if not channel or not mode or mode.lower() not in ["embed", "text"]:
        return await ctx.send("❌ Usage : `+setleave #channel embed/text`")
    
    if mode.lower() == "embed":
        set_conf(ctx.guild.id, "leave_embed_channel", channel.id)
        await ctx.send(f"✅ Messages de départ (embed) configurés dans {channel.mention}")
    else:
        set_conf(ctx.guild.id, "leave_text_channel", channel.id)
        await ctx.send(f"✅ Messages de départ (texte) configurés dans {channel.mention}")

# ==================== SETJOINROLE ====================
@bot.command(name="setjoinrole")
@commands.has_permissions(manage_guild=True)
async def setjoinrole(ctx, role: discord.Role = None):
    if not role:
        return await ctx.send("❌ Usage : `+setjoinrole @role`")
    set_conf(ctx.guild.id, "role_join", role.id)
    await ctx.send(f"✅ Rôle {role.mention} sera attribué automatiquement aux nouveaux membres.")

# ==================== SETLOGS ====================
@bot.command(name="setlogs")
@commands.has_permissions(manage_guild=True)
async def setlogs(ctx, channel: discord.TextChannel = None):
    if not channel:
        return await ctx.send("❌ Usage : `+setlogs #channel`")
    set_conf(ctx.guild.id, "logs_channel", channel.id)
    await ctx.send(f"✅ Salon de logs configuré : {channel.mention}")

# ==================== WELCOME / LEAVE / ROLE JOIN ====================
async def send_welcome(member):
    conf = get_gconf(member.guild.id)
    total = member.guild.member_count
    role_join_id = conf.get("role_join")
    if role_join_id:
        role = member.guild.get_role(role_join_id)
        if role: 
            try:
                await member.add_roles(role)
            except:
                pass
    embed_ch = conf.get("welcome_embed_channel")
    text_ch = conf.get("welcome_text_channel")
    if embed_ch:
        ch = member.guild.get_channel(embed_ch)
        if ch:
            e = discord.Embed(title="✨ Bienvenue sur **Hoshikuzu** !",
                              description=f"{member.mention} vient de rejoindre ✨",
                              color=discord.Color.green(),
                              timestamp=datetime.datetime.now(datetime.timezone.utc))
            e.add_field(name="Infos",
                        value=f"{EMOJI} **BVN {member.mention} sur Hoshikuzu !**\n{EMOJI} Nous sommes maintenant **{total} membres**.")
            e.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=e)
    if text_ch:
        ch = member.guild.get_channel(text_ch)
        if ch:
            await ch.send(f"{EMOJI} **BVN {member.mention} sur Hoshikuzu !**\n{EMOJI} Nous sommes maintenant **{total} membres**.")

async def send_leave(member):
    conf = get_gconf(member.guild.id)
    total = member.guild.member_count
    embed_ch = conf.get("leave_embed_channel")
    text_ch = conf.get("leave_text_channel")
    if embed_ch:
        ch = member.guild.get_channel(embed_ch)
        if ch:
            e = discord.Embed(title="❌ Un membre nous quitte...",
                              description=f"{member.mention} vient de partir.",
                              color=discord.Color.red(),
                              timestamp=datetime.datetime.now(datetime.timezone.utc))
            e.add_field(name="Infos",
                        value=f"{EMOJI} {member.mention} a quitté Hoshikuzu...\n{EMOJI} Il reste maintenant **{total} membres**.")
            e.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=e)
    if text_ch:
        ch = member.guild.get_channel(text_ch)
        await ch.send(f"{EMOJI} {member.mention} a quitté Hoshikuzu...\n{EMOJI} Il reste maintenant **{total} membres**.")

@bot.event
async def on_member_join(member): 
    await send_welcome(member)
    # Système d'invitations
    try:
        invites_before = data.get("invites", {}).get(str(member.guild.id), {})
        invites_after = {inv.code: inv.uses for inv in await member.guild.invites()}
        
        for code, uses in invites_after.items():
            if code in invites_before and uses > invites_before[code]:
                # Trouver l'inviteur
                for inv in await member.guild.invites():
                    if inv.code == code:
                        inviter_id = str(inv.inviter.id)
                        data.setdefault("invites", {}).setdefault(str(member.guild.id), {}).setdefault(inviter_id, {"count": 0, "members": []})
                        data["invites"][str(member.guild.id)][inviter_id]["count"] += 1
                        data["invites"][str(member.guild.id)][inviter_id]["members"].append(member.id)
                        save_data(data)
                        break
        
        # Sauvegarder les invitations actuelles
        data.setdefault("invites", {})[str(member.guild.id)] = invites_after
        save_data(data)
    except:
        pass

@bot.event
async def on_member_remove(member): 
    await send_leave(member)

# ==================== INVITES ====================
@bot.command(name="invites")
async def invites(ctx, member: discord.Member = None):
    member = member or ctx.author
    gid = str(ctx.guild.id)
    invites_data = data.get("invites", {}).get(gid, {}).get(str(member.id), {"count": 0, "members": []})
    
    count = invites_data.get("count", 0)
    e = discord.Embed(title=f"📊 Invitations de {member.display_name}", color=discord.Color.blue())
    e.add_field(name="Total", value=f"**{count}** invitation(s)")
    e.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=e)

# ==================== ROLEINVITE ====================
@bot.command(name="roleinvite")
@commands.has_permissions(manage_guild=True)
async def roleinvite(ctx, count: int = None, role: discord.Role = None):
    if not count or not role:
        return await ctx.send("❌ Usage : `+roleinvite <nombre> @role`")
    
    gid = str(ctx.guild.id)
    data.setdefault("config", {}).setdefault(gid, {}).setdefault("role_invites", {})[str(role.id)] = count
    save_data(data)
    await ctx.send(f"✅ Le rôle {role.mention} sera donné après **{count}** invitations.")

# ==================== MODÉRATION ====================
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member = None, *, reason="Aucune raison"):
    if not member: return await ctx.send("❌ Usage : `+ban @user <raison>`")
    if member.id == ctx.author.id or member.id == ctx.guild.me.id: return await ctx.send("❌ Action impossible.")
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner: return await ctx.send("❌ Tu ne peux pas bannir un rôle supérieur.")
    if member.guild_permissions.administrator: return await ctx.send("❌ Impossible de bannir un administrateur.")
    await member.ban(reason=f"Banni par {ctx.author} | {reason}")
    embed = discord.Embed(title="🔨 Membre banni", color=discord.Color.red(), timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="👤 Membre", value=f"{member} (`{member.id}`)")
    embed.add_field(name="🛠️ Staff", value=ctx.author.mention)
    embed.add_field(name="📄 Raison", value=reason)
    await ctx.send(embed=embed)
    await send_log(ctx.guild, embed)

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int = None):
    if not user_id: return await ctx.send("❌ Usage : `+unban <id_utilisateur>`")
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    embed = discord.Embed(title="♻️ Unban", color=discord.Color.green(), timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="Utilisateur", value=user.mention)
    embed.add_field(name="Par", value=ctx.author.mention)
    await ctx.send(f"♻️ {user.mention} a été débanni.")
    await send_log(ctx.guild, embed)

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member = None, duration: int = None, *, reason="Aucune raison"):
    if not member or not duration: return await ctx.send("❌ Usage : `+mute @user <minutes> <raison>`")
    try: 
        await member.timeout(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=duration), reason=reason)
    except: 
        return await ctx.send("❌ Impossible de timeout cet utilisateur.")
    embed = discord.Embed(title="🔇 Mute", color=discord.Color.orange(), timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="Utilisateur", value=member.mention)
    embed.add_field(name="Durée", value=f"{duration} minutes")
    embed.add_field(name="Raison", value=reason)
    embed.add_field(name="Par", value=ctx.author.mention)
    await ctx.send(f"🔇 {member.mention} a été mute pendant **{duration} minutes**.")
    await send_log(ctx.guild, embed)

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member = None, *, reason="Aucune raison"):
    if not member: return await ctx.send("❌ Usage : `+unmute @user`")
    try: await member.timeout(None, reason=reason)
    except: return await ctx.send("❌ Impossible d'unmute cet utilisateur.")
    embed = discord.Embed(title="🔊 Unmute", color=discord.Color.green(), timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="Utilisateur", value=member.mention)
    embed.add_field(name="Raison", value=reason)
    embed.add_field(name="Par", value=ctx.author.mention)
    await ctx.send(f"🔊 {member.mention} a été unmute.")
    await send_log(ctx.guild, embed)

# ==================== ROLE ====================
@bot.command(name="role")
@commands.has_permissions(manage_roles=True)
async def role(ctx, member: discord.Member = None, role: discord.Role = None):
    if not member or not role:
        return await ctx.send("❌ Usage : `+role @user @role`")
    
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send(f"❌ Rôle {role.mention} retiré de {member.mention}")
    else:
        await member.add_roles(role)
        await ctx.send(f"✅ Rôle {role.mention} ajouté à {member.mention}")

# ==================== ROLE JOIN ====================
@bot.command(name="rolejoin")
@commands.has_permissions(manage_guild=True)
async def rolejoin(ctx, role: discord.Role = None):
    if not role: return await ctx.send("❌ Usage : `+rolejoin @role`")
    set_conf(ctx.guild.id, "role_join", role.id)
    await ctx.send(f"✅ Rôle {role.mention} sera attribué à chaque nouvel arrivant.")

# ==================== TICKETS ====================
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
    overwrites = {ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                  ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                  ctx.guild.me: discord.PermissionOverwrite(read_messages=True)}
    channel = await ctx.guild.create_text_channel(name=f"ticket-{ctx.author.name}", overwrites=overwrites)
    ticket_roles = get_conf(ctx.guild.id, "ticket_roles") or []
    for role_id in ticket_roles:
        role = ctx.guild.get_role(role_id)
        if role: await channel.set_permissions(role, read_messages=True, send_messages=True)
    embed = discord.Embed(title="🎫 Ticket ouvert",
                          description=f"{ctx.author.mention}, explique ton problème ici.",
                          color=discord.Color.green())
    await channel.send(embed=embed, view=TicketView())
    await ctx.send(f"✅ Ticket créé : {channel.mention}", delete_after=5)

# ==================== TICKETROLE ====================
@bot.command(name="ticketrole")
@commands.has_permissions(manage_guild=True)
async def ticketrole(ctx, role: discord.Role = None):
    if not role:
        return await ctx.send("❌ Usage : `+ticketrole @role`")
    
    ticket_roles = get_conf(ctx.guild.id, "ticket_roles") or []
    if role.id in ticket_roles:
        ticket_roles.remove(role.id)
        set_conf(ctx.guild.id, "ticket_roles", ticket_roles)
        await ctx.send(f"❌ Rôle {role.mention} retiré des rôles de support ticket.")
    else:
        ticket_roles.append(role.id)
        set_conf(ctx.guild.id, "ticket_roles", ticket_roles)
        await ctx.send(f"✅ Rôle {role.mention} ajouté aux rôles de support ticket.")

# ==================== CLOSE ====================
@bot.command(name="close")
async def close(ctx):
    if "ticket-" not in ctx.channel.name:
        return await ctx.send("❌ Cette commande ne fonctionne que dans un ticket.")
    
    await ctx.send("🔒 Ce ticket sera supprimé dans 5 secondes...")
    await asyncio.sleep(5)
    await ctx.channel.delete()

# ==================== TICKETPANEL ====================
class CreateTicketButton(Button):
    def __init__(self):
        super().__init__(label="Créer un ticket", style=discord.ButtonStyle.green, emoji="🎫")
    
    async def callback(self, interaction: discord.Interaction):
        # Vérifier si l'utilisateur a déjà un ticket ouvert
        for channel in interaction.guild.text_channels:
            if f"ticket-{interaction.user.name}" == channel.name:
                return await interaction.response.send_message("❌ Tu as déjà un ticket ouvert !", ephemeral=True)
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}", 
            overwrites=overwrites
        )
        
        ticket_roles = get_conf(interaction.guild.id, "ticket_roles") or []
        for role_id in ticket_roles:
            role = interaction.guild.get_role(role_id)
            if role: 
                await channel.set_permissions(role, read_messages=True, send_messages=True)
        
        embed = discord.Embed(
            title="🎫 Ticket ouvert",
            description=f"{interaction.user.mention}, explique ton problème ici.\nUn membre du staff va te répondre.",
            color=discord.Color.green()
        )
        await channel.send(embed=embed, view=TicketView())
        await interaction.response.send_message(f"✅ Ticket créé : {channel.mention}", ephemeral=True)

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CreateTicketButton())

@bot.command(name="ticketpanel")
@commands.has_permissions(manage_guild=True)
async def ticketpanel(ctx):
    embed = discord.Embed(
        title="🎫 Système de Tickets",
        description="Clique sur le bouton ci-dessous pour créer un ticket.\nUn membre du staff te répondra dès que possible.",
        color=discord.Color.blue()
    )
    embed.add_field(name="📌 Rappel", value="N'ouvre un ticket que si tu as vraiment besoin d'aide !")
    await ctx.send(embed=embed, view=TicketPanelView())

# ==================== VOC TEMPORAIRES ====================
@bot.command(name="setupvoc")
@commands.has_permissions(manage_guild=True)
async def setup_voc(ctx, channel: discord.VoiceChannel = None):
    if not channel: return await ctx.send("❌ Usage : `+setupvoc #salon`")
    set_conf(ctx.guild.id, "voc_trigger_channel", channel.id)
    await channel.edit(name=VOC_TRIGGER_NAME)
    await ctx.send(f"✅ Salon vocal trigger configuré : {channel.mention}")

@bot.command(name="createvoc")
@commands.has_permissions(manage_guild=True)
async def create_voc(ctx):
    category = ctx.channel.category
    voc_trigger = await ctx.guild.create_voice_channel(name=VOC_TRIGGER_NAME, category=category)
    set_conf(ctx.guild.id, "voc_trigger_channel", voc_trigger.id)
    await ctx.send(f"✅ Salon vocal trigger créé : {voc_trigger.mention}")

@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild
    trigger_channel_id = get_conf(guild.id, "voc_trigger_channel")
    if after.channel and after.channel.id == trigger_channel_id:
        voc = await guild.create_voice_channel(name=f"🔊 {member.display_name}", category=after.channel.category)
        data.setdefault("temp_vocs", {})[str(voc.id)] = {"owner": member.id,
                                                        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        save_data(data)
        await member.move_to(voc)
    if before.channel:
        cid = str(before.channel.id)
        if cid in data.get("temp_vocs", {}) and len(before.channel.members) == 0:
            await before.channel.delete()
            del data["temp_vocs"][cid]
            save_data(data)

# ==================== LIENS ====================
@bot.command(name="allowlink")
@commands.has_permissions(manage_guild=True)
async def allow_link(ctx, channel: discord.TextChannel = None):
    if not channel: return await ctx.send("❌ Usage : `+allowlink #channel`")
    gid = str(ctx.guild.id)
    data.setdefault("allowed_links", {}).setdefault(gid, [])
    if channel.id not in data["allowed_links"][gid]:
        data["allowed_links"][gid].append(channel.id)
        save_data(data)
        await ctx.send(f"✅ Liens autorisés dans {channel.mention}")
    else: await ctx.send("ℹ️ Les liens étaient déjà bloqués ici.")

@bot.event
async def on_message(message):
    if message.author.bot: await bot.process_commands(message); return
    gid = str(message.guild.id) if message.guild else None
    if gid:
        allowed_channels = data.get("allowed_links", {}).get(gid, [])
        url_regex = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        if message.channel.id not in allowed_channels and re.search(url_regex, message.content):
            await message.delete()
            await message.channel.send(f"❌ {message.author.mention}, les liens ne sont pas autorisés ici !", delete_after=5)
            e = discord.Embed(title="🔗 Lien supprimé", color=discord.Color.orange())
            e.add_field(name="Auteur", value=message.author.mention)
            e.add_field(name="Salon", value=message.channel.mention)
            e.add_field(name="Message", value=message.content[:1024])
            e.timestamp = datetime.datetime.now(datetime.timezone.utc)
            await send_log(message.guild, e)
            return
    await bot.process_commands(message)

# ==================== SAY / LOCK / UNLOCK ====================
@bot.command(name="say")
@commands.has_permissions(manage_guild=True)
async def say(ctx, *, msg=None):
    if not msg: return await ctx.send("❌ Usage : `+say <message>`")
    await ctx.message.delete()
    await ctx.send(msg)

@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Salon verrouillé")

@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 Salon déverrouillé")

# ==================== REACTION ROLES ====================
class ReactionButton(Button):
    def __init__(self, emoji, role_id):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.gray)
        self.role_id = role_id
    
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.response.send_message("❌ Rôle introuvable.", ephemeral=True)
        
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"❌ Rôle **{role.name}** retiré", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ Rôle **{role.name}** ajouté", ephemeral=True)

@bot.command(name="reactionrole")
@commands.has_permissions(manage_roles=True)
async def reactionrole(ctx, channel: discord.TextChannel = None, emoji: str = None, role: discord.Role = None):
    if not all([channel, emoji, role]):
        return await ctx.send("❌ Usage : `+reactionrole #channel emoji @role`")
    
    # Vérifier que le bot peut gérer ce rôle
    if role >= ctx.guild.me.top_role:
        return await ctx.send("❌ Ce rôle est trop élevé dans la hiérarchie pour que je puisse le gérer.")
    
    view = View(timeout=None)
    view.add_item(ReactionButton(emoji, role.id))
    
    embed = discord.Embed(
        title="🎭 Rôles Réactions",
        description=f"Clique sur {emoji} pour obtenir le rôle {role.mention}",
        color=discord.Color.blue()
    )
    
    msg = await channel.send(embed=embed, view=view)
    
    # Sauvegarder dans data
    data.setdefault("reaction_roles", {})[str(msg.id)] = {
        "channel_id": channel.id,
        "emoji": emoji,
        "role_id": role.id
    }
    save_data(data)
    
    await ctx.send(f"✅ Rôle réaction configuré dans {channel.mention}")

# ==================== GESTION ERREURS ====================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Tu n'as pas les permissions nécessaires pour utiliser cette commande.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant. Utilise `+help` pour voir l'usage correct.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Argument invalide. Vérifie ta commande.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignorer les commandes inexistantes
    else:
        print(f"Erreur : {error}")
        await ctx.send("❌ Une erreur est survenue lors de l'exécution de la commande.")

# ==================== LANCEMENT DU BOT ====================
if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ DISCORD_TOKEN manquant dans les variables d'environnement")
        print("💡 Crée un fichier .env avec : DISCORD_TOKEN=ton_token_ici")
        exit(1)
    
    print("🚀 Démarrage du bot Hoshikuzu...")
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Token Discord invalide. Vérifie ta variable d'environnement DISCORD_TOKEN.")
    except Exception as e:
        print(f"❌ Erreur fatale : {e}") liens étaient déjà autorisés ici.")

@bot.command(name="disallowlink")
@commands.has_permissions(manage_guild=True)
async def disallow_link(ctx, channel: discord.TextChannel = None):
    if not channel: return await ctx.send("❌ Usage : `+disallowlink #channel`")
    gid = str(ctx.guild.id)
    if gid in data.get("allowed_links", {}) and channel.id in data["allowed_links"][gid]:
        data["allowed_links"][gid].remove(channel.id)
        save_data(data)
        await ctx.send(f"❌ Liens bloqués dans {channel.mention}")
    else: await ctx.send("ℹ️ Les
