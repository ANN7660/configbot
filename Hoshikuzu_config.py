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

# ==================== READY ====================
@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")
    await bot.change_presence(activity=discord.Game(name="hoshikuzu | +help"))

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

# ==================== CONFIG / WELCOME / LEAVE ====================
@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config_cmd(ctx):
    conf = get_gconf(ctx.guild.id)
    e = discord.Embed(title="⚙️ Configuration Hoshikuzu", color=discord.Color.blue())
    e.add_field(name="Bienvenue (embed)", value=conf.get("welcome_embed_channel", "❌ Non défini"), inline=False)
    e.add_field(name="Bienvenue (texte)", value=conf.get("welcome_text_channel", "❌ Non défini"), inline=False)
    e.add_field(name="Leave (embed)", value=conf.get("leave_embed_channel", "❌ Non défini"), inline=False)
    e.add_field(name="Leave (texte)", value=conf.get("leave_text_channel", "❌ Non défini"), inline=False)
    e.add_field(name="Tickets rôles", value=conf.get("ticket_roles", "❌ Aucun"), inline=False)
    e.add_field(name="Trigger Voc", value=conf.get("voc_trigger_channel", "❌ Aucun"), inline=False)
    await ctx.send(embed=e)

@bot.command(name="setwelcome")
@commands.has_permissions(manage_guild=True)
async def setwelcome(ctx, channel: discord.TextChannel, mode):
    if mode.lower() == "embed":
        set_conf(ctx.guild.id, "welcome_embed_channel", channel.id)
        await ctx.send(f"✅ Bienvenue embed sur {channel.mention}")
    else:
        set_conf(ctx.guild.id, "welcome_text_channel", channel.id)
        await ctx.send(f"✅ Bienvenue texte sur {channel.mention}")

@bot.command(name="setleave")
@commands.has_permissions(manage_guild=True)
async def setleave(ctx, channel: discord.TextChannel, mode):
    if mode.lower() == "embed":
        set_conf(ctx.guild.id, "leave_embed_channel", channel.id)
        await ctx.send(f"✅ Leave embed sur {channel.mention}")
    else:
        set_conf(ctx.guild.id, "leave_text_channel", channel.id)
        await ctx.send(f"✅ Leave texte sur {channel.mention}")

async def send_welcome(member):
    conf = get_gconf(member.guild.id)
    total = member.guild.member_count
    embed_ch = conf.get("welcome_embed_channel")
    text_ch = conf.get("welcome_text_channel")

    if embed_ch:
        ch = member.guild.get_channel(embed_ch)
        if ch:
            e = discord.Embed(
                title="✨ Bienvenue sur Hoshikuzu !",
                description=f"{member.mention} rejoint le serveur",
                color=discord.Color.green(),
                timestamp=datetime.datetime.utcnow()
            )
            e.add_field(name="Infos", value=f"{EMOJI} **BVN {member.mention} sur Hoshikuzu !**\n{EMOJI} Nous sommes {total} membres.")
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text="Bienvenue à toi !")
            await ch.send(embed=e)
    if text_ch:
        ch = member.guild.get_channel(text_ch)
        if ch:
            await ch.send(f"{EMOJI} **BVN {member.mention} sur Hoshikuzu !**\n{EMOJI} Nous sommes {total} membres.")

async def send_leave(member):
    conf = get_gconf(member.guild.id)
    total = member.guild.member_count
    embed_ch = conf.get("leave_embed_channel")
    text_ch = conf.get("leave_text_channel")

    if embed_ch:
        ch = member.guild.get_channel(embed_ch)
        if ch:
            e = discord.Embed(
                title="❌ Un membre nous quitte...",
                description=f"{member.mention} nous a quitté.",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            e.add_field(name="Infos", value=f"{EMOJI} {member.mention} a quitté Hoshikuzu...\n{EMOJI} Il reste {total} membres.")
            e.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=e)
    if text_ch:
        ch = member.guild.get_channel(text_ch)
        if ch:
            await ch.send(f"{EMOJI} {member.mention} a quitté Hoshikuzu...\n{EMOJI} Il reste {total} membres.")

@bot.event
async def on_member_join(member):
    await send_welcome(member)

@bot.event
async def on_member_remove(member):
    await send_leave(member)

# ==================== MODÉRATION ====================
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_user(ctx, member: discord.Member, *, reason="Aucune raison"):
    if member.id == ctx.author.id:
        return await ctx.send("❌ Tu ne peux pas te bannir toi-même.")
    if member.id == ctx.guild.me.id:
        return await ctx.send("❌ Je ne peux pas me bannir moi-même.")
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("❌ Tu ne peux pas bannir un membre avec un rôle plus haut ou égal.")
    if member.guild_permissions.administrator:
        return await ctx.send("❌ Tu ne peux pas bannir un administrateur.")
    await member.ban(reason=f"Banni par {ctx.author} | {reason}")
    embed = discord.Embed(title="🔨 Membre banni", color=discord.Color.red(), timestamp=datetime.datetime.utcnow())
    embed.add_field(name="👤 Membre", value=f"{member} (`{member.id}`)", inline=False)
    embed.add_field(name="🛠️ Par", value=ctx.author.mention, inline=False)
    embed.add_field(name="📄 Raison", value=reason, inline=False)
    await ctx.send(embed=embed)
    await send_log(ctx.guild, embed)

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban_user(ctx, *, user: str):
    banned = await ctx.guild.bans()
    try:
        name, discrim = user.split("#")
    except:
        return await ctx.send("❌ Format invalide, utiliser Username#0000")
    for ban_entry in banned:
        u = ban_entry.user
        if (u.name, u.discriminator) == (name, discrim):
            await ctx.guild.unban(u)
            await ctx.send(f"🔓 {u.mention} a été dé-banni.")
            embed = discord.Embed(title="♻️ Unban", color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name="Utilisateur", value=u.mention)
            embed.add_field(name="Par", value=ctx.author.mention)
            await send_log(ctx.guild, embed)
            return
    await ctx.send("❌ Membre non trouvé dans la liste des bannis.")

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, duration: int, unit: str = "m", *, reason="Aucune raison"):
    mult = {"s":1, "m":60, "h":3600, "d":86400}
    unit = unit.lower()
    if unit not in mult:
        return await ctx.send("❌ Unité invalide (s, m, h, d)")
    seconds = duration * mult[unit]
    try:
        await member.timeout(datetime.timedelta(seconds=seconds), reason=f"Mute par {ctx.author} | {reason}")
    except Exception as e:
        return await ctx.send(f"❌ Impossible de mute : {e}")
    embed = discord.Embed(title="🔇 Mute", color=discord.Color.orange(), timestamp=datetime.datetime.utcnow())
    embed.add_field(name="Utilisateur", value=member.mention)
    embed.add_field(name="Durée", value=f"{duration}{unit}")
    embed.add_field(name="Raison", value=reason)
    embed.add_field(name="Par", value=ctx.author.mention)
    await ctx.send(f"🔇 {member.mention} a été mute pendant **{duration}{unit}**.")
    await send_log(ctx.guild, embed)

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member, *, reason="Aucune raison"):
    try:
        await member.timeout(None, reason=f"Unmute par {ctx.author} | {reason}")
    except Exception as e:
        return await ctx.send(f"❌ Impossible d’unmute : {e}")
    embed = discord.Embed(title="🔊 Unmute", color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
    embed.add_field(name="Utilisateur", value=member.mention)
    embed.add_field(name="Raison", value=reason)
    embed.add_field(name="Par", value=ctx.author.mention)
    await ctx.send(f"🔊 {member.mention} a été unmute.")
    await send_log(ctx.guild, embed)

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
    roles = get_conf(ctx.guild.id, "ticket_roles") or []
    for rid in roles:
        role = ctx.guild.get_role(rid)
        if role:
            await channel.set_permissions(role, read_messages=True, send_messages=True)
    embed = discord.Embed(title="🎫 Ticket ouvert", description=f"{ctx.author.mention}, explique ton problème ici.", color=discord.Color.green())
    await channel.send(embed=embed, view=TicketView())
    await ctx.send(f"✅ Ticket créé : {channel.mention}", delete_after=5)

# ==================== VOC TEMP ====================
@bot.command(name="setupvoc")
@commands.has_permissions(manage_guild=True)
async def setup_voc(ctx, channel: discord.VoiceChannel):
    set_conf(ctx.guild.id, "voc_trigger_channel", channel.id)
    await channel.edit(name=VOC_TRIGGER_NAME)
    await ctx.send(f"✅ Salon trigger vocal configuré : {channel.mention}")

@bot.command(name="createvoc")
@commands.has_permissions(manage_guild=True)
async def create_voc(ctx):
    category = ctx.channel.category
    voc = await ctx.guild.create_voice_channel(name=VOC_TRIGGER_NAME, category=category)
    set_conf(ctx.guild.id, "voc_trigger_channel", voc.id)
    await ctx.send(f"✅ Salon vocal trigger créé : {voc.mention}")

@bot.event
async def on_voice_state_update(member, before, after):
    gid = member.guild.id
    trigger = get_conf(gid, "voc_trigger_channel")
    if after.channel and after.channel.id == trigger:
        voc = await member.guild.create_voice_channel(name=f"🔊 {member.display_name}", category=after.channel.category)
        data.setdefault("temp_vocs", {})[str(voc.id)] = {"owner": member.id, "created_at": datetime.datetime.utcnow().isoformat()}
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
async def allow_link(ctx, channel: discord.TextChannel):
    gid = str(ctx.guild.id)
    data.setdefault("allowed_links", {}).setdefault(gid, [])
    if channel.id not in data["allowed_links"][gid]:
        data["allowed_links"][gid].append(channel.id)
        save_data(data)
        await ctx.send(f"✅ Liens autorisés dans {channel.mention}")
    else:
        await ctx.send("ℹ️ Liens déjà autorisés")

@bot.command(name="disallowlink")
@commands.has_permissions(manage_guild=True)
async def disallow_link(ctx, channel: discord.TextChannel):
    gid = str(ctx.guild.id)
    if gid in data.get("allowed_links", {}) and channel.id in data["allowed_links"][gid]:
        data["allowed_links"][gid].remove(channel.id)
        save_data(data)
        await ctx.send(f"❌ Liens bloqués dans {channel.mention}")
    else:
        await ctx.send("ℹ️ Liens déjà bloqués")

@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    gid = str(message.guild.id)
    allowed = data.get("allowed_links", {}).get(gid, [])
    url_regex = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    if message.channel.id not in allowed and re.search(url_regex, message.content):
        await message.delete()
        e = discord.Embed(title="🔗 Lien supprimé", color=discord.Color.orange())
        e.add_field(name="Auteur", value=message.author.mention, inline=True)
        e.add_field(name="Salon", value=message.channel.mention, inline=True)
        e.add_field(name="Message", value=message.content[:1024], inline=False)
        e.timestamp = datetime.datetime.utcnow()
        await send_log(message.guild, e)
        return
    await bot.process_commands(message)

# ==================== SAY / LOCK / REACTION ROLES ====================
@bot.command(name="say")
@commands.has_permissions(manage_guild=True)
async def say(ctx, *, msg):
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

class ReactionButton(Button):
    def __init__(self, emoji, role_id):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.gray)
        self.role_id = role_id
    async def callback(self, interaction):
        role = interaction.guild.get_role(self.role_id)
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"❌ Rôle **{role.name}** retiré", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ Rôle **{role.name}** ajouté", ephemeral=True)

@bot.command(name="reactionrole")
@commands.has_permissions(manage_guild=True)
async def reactionrole(ctx, channel: discord.TextChannel, emoji, role: discord.Role):
    view = View(timeout=None)
    view.add_item(ReactionButton(emoji, role.id))
    msg = await channel.send(f"Réagis avec {emoji} pour obtenir le rôle **{role.name}**", view=view)
    data.setdefault("reaction_roles", {}).setdefault(str(ctx.guild.id), {})[str(msg.id)] = {"emoji": emoji, "role": role.id}
    save_data(data)
    await ctx.send("✅ Rôle réaction créé !")

# ==================== RUN BOT ====================
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERREUR : DISCORD_TOKEN non défini")
        exit(1)
    print("🚀 Démarrage du bot Hoshikuzu...")
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ Token Discord invalide !")
    except Exception as e:
        print(f"❌ Erreur: {e}")
