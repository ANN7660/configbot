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
async def send_log(guild, embed):
    logs_channel_id = get_conf(guild.id, "logs_channel")
    if logs_channel_id:
        ch = guild.get_channel(logs_channel_id)
        if ch:
            try: await ch.send(embed=embed)
            except Exception as e: print(f"Erreur log: {e}")

# ==================== CONFIG COMMAND ====================
@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config_cmd(ctx):
    conf = get_gconf(ctx.guild.id)
    e = discord.Embed(title="⚙️ Configuration Hoshikuzu", color=discord.Color.blue())
    e.add_field(name="Bienvenue (embed)", value=conf.get("welcome_embed_channel","❌ Non défini"), inline=False)
    e.add_field(name="Bienvenue (texte)", value=conf.get("welcome_text_channel","❌ Non défini"), inline=False)
    e.add_field(name="Leave (embed)", value=conf.get("leave_embed_channel","❌ Non défini"), inline=False)
    e.add_field(name="Leave (texte)", value=conf.get("leave_text_channel","❌ Non défini"), inline=False)
    e.add_field(name="Tickets", value=conf.get("ticket_roles","❌ Aucun"), inline=False)
    e.add_field(name="Voc Trigger", value=conf.get("voc_trigger_channel","❌ Aucun"), inline=False)
    e.add_field(name="Rôles auto join", value=conf.get("auto_roles","❌ Aucun"), inline=False)
    await ctx.send(embed=e)

# ==================== WELCOME / LEAVE ====================
async def send_welcome(member):
    conf = get_gconf(member.guild.id)
    total = member.guild.member_count
    embed_ch = conf.get("welcome_embed_channel")
    text_ch = conf.get("welcome_text_channel")
    if embed_ch:
        ch = member.guild.get_channel(embed_ch)
        if ch:
            e = discord.Embed(title="✨ Bienvenue sur **Hoshikuzu** !",
                              description=f"{member.mention} vient de rejoindre ✨",
                              color=discord.Color.green(),
                              timestamp=datetime.datetime.utcnow())
            e.add_field(name="Infos :",
                        value=f"{EMOJI} **BVN {member.mention} sur Hoshikuzu !**\n"
                              f"{EMOJI} Nous sommes maintenant **{total} membres**.")
            e.set_thumbnail(url=member.avatar)
            e.set_footer(text="Profite bien de ton séjour ⭐")
            await ch.send(embed=e)
    if text_ch:
        ch = member.guild.get_channel(text_ch)
        if ch:
            await ch.send(f"{EMOJI} **BVN {member.mention} sur Hoshikuzu !**\n{EMOJI} Nous sommes maintenant **{total} membres**.")
    # Roles auto join
    auto_roles = get_conf(member.guild.id, "auto_roles", [])
    for role_id in auto_roles:
        role = member.guild.get_role(role_id)
        if role:
            try: await member.add_roles(role, reason="Role join automatique")
            except: print(f"Impossible d'ajouter le rôle {role.name} à {member}")

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
                              timestamp=datetime.datetime.utcnow())
            e.add_field(name="Infos :", value=f"{EMOJI} {member.mention} a quitté Hoshikuzu...\n{EMOJI} Il reste maintenant **{total} membres**.")
            e.set_thumbnail(url=member.avatar)
            await ch.send(embed=e)
    if text_ch:
        ch = member.guild.get_channel(text_ch)
        await ch.send(f"{EMOJI} {member.mention} a quitté Hoshikuzu...\n{EMOJI} Il reste maintenant **{total} membres**.")

@bot.event
async def on_member_join(member): await send_welcome(member)
@bot.event
async def on_member_remove(member): await send_leave(member)

# ==================== SET WELCOME / LEAVE ====================
@bot.command(name="setwelcome")
@commands.has_permissions(manage_guild=True)
async def setwelcome(ctx, channel: discord.TextChannel, mode):
    gid = ctx.guild.id
    if mode.lower()=="embed":
        set_conf(gid,"welcome_embed_channel",channel.id)
        await ctx.send(f"✅ Salon embed bienvenue défini sur {channel.mention}")
    else:
        set_conf(gid,"welcome_text_channel",channel.id)
        await ctx.send(f"✅ Salon texte bienvenue défini sur {channel.mention}")

@bot.command(name="setleave")
@commands.has_permissions(manage_guild=True)
async def setleave(ctx, channel: discord.TextChannel, mode):
    gid = ctx.guild.id
    if mode.lower()=="embed":
        set_conf(gid,"leave_embed_channel",channel.id)
        await ctx.send(f"✅ Salon embed leave défini sur {channel.mention}")
    else:
        set_conf(gid,"leave_text_channel",channel.id)
        await ctx.send(f"✅ Salon texte leave défini sur {channel.mention}")

# ==================== ROLE JOIN ====================
@bot.command(name="rolejoin")
@commands.has_permissions(manage_guild=True)
async def role_join(ctx,*roles: discord.Role):
    role_ids = [r.id for r in roles]
    set_conf(ctx.guild.id,"auto_roles",role_ids)
    await ctx.send(f"✅ Rôles attribués automatiquement aux nouveaux membres : {', '.join([r.name for r in roles])}")

# ==================== MODÉRATION ====================
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison"):
    if member.id == ctx.author.id: return await ctx.send("❌ Tu ne peux pas te bannir toi-même.")
    if member.id == ctx.guild.me.id: return await ctx.send("❌ Impossible de ban le bot.")
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner: return await ctx.send("❌ Impossible de ban un rôle supérieur ou égal.")
    if member.guild_permissions.administrator: return await ctx.send("❌ Impossible de bannir un admin.")
    await member.ban(reason=f"Banni par {ctx.author} | {reason}")
    embed = discord.Embed(title="🔨 Membre banni",color=discord.Color.red(),timestamp=datetime.datetime.utcnow())
    embed.add_field(name="👤 Membre",value=f"{member} (`{member.id}`)",inline=False)
    embed.add_field(name="🛠️ Staff",value=ctx.author.mention,inline=False)
    embed.add_field(name="📄 Raison",value=reason,inline=False)
    await ctx.send(embed=embed)
    await send_log(ctx.guild, embed)

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, user):
    banned = await ctx.guild.bans()
    try:
        name, discrim = user.split("#")
    except: return await ctx.send("❌ Format invalide, ex: User#1234")
    for ban_entry in banned:
        if (ban_entry.user.name, ban_entry.user.discriminator) == (name, discrim):
            await ctx.guild.unban(ban_entry.user)
            return await ctx.send(f"♻️ {ban_entry.user} a été unban.")
    await ctx.send("❌ Utilisateur introuvable.")

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, duration: int, *, reason="Aucune raison"):
    seconds = duration*60
    try: await member.timeout(discord.utils.utcnow()+datetime.timedelta(seconds=seconds),reason=reason)
    except: return await ctx.send("❌ Impossible de timeout cet utilisateur.")
    embed = discord.Embed(title="🔇 Mute",color=discord.Color.orange(),timestamp=datetime.datetime.utcnow())
    embed.add_field(name="Utilisateur",value=member.mention)
    embed.add_field(name="Durée",value=f"{duration} minutes")
    embed.add_field(name="Raison",value=reason)
    embed.add_field(name="Par",value=ctx.author.mention)
    await ctx.send(f"🔇 {member.mention} a été mute pendant **{duration} minutes**.")
    await send_log(ctx.guild, embed)

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member, *, reason="Aucune raison"):
    try: await member.timeout(None,reason=reason)
    except: return await ctx.send("❌ Impossible d’unmute cet utilisateur.")
    embed = discord.Embed(title="🔊 Unmute",color=discord.Color.green(),timestamp=datetime.datetime.utcnow())
    embed.add_field(name="Utilisateur",value=member.mention)
    embed.add_field(name="Raison",value=reason)
    embed.add_field(name="Par",value=ctx.author.mention)
    await ctx.send(f"🔊 {member.mention} a été unmute.")
    await send_log(ctx.guild, embed)

# ==================== REACTION ROLES ====================
class ReactionButton(Button):
    def __init__(self, emoji, role_id):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.gray)
        self.role_id = role_id
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role: return await interaction.response.send_message("❌ Rôle introuvable.", ephemeral=True)
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
    data.setdefault("reaction_roles", {}).setdefault(str(ctx.guild.id), {})[str(msg.id)] = {"emoji": emoji,"role": role.id}
    save_data(data)
    await ctx.send("✅ Rôle réaction créé !")

# ==================== RUN ====================
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token: print("❌ DISCORD_TOKEN non défini"); exit(1)
    print("🚀 Démarrage du bot Hoshikuzu...")
    try: bot.run(token)
    except discord.LoginFailure: print("❌ Token Discord invalide !")
    except Exception as e: print(f"❌ Erreur lors du démarrage : {e}")
