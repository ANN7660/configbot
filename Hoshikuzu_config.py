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
    return {
        "config": {}, "tickets": {}, "invites": {}, "roles_invites": {},
        "temp_vocs": {}, "user_invites": {}, "allowed_links": {}, "reaction_roles": {}
    }
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

# ==================== LOGGING HELPER ====================
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
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            data["invites"][str(guild.id)] = {inv.code: inv.uses for inv in invites}
            save_data(data)
        except:
            pass

# ==================== HELP ====================
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🌿 Commandes Hoshikuzu", color=discord.Color.green())
    e.add_field(name="📊 Configuration", value=(
        "+config\n+setwelcome #channel <embed/text>\n+setleave #channel <embed/text>\n+setlogs #channel\n+setinvitation #channel"
    ), inline=False)
    e.add_field(name="👥 Invitations", value="+roleinvite <nombre> @role\n+invites [@user]", inline=False)
    e.add_field(name="🔗 Liens", value="+allowlink #channel / +disallowlink #channel", inline=False)
    e.add_field(name="🔒 Modération", value="+lock / +unlock / +ban / +unban / +mute / +unmute", inline=False)
    e.add_field(name="👤 Rôles", value="+role @user @role / +rolejoin @role", inline=False)
    e.add_field(name="🎫 Tickets", value="+ticket / +ticketpanel / +close / +ticketrole", inline=False)
    e.add_field(name="🎭 Rôles Réactions", value="+reactionrole / +listreactionroles", inline=False)
    e.add_field(name="💬 Utilitaires", value="+say <message>", inline=False)
    e.add_field(name="🧪 Tests", value="+testwelcome / +testleave", inline=False)
    e.add_field(name="🔊 Vocaux", value="+createvoc / +setupvoc", inline=False)
    await ctx.send(embed=e)

# ==================== WELCOME / LEAVE ====================
async def send_welcome(member):
    conf = get_gconf(member.guild.id)
    embed_ch_id = conf.get("welcome_embed_channel")
    text_ch_id = conf.get("welcome_text_channel")
    total_members = member.guild.member_count

    # Embed welcome
    if embed_ch_id:
        ch = member.guild.get_channel(embed_ch_id)
        if ch:
            e = discord.Embed(
                title="✨ Nouveau membre !",
                description=f"{member.mention} a rejoint le serveur !",
                color=discord.Color.green(),
                timestamp=datetime.datetime.utcnow()
            )
            e.set_footer(text=f"Nous sommes maintenant {total_members} membres")
            await ch.send(embed=e)

    # Text welcome
    if text_ch_id:
        ch = member.guild.get_channel(text_ch_id)
        if ch:
            msg = (
                f"{EMOJI} Bienvenue {member.mention} sur **Hoshikuzu** !\n"
                f"{EMOJI} Nous sommes maintenant **{total_members} membres**."
            )
            await ch.send(msg)

async def send_leave(member):
    conf = get_gconf(member.guild.id)
    embed_ch_id = conf.get("leave_embed_channel")
    text_ch_id = conf.get("leave_text_channel")
    total_members = member.guild.member_count

    # Embed leave
    if embed_ch_id:
        ch = member.guild.get_channel(embed_ch_id)
        if ch:
            e = discord.Embed(
                title="❌ Un membre nous quitte...",
                description=f"{member.mention} a quitté le serveur.",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            e.set_footer(text=f"Il reste {total_members} membres")
            await ch.send(embed=e)

    # Text leave
    if text_ch_id:
        ch = member.guild.get_channel(text_ch_id)
        if ch:
            msg = (
                f"{EMOJI} {member.mention} a quitté le serveur.\n"
                f"{EMOJI} Il reste maintenant **{total_members} membres**."
            )
            await ch.send(msg)

@bot.event
async def on_member_join(member):
    await send_welcome(member)

@bot.event
async def on_member_remove(member):
    await send_leave(member)

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
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    channel = await ctx.guild.create_text_channel(name=f"ticket-{ctx.author.name}", overwrites=overwrites)
    ticket_roles = get_conf(ctx.guild.id, "ticket_roles") or []
    for role_id in ticket_roles:
        role = ctx.guild.get_role(role_id)
        if role:
            await channel.set_permissions(role, read_messages=True, send_messages=True)
    embed = discord.Embed(title="🎫 Ticket ouvert", description=f"{ctx.author.mention}, explique ton problème ici.", color=discord.Color.green())
    await channel.send(embed=embed, view=TicketView())
    await ctx.send(f"✅ Ticket créé : {channel.mention}", delete_after=5)

@bot.command(name="ticketpanel")
@commands.has_permissions(manage_guild=True)
async def ticket_panel(ctx):
    embed = discord.Embed(title="🎫 Ouvre un ticket !", description="Clique sur le bouton ci-dessous pour créer un ticket privé !", color=discord.Color.green())
    view = TicketView()
    msg = await ctx.send(embed=embed, view=view)
    set_conf(ctx.guild.id, "ticket_panel", msg.id)
    set_conf(ctx.guild.id, "ticket_panel_channel", ctx.channel.id)
    await ctx.send("✅ Panel de tickets créé avec succès !")

@bot.command(name="ticketrole")
@commands.has_permissions(manage_guild=True)
async def ticket_role(ctx, *roles: discord.Role):
    role_ids = [role.id for role in roles]
    set_conf(ctx.guild.id, "ticket_roles", role_ids)
    await ctx.send(f"✅ Les rôles {', '.join([r.name for r in roles])} seront attribués dans les tickets.")

@bot.command(name="close")
async def close_ticket(ctx):
    if ctx.channel.name.startswith("ticket-"):
        await ctx.send("🔒 Ce ticket sera supprimé dans 5 secondes...")
        e = discord.Embed(title="🎫 Ticket fermé", color=discord.Color.red())
        e.add_field(name="Fermé par", value=ctx.author.mention, inline=True)
        e.add_field(name="Salon", value=ctx.channel.name, inline=True)
        e.timestamp = datetime.datetime.utcnow()
        await send_log(ctx.guild, e)
        await asyncio.sleep(5)
        await ctx.channel.delete()
    else:
        await ctx.send("❌ Cette commande ne fonctionne que dans un salon ticket.")

# ==================== VOC TEMPORAIRES ====================
@bot.command(name="setupvoc")
@commands.has_permissions(manage_guild=True)
async def setup_voc(ctx, channel: discord.VoiceChannel):
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
        data.setdefault("temp_vocs", {})[str(voc.id)] = {"owner": member.id, "created_at": datetime.datetime.utcnow().isoformat()}
        save_data(data)
        await member.move_to(voc)
    if before.channel:
        channel_id = str(before.channel.id)
        if channel_id in data.get("temp_vocs", {}) and len(before.channel.members) == 0:
            await before.channel.delete()
            del data["temp_vocs"][channel_id]
            save_data(data)

# ==================== LIENS ====================
@bot.command(name="allowlink")
@commands.has_permissions(manage_guild=True)
async def allow_link(ctx, channel: discord.TextChannel):
    gid = str(ctx.guild.id)
    data.setdefault("allowed_links", {}).setdefault(gid, [])
    if channel.id not in data["allowed_links"][gid]:
        data["allowed_links"][gid].append(channel.id)
        save_data(data)
        await ctx.send(f"✅ Liens autorisés dans {channel.mention}")
    else:
        await ctx.send(f"ℹ️ Liens déjà autorisés")

@bot.command(name="disallowlink")
@commands.has_permissions(manage_guild=True)
async def disallow_link(ctx, channel: discord.TextChannel):
    gid = str(ctx.guild.id)
    if gid in data.get("allowed_links", {}) and channel.id in data["allowed_links"][gid]:
        data["allowed_links"][gid].remove(channel.id)
        save_data(data)
        await ctx.send(f"✅ Liens bloqués dans {channel.mention}")
    else:
        await ctx.send(f"ℹ️ Liens déjà bloqués")

@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    gid = str(message.guild.id) if message.guild else None
    if gid:
        allowed_channels = data.get("allowed_links", {}).get(gid, [])
        if message.channel.id not in allowed_channels:
            url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
            if re.search(url_pattern, message.content):
                await message.delete()
                await message.channel.send(f"❌ {message.author.mention}, les liens ne sont pas autorisés ici !", delete_after=5)
                e = discord.Embed(title="🔗 Lien supprimé", color=discord.Color.orange())
                e.add_field(name="Auteur", value=message.author.mention, inline=True)
                e.add_field(name="Salon", value=message.channel.mention, inline=True)
                e.add_field(name="Contenu", value=message.content[:1024], inline=False)
                e.timestamp = datetime.datetime.utcnow()
                await send_log(message.guild, e)
                return
    await bot.process_commands(message)

# ==================== SAY ====================
@bot.command(name="say")
@commands.has_permissions(manage_guild=True)
async def say(ctx, *, msg):
    await ctx.message.delete()
    await ctx.send(msg)

# ==================== LOCK / UNLOCK ====================
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

# ==================== ROLE REACTION ====================
class ReactionButton(Button):
    def __init__(self, emoji, role_id):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.gray)
        self.role_id = role_id
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"❌ Rôle {role.name} retiré", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ Rôle {role.name} ajouté", ephemeral=True)

@bot.command(name="reactionrole")
@commands.has_permissions(manage_guild=True)
async def reactionrole(ctx, channel: discord.TextChannel, emoji, role: discord.Role):
    view = View(timeout=None)
    view.add_item(ReactionButton(emoji, role.id))
    msg = await channel.send(f"Réagis avec {emoji} pour obtenir le rôle {role.name}", view=view)
    data.setdefault("reaction_roles", {}).setdefault(str(ctx.guild.id), {})[str(msg.id)] = {"emoji": emoji, "role": role.id}
    save_data(data)
    await ctx.send("✅ Rôle réaction créé")

# ==================== MODERATION ====================
@bot.command(name="config")
@commands.has_permissions(administrator=True)
async def config(ctx, option=None, *, value=None):
    if option is None:
        await ctx.send("⚙️ Utilisation: +config <option> <valeur>")
        return
    set_conf(ctx.guild.id, option, value)
    await ctx.send(f"✅ Configuration {option} mise à jour avec la valeur: `{value}`")

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f"⛔ {member.mention} a été banni ! Raison: {reason if reason else 'Aucune'}")

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, member_str):
    banned_users = await ctx.guild.bans()
    member_name, member_discrim = member_str.split("#")
    for ban_entry in banned_users:
        user = ban_entry.user
        if (user.name, user.discriminator) == (member_name, member_discrim):
            await ctx.guild.unban(user)
            await ctx.send(f"✅ {user.mention} a été débanni !")
            return
    await ctx.send("❌ Membre non trouvé dans la liste des bannis.")

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, duration: str = None):
    time_multiplier = {"s":1, "m":60, "h":3600, "d":86400}
    seconds = 0
    if duration:
        unit = duration[-1]
        if unit not in time_multiplier:
            await ctx.send("❌ Format invalide. Exemple: 10s, 5m, 2h, 1d")
            return
        try:
            seconds = int(duration[:-1]) * time_multiplier[unit]
        except:
            await ctx.send("❌ Format invalide.")
            return
    try:
        until = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
        await member.timeout(until, reason=f"Muted par {ctx.author}")
        await ctx.send(f"🔇 {member.mention} a été mute pour {duration if duration else 'indéfiniment'}.")
    except Exception as e:
        await ctx.send(f"❌ Impossible de mute: {e}")

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    try:
        await member.timeout(None, reason=f"Unmute par
