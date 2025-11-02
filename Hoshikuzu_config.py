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
    return {"config": {}, "tickets": {}}

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
intents.voice_states = True
intents.reactions = True
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)
EMOJI = "<a:caarrow:1433143710094196997>"

@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")

# === Commandes ===
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🌿 Commandes Hoshikuzu", color=discord.Color.green())
    e.add_field(name="📊 Configuration", value=(
        "`+config` - Voir la config actuelle\n"
        "`+setwelcome #channel <embed/text>` - Salon de bienvenue\n"
        "`+setleave #channel <embed/text>` - Salon d'au revoir\n"
        "`+setlogs #channel` - Salon de logs"
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
        "`+ticketpanel` - Panel avec bouton\n"
        "`+close` - Fermer un ticket"
    ), inline=False)
    e.add_field(name="🧪 Tests", value=(
        "`+testwelcome` - Test bienvenue\n"
        "`+testleave` - Test au revoir"
    ), inline=False)
    await ctx.send(embed=e)

@bot.command(name="config")
@commands.has_permissions(manage_guild=True)
async def config_cmd(ctx):
    conf = get_gconf(ctx.guild.id)
    e = discord.Embed(title="⚙️ Configuration actuelle", color=discord.Color.green())
    for key in ["logs_channel", "welcome_embed_channel", "welcome_text_channel", "leave_embed_channel", "leave_text_channel"]:
        val = conf.get(key)
        e.add_field(name=key.replace("_channel", "").replace("_", " ").title(), value=f"<#{val}>" if val else "Aucun", inline=False)
    await ctx.send(embed=e)

@bot.command(name="setwelcome")
@commands.has_permissions(manage_guild=True)
async def set_welcome(ctx, channel: discord.TextChannel, type: str = "embed"):
    """Configure le salon de bienvenue. Type: embed ou text"""
    if type.lower() == "embed":
        set_conf(ctx.guild.id, "welcome_embed_channel", channel.id)
        await ctx.send(f"✅ Messages de bienvenue (embed) définis dans {channel.mention}")
    elif type.lower() == "text":
        set_conf(ctx.guild.id, "welcome_text_channel", channel.id)
        await ctx.send(f"✅ Messages de bienvenue (texte) définis dans {channel.mention}")
    else:
        await ctx.send("❌ Type invalide ! Utilise `embed` ou `text`")

@bot.command(name="setleave")
@commands.has_permissions(manage_guild=True)
async def set_leave(ctx, channel: discord.TextChannel, type: str = "embed"):
    """Configure le salon d'au revoir. Type: embed ou text"""
    if type.lower() == "embed":
        set_conf(ctx.guild.id, "leave_embed_channel", channel.id)
        await ctx.send(f"✅ Messages d'au revoir (embed) définis dans {channel.mention}")
    elif type.lower() == "text":
        set_conf(ctx.guild.id, "leave_text_channel", channel.id)
        await ctx.send(f"✅ Messages d'au revoir (texte) définis dans {channel.mention}")
    else:
        await ctx.send("❌ Type invalide ! Utilise `embed` ou `text`")

@bot.command(name="setlogs")
@commands.has_permissions(manage_guild=True)
async def set_logs(ctx, channel: discord.TextChannel):
    """Configure le salon des logs"""
    set_conf(ctx.guild.id, "logs_channel", channel.id)
    await ctx.send(f"✅ Salon de logs défini : {channel.mention}")

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
    await ctx.send(f"✅ Rôle d'arrivée défini : {role.name}")

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
    """Crée un panel avec bouton pour ouvrir des tickets"""
    embed = discord.Embed(
        title="🎫 Système de Tickets",
        description="Besoin d'aide ? Clique sur le bouton ci-dessous pour créer un ticket !\n\nNotre équipe te répondra dès que possible.",
        color=discord.Color.green()
    )
    embed.add_field(name="📋 Utilisation", value="• Clique sur 🎫\n• Un salon privé sera créé\n• Explique ton problème", inline=False)
    embed.set_footer(text="Hoshikuzu — Support")
    
    # Créer le message
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎫")
    
    # Sauvegarder l'ID du message pour le panel
    set_conf(ctx.guild.id, "ticket_panel_msg", msg.id)
    set_conf(ctx.guild.id, "ticket_panel_channel", ctx.channel.id)
    
    await ctx.send("✅ Panel de tickets créé !", delete_after=5)

@bot.event
async def on_raw_reaction_add(payload):
    # Ignorer les réactions du bot
    if payload.user_id == bot.user.id:
        return
    
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    
    # Vérifier si c'est le panel de tickets
    panel_msg_id = get_conf(guild.id, "ticket_panel_msg")
    panel_channel_id = get_conf(guild.id, "ticket_panel_channel")
    
    if panel_msg_id == payload.message_id and str(payload.emoji) == "🎫":
        member = guild.get_member(payload.user_id)
        if not member:
            return
        
        # Vérifier si l'utilisateur a déjà un ticket ouvert
        existing_ticket = discord.utils.get(guild.text_channels, name=f"ticket-{member.name}")
        if existing_ticket:
            try:
                await member.send(f"❌ Tu as déjà un ticket ouvert : {existing_ticket.mention}")
            except:
                pass
            
            # Retirer la réaction
            channel = bot.get_channel(payload.channel_id)
            if channel:
                try:
                    msg = await channel.fetch_message(payload.message_id)
                    await msg.remove_reaction(payload.emoji, member)
                except:
                    pass
            return
        
        # Créer le ticket
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        # Ajouter les admins/modos au ticket
        for role in guild.roles:
            if role.permissions.manage_guild or role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        try:
            ticket_channel = await guild.create_text_channel(
                name=f"ticket-{member.name}",
                overwrites=overwrites,
                topic=f"Ticket de {member.name} ({member.id})"
            )
            
            # Message de bienvenue dans le ticket
            embed = discord.Embed(
                title="🎫 Ticket créé !",
                description=f"Bienvenue {member.mention} !\n\nExplique ton problème et notre équipe te répondra rapidement.",
                color=discord.Color.green()
            )
            embed.add_field(name="📝 Fermer le ticket", value="Utilise `+close` pour fermer ce ticket", inline=False)
            
            await ticket_channel.send(f"{member.mention}", embed=embed)
            
            # Sauvegarder le ticket
            tickets = data.setdefault("tickets", {})
            tickets[str(ticket_channel.id)] = {
                "user_id": member.id,
                "created_at": str(datetime.datetime.now())
            }
            save_data(data)
            
            # MP à l'utilisateur
            try:
                await member.send(f"✅ Ton ticket a été créé : {ticket_channel.mention}")
            except:
                pass
            
        except Exception as e:
            print(f"Erreur création ticket: {e}")
        
        # Retirer la réaction
        channel = bot.get_channel(payload.channel_id)
        if channel:
            try:
                msg = await channel.fetch_message(payload.message_id)
                await msg.remove_reaction(payload.emoji, member)
            except:
                pass

@bot.command(name="close")
async def close_ticket(ctx):
    """Ferme un ticket"""
    # Vérifier si c'est un salon ticket
    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.send("❌ Cette commande fonctionne uniquement dans les tickets !")
    
    # Vérifier les permissions
    if not (ctx.author.guild_permissions.manage_channels or 
            str(ctx.channel.id) in data.get("tickets", {}) and 
            data["tickets"][str(ctx.channel.id)]["user_id"] == ctx.author.id):
        return await ctx.send("❌ Tu n'as pas la permission de fermer ce ticket !")
    
    embed = discord.Embed(
        title="🔒 Fermeture du ticket",
        description="Ce ticket va être supprimé dans 5 secondes...",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)
    
    # Supprimer des données
    tickets = data.get("tickets", {})
    if str(ctx.channel.id) in tickets:
        del tickets[str(ctx.channel.id)]
        save_data(data)
    
    await asyncio.sleep(5)
    await ctx.channel.delete(reason="Ticket fermé")

@bot.command(name="allowlink")
@commands.has_permissions(manage_guild=True)
async def allowlink(ctx, channel: discord.TextChannel):
    links = get_conf(ctx.guild.id, "allow_links", [])
    if channel.id not in links:
        links.append(channel.id)
        set_conf(ctx.guild.id, "allow_links", links)
        await ctx.send(f"✅ Liens autorisés dans {channel.mention}")
    else:
        await ctx.send(f"ℹ️ Déjà autorisé.")

@bot.command(name="disallowlink")
@commands.has_permissions(manage_guild=True)
async def disallowlink(ctx, channel: discord.TextChannel):
    links = get_conf(ctx.guild.id, "allow_links", [])
    if channel.id in links:
        links.remove(channel.id)
        set_conf(ctx.guild.id, "allow_links", links)
        await ctx.send(f"❌ Liens désactivés dans {channel.mention}")
    else:
        await ctx.send(f"ℹ️ Déjà désactivé.")

# === Bienvenue / Au revoir ===
@bot.event
async def on_member_join(member):
    gid = member.guild.id
    total = member.guild.member_count

    embed_id = get_conf(gid, "welcome_embed_channel")
    if embed_id:
        ch = bot.get_channel(embed_id)
        if ch:
            e = discord.Embed(title="🌿 Bienvenue !", description=f"{member.mention} a rejoint le serveur.", color=discord.Color.green())
            e.set_footer(text=f"Tu es le {total}ᵉ membre !")
            e.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=e)

    text_id = get_conf(gid, "welcome_text_channel")
    if text_id:
        ch = bot.get_channel(text_id)
        if ch:
            await ch.send(f"{EMOJI} Bienvenue {member.mention} sur **Hoshikuzu** !\n{EMOJI} Tu es le **{total}ᵉ** membre !")

    role_id = get_conf(gid, "auto_role")
    if role_id:
        role = member.guild.get_role(role_id)
        if role:
            await member.add_roles(role)

@bot.event
async def on_member_remove(member):
    gid = member.guild.id
    total = member.guild.member_count

    embed_id = get_conf(gid, "leave_embed_channel")
    if embed_id:
        ch = bot.get_channel(embed_id)
        if ch:
            e = discord.Embed(title="👋 Au revoir !", description=f"{member.name} a quitté le serveur.", color=discord.Color.red())
            e.set_footer(text=f"Il reste {total} membres.")
            e.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=e)

    text_id = get_conf(gid, "leave_text_channel")
    if text_id:
        ch = bot.get_channel(text_id)
        if ch:
            await ch.send(f"{EMOJI} {member.name} a quitté le serveur. Il reste **{total}** membres.")

# === Tests ===
@bot.command(name="testwelcome")
@commands.has_permissions(manage_guild=True)
async def test_welcome(ctx):
    await on_member_join(ctx.author)
    await ctx.send("✅ Test de bienvenue envoyé.")

@bot.command(name="testleave")
@commands.has_permissions(manage_guild=True)
async def test_leave(ctx):
    await on_member_remove(ctx.author)
    await ctx.send("✅ Test d'au revoir envoyé.")

# === Salon vocal temporaire ===
VOC_TRIGGER_NAME = "🔊Créer un voc"

@bot.event
async def on_voice_state_update(member, before, after):
    try:
        if after.channel and after.channel.name == VOC_TRIGGER_NAME:
            guild = member.guild
            category = after.channel.category
            
            # Créer un salon vocal temporaire
            temp_channel = await guild.create_voice_channel(
                name=f"Voc de {member.display_name}",
                category=category
            )
            
            # Déplacer le membre
            await member.move_to(temp_channel)
            
            # Sauvegarder l'info du salon temporaire
            data.setdefault("temp_vocs", {})[str(temp_channel.id)] = member.id
            save_data(data)
        
        # Supprimer les salons vides
        if before.channel and before.channel.id != after.channel.id if after.channel else True:
            temp_vocs = data.get("temp_vocs", {})
            if str(before.channel.id) in temp_vocs and len(before.channel.members) == 0:
                await before.channel.delete()
                del temp_vocs[str(before.channel.id)]
                save_data(data)
    
    except Exception as e:
        print(f"Erreur vocal temporaire: {e}")

# === Lancement du bot ===
if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN manquant !")
        print("ℹ️  Configure la variable d'environnement DISCORD_TOKEN sur Render")
        print("ℹ️  Variables disponibles:", list(os.environ.keys())[:10])
        exit(1)
    else:
        print(f"✅ Token trouvé, démarrage du bot...")
        bot.run(token)
