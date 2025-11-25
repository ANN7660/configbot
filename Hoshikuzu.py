import disnake as discord
from disnake.ext import commands, tasks
from disnake.ui import Button, View, Select
import asyncio
import aiohttp
import json
import os
from datetime import datetime, timedelta
import random
from collections import defaultdict
from flask import Flask
from threading import Thread
import io
from PIL import Image, ImageDraw, ImageFont

# ============= CONFIGURATION =============
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ============= DONNÉES =============
economy_data = defaultdict(lambda: {"money": 0, "bank": 0, "xp": 0, "level": 1, "rep": 0, "daily_claimed": None, "work_claimed": None, "inventory": []})
warnings_data = defaultdict(list)
tickets_data = defaultdict(list)
stats_data = defaultdict(lambda: {"messages": 0, "voice_time": 0, "last_message": None})
giveaways_data = []
voice_tracking = {}

server_config = defaultdict(lambda: {
    "welcome_channel": None,
    "leave_channel": None,
    "welcome_msg": "Bienvenue {user} sur {server}!",
    "leave_msg": "{user} a quitté {server}",
    "welcome_embed": None,
    "leave_embed": None,
    "automod_words": [],
    "shop": [],
    "ticket_category": None,
    "ticket_role": None,
    "ticket_counter": 0,
    "tempvoc_channel": None,
    "tempvoc_category": None,
    "log_channels": {},
    "autorole": None,
    "level_roles": {},
    "antispam": {"enabled": False, "messages": 5, "seconds": 5}
})

# ============= KEEP ALIVE (RENDER) =============
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ============= EVENTS =============
@bot.event
async def on_ready():
    print(f'✅ {bot.user} est connecté!')
    auto_reboot.start()
    check_giveaways.start()
    await bot.change_presence(activity=discord.Game(name="!help"))

@tasks.loop(hours=23)
async def auto_reboot():
    print("🔄 Auto-reboot check...")

@tasks.loop(seconds=30)
async def check_giveaways():
    current_time = datetime.now()
    for giveaway in giveaways_data[:]:
        if current_time >= giveaway["end_time"]:
            channel = bot.get_channel(giveaway["channel_id"])
            if channel:
                try:
                    msg = await channel.fetch_message(giveaway["message_id"])
                    reaction = discord.utils.get(msg.reactions, emoji="🎉")
                    if reaction:
                        users = [user async for user in reaction.users() if not user.bot]
                        if users:
                            winner = random.choice(users)
                            await channel.send(f"🎉 Félicitations {winner.mention}! Vous avez gagné **{giveaway['prize']}**!")
                        else:
                            await channel.send("❌ Aucun participant au giveaway!")
                except:
                    pass
            giveaways_data.remove(giveaway)

@bot.event
async def on_member_join(member):
    config = server_config[member.guild.id]
    
    # Autorole
    if config.get("autorole"):
        role = member.guild.get_role(config["autorole"])
        if role:
            await member.add_roles(role)
    
    # Welcome message
    channel_id = config.get("welcome_channel")
    if not channel_id:
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    
    if config.get("welcome_embed"):
        embed_data = config["welcome_embed"]
        embed = discord.Embed(
            title=embed_data.get("title", "Bienvenue!").replace("{user}", member.name),
            description=embed_data.get("description", "").replace("{user}", member.mention).replace("{server}", member.guild.name),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)
    else:
        msg = config["welcome_msg"].replace("{user}", member.mention).replace("{server}", member.guild.name)
        await channel.send(msg)
    
    # Log
    await log_action(member.guild, "membres", f"📥 {member.mention} a rejoint le serveur")

@bot.event
async def on_member_remove(member):
    config = server_config[member.guild.id]
    channel_id = config.get("leave_channel")
    if not channel_id:
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    
    if config.get("leave_embed"):
        embed_data = config["leave_embed"]
        embed = discord.Embed(
            title=embed_data.get("title", "Au revoir!").replace("{user}", member.name),
            description=embed_data.get("description", "").replace("{user}", member.name).replace("{server}", member.guild.name),
            color=discord.Color.red()
        )
        await channel.send(embed=embed)
    else:
        msg = config["leave_msg"].replace("{user}", member.name).replace("{server}", member.guild.name)
        await channel.send(msg)
    
    await log_action(member.guild, "membres", f"📤 {member.name} a quitté le serveur")

@bot.event
async def on_voice_state_update(member, before, after):
    config = server_config[member.guild.id]
    
    # Système de vocal temporaire
    if after.channel and after.channel.id == config.get("tempvoc_channel"):
        category = bot.get_channel(config.get("tempvoc_category"))
        if not category:
            category = after.channel.category
        
        temp_channel = await member.guild.create_voice_channel(
            name=f"🎤 {member.display_name}",
            category=category,
            user_limit=10
        )
        await member.move_to(temp_channel)
        
        # Attendre que le salon se vide pour le supprimer
        def check():
            return len(temp_channel.members) == 0
        
        while len(temp_channel.members) > 0:
            await asyncio.sleep(5)
        
        await temp_channel.delete()
    
    # Tracking temps vocal
    user_key = f"{member.guild.id}_{member.id}"
    
    if before.channel is None and after.channel is not None:
        voice_tracking[user_key] = datetime.now()
    
    elif before.channel is not None and after.channel is None:
        if user_key in voice_tracking:
            duration = (datetime.now() - voice_tracking[user_key]).total_seconds()
            stats_data[user_key]["voice_time"] += duration
            del voice_tracking[user_key]

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    config = server_config[message.guild.id]
    user_key = f"{message.guild.id}_{message.author.id}"
    
    # Stats
    stats_data[user_key]["messages"] += 1
    stats_data[user_key]["last_message"] = datetime.now()
    
    # Antispam
    antispam = config["antispam"]
    if antispam["enabled"]:
        recent_messages = [m for m in message.channel.history(limit=antispam["messages"]) 
                          if m.author == message.author and 
                          (datetime.now() - m.created_at).total_seconds() < antispam["seconds"]]
        
        if len(recent_messages) >= antispam["messages"]:
            await message.channel.purge(limit=antispam["messages"], check=lambda m: m.author == message.author)
            await message.channel.send(f"{message.author.mention}, stop le spam!", delete_after=5)
            return
    
    # Automod
    for word in config["automod_words"]:
        if word.lower() in message.content.lower():
            await message.delete()
            await message.channel.send(f"{message.author.mention}, ce mot est interdit!", delete_after=5)
            await log_action(message.guild, "modération", f"🚫 Message supprimé de {message.author.mention}: mot interdit")
            return
    
    # XP système
    user_data = economy_data[user_key]
    xp_gain = random.randint(10, 25)
    user_data["xp"] += xp_gain
    
    xp_needed = user_data["level"] * 100
    if user_data["xp"] >= xp_needed:
        user_data["level"] += 1
        user_data["xp"] = 0
        
        # Check level roles
        level_roles = config.get("level_roles", {})
        if user_data["level"] in level_roles:
            role = message.guild.get_role(level_roles[user_data["level"]])
            if role:
                await message.author.add_roles(role)
        
        await message.channel.send(f"🎉 {message.author.mention} a atteint le niveau {user_data['level']}!")
    
    await bot.process_commands(message)

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    await log_action(message.guild, "messages", f"🗑️ Message supprimé dans {message.channel.mention}\n**Auteur:** {message.author.mention}\n**Contenu:** {message.content[:100]}")

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    await log_action(before.guild, "messages", f"✏️ Message édité dans {before.channel.mention}\n**Auteur:** {before.author.mention}\n**Avant:** {before.content[:50]}\n**Après:** {after.content[:50]}")

# ============= LOG SYSTEM =============
async def log_action(guild, log_type, message):
    config = server_config[guild.id]
    log_channel_id = config["log_channels"].get(log_type)
    
    if not log_channel_id:
        return
    
    channel = bot.get_channel(log_channel_id)
    if channel:
        embed = discord.Embed(description=message, color=discord.Color.blue(), timestamp=datetime.now())
        await channel.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def setlog(ctx, log_type: str, channel: discord.TextChannel):
    valid_types = ["messages", "membres", "modération", "vocal"]
    if log_type not in valid_types:
        return await ctx.send(f"❌ Types valides: {', '.join(valid_types)}")
    
    server_config[ctx.guild.id]["log_channels"][log_type] = channel.id
    await ctx.send(f"✅ Logs **{log_type}** configurés dans {channel.mention}")

# ============= HELP COMMAND (Updated) =============
class HelpView(View):
    def __init__(self):
        super().__init__(timeout=180)
        self.category = "moderation"
    
    @discord.ui.button(label="Modération", style=discord.ButtonStyle.primary, emoji="🛡️")
    async def moderation_btn(self, interaction: discord.Interaction, button: Button):
        self.category = "moderation"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="Économie", style=discord.ButtonStyle.success, emoji="💰")
    async def economy_btn(self, interaction: discord.Interaction, button: Button):
        self.category = "economy"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="Fun", style=discord.ButtonStyle.danger, emoji="🎮")
    async def fun_btn(self, interaction: discord.Interaction, button: Button):
        self.category = "fun"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="Utilitaires", style=discord.ButtonStyle.secondary, emoji="🔧")
    async def utility_btn(self, interaction: discord.Interaction, button: Button):
        self.category = "utility"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="Systèmes", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def systems_btn(self, interaction: discord.Interaction, button: Button):
        self.category = "systems"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    def get_embed(self):
        embeds = {
            "moderation": discord.Embed(
                title="🛡️ Commandes de Modération",
                description=(
                    "**!mute** <membre> <temps> [raison]\n"
                    "**!unmute** <membre>\n"
                    "**!kick** <membre> [raison]\n"
                    "**!ban** <membre> [raison]\n"
                    "**!lock** [salon]\n"
                    "**!unlock** [salon]\n"
                    "**!clear** <nombre>\n"
                    "**!warn** <membre> <raison>\n"
                    "**!warnings** <membre>\n"
                    "**!clearwarn** <membre> [index]\n"
                    "**!slowmode** <secondes>\n"
                    "**!nuke**\n"
                    "**!lockdown**\n"
                    "**!antispam** <on/off>"
                ),
                color=discord.Color.blue()
            ),
            "economy": discord.Embed(
                title="💰 Commandes d'Économie",
                description=(
                    "**!daily** - Récompense journalière\n"
                    "**!balance** [membre]\n"
                    "**!rep** <membre>\n"
                    "**!work** - Gagne de l'argent\n"
                    "**!beg** - Demande l'aumône\n"
                    "**!pay** <membre> <montant>\n"
                    "**!rob** <membre>\n"
                    "**!deposit** <montant>\n"
                    "**!withdraw** <montant>\n"
                    "**!shop** - Boutique\n"
                    "**!buy** <id>\n"
                    "**!inventory**\n"
                    "**!gift** <membre> <item>\n"
                    "**!dice** [montant]\n"
                    "**!slots** [mise]\n"
                    "**!blackjack** [mise]\n"
                    "**!leaderboard**"
                ),
                color=discord.Color.gold()
            ),
            "fun": discord.Embed(
                title="🎮 Commandes Fun & Jeux",
                description=(
                    "**!8ball** <question>\n"
                    "**!joke**\n"
                    "**!quote**\n"
                    "**!ascii** <texte>\n"
                    "**!coinflip**\n"
                    "**!rate** <chose>\n"
                    "**!ship** <membre1> <membre2>\n"
                    "**!choose** <opt1>, <opt2>...\n"
                    "**!rps** <pierre/papier/ciseaux>\n"
                    "**!tictactoe** <membre>\n"
                    "**!hangman**\n"
                    "**!trivia**"
                ),
                color=discord.Color.red()
            ),
            "utility": discord.Embed(
                title="🔧 Commandes Utilitaires",
                description=(
                    "**!userinfo** [membre]\n"
                    "**!serverinfo**\n"
                    "**!serverstats**\n"
                    "**!userstats** [membre]\n"
                    "**!avatar** [membre]\n"
                    "**!banner** [membre]\n"
                    "**!rank** [membre]\n"
                    "**!timer** <temps> [raison]\n"
                    "**!remind** <durée> <message>\n"
                    "**!poll** <question> | <opt1> | <opt2>...\n"
                    "**!embed**\n"
                    "**!announce** <salon> <message>\n"
                    "**!reaction** <msg_id> <emojis>\n"
                    "**!weather** <ville>\n"
                    "**!translate** <langue> <texte>"
                ),
                color=discord.Color.greyple()
            ),
            "systems": discord.Embed(
                title="⚙️ Systèmes & Configuration",
                description=(
                    "**!config** - Menu de configuration\n"
                    "**!ticketsetup** - Configure les tickets\n"
                    "**!tempvoc** <salon> - Vocal temporaire\n"
                    "**!giveaway** <durée> <prix>\n"
                    "**!setlog** <type> <salon>\n"
                    "**!autorole** <role>\n"
                    "**!setrankrole** <niveau> <role>\n"
                    "**!reactionrole** - Reaction roles\n"
                    "**!automod** add/list\n"
                    "**!bvntext/bvnembed**\n"
                    "**!leavetext/leaveembed**"
                ),
                color=discord.Color.purple()
            )
        }
        return embeds[self.category]

@bot.command()
async def help(ctx):
    view = HelpView()
    await ctx.send(embed=view.get_embed(), view=view)

# ============= CONFIG COMMAND (Updated) =============
class ConfigView(View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
    
    @discord.ui.button(label="Salon Bienvenue", style=discord.ButtonStyle.primary, emoji="👋")
    async def welcome_channel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Mentionnez le salon pour les messages de bienvenue:", ephemeral=True)
        
        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=60)
            if msg.channel_mentions:
                server_config[self.guild_id]["welcome_channel"] = msg.channel_mentions[0].id
                await interaction.followup.send(f"✅ Salon de bienvenue défini: {msg.channel_mentions[0].mention}", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Temps écoulé!", ephemeral=True)
    
    @discord.ui.button(label="Salon Départ", style=discord.ButtonStyle.primary, emoji="👋")
    async def leave_channel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Mentionnez le salon pour les messages de départ:", ephemeral=True)
        
        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=60)
            if msg.channel_mentions:
                server_config[self.guild_id]["leave_channel"] = msg.channel_mentions[0].id
                await interaction.followup.send(f"✅ Salon de départ défini: {msg.channel_mentions[0].mention}", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Temps écoulé!", ephemeral=True)
    
    @discord.ui.button(label="Rôle Ticket", style=discord.ButtonStyle.success, emoji="🎫")
    async def ticket_role(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Mentionnez le rôle à notifier pour les tickets:", ephemeral=True)
        
        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=60)
            if msg.role_mentions:
                server_config[self.guild_id]["ticket_role"] = msg.role_mentions[0].id
                await interaction.followup.send(f"✅ Rôle ticket défini: {msg.role_mentions[0].mention}", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Temps écoulé!", ephemeral=True)
    
    @discord.ui.button(label="Voir Config", style=discord.ButtonStyle.secondary, emoji="📋")
    async def view_config(self, interaction: discord.Interaction, button: Button):
        config = server_config[self.guild_id]
        embed = discord.Embed(title="⚙️ Configuration du Serveur", color=discord.Color.blue())
        
        welcome_ch = bot.get_channel(config["welcome_channel"]) if config["welcome_channel"] else None
        leave_ch = bot.get_channel(config["leave_channel"]) if config["leave_channel"] else None
        ticket_role = interaction.guild.get_role(config["ticket_role"]) if config["ticket_role"] else None
        tempvoc_ch = bot.get_channel(config["tempvoc_channel"]) if config["tempvoc_channel"] else None
        
        embed.add_field(name="👋 Salon Bienvenue", value=welcome_ch.mention if welcome_ch else "Non défini", inline=False)
        embed.add_field(name="👋 Salon Départ", value=leave_ch.mention if leave_ch else "Non défini", inline=False)
        embed.add_field(name="🎫 Rôle Ticket", value=ticket_role.mention if ticket_role else "Non défini", inline=False)
        embed.add_field(name="🎤 Vocal Temporaire", value=tempvoc_ch.mention if tempvoc_ch else "Non défini", inline=False)
        embed.add_field(name="🚫 Mots Interdits", value=f"{len(config['automod_words'])} mots", inline=True)
        embed.add_field(name="🛒 Articles Boutique", value=f"{len(config['shop'])} articles", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command()
@commands.has_permissions(administrator=True)
async def config(ctx):
    view = ConfigView(ctx.guild.id)
    embed = discord.Embed(
        title="⚙️ Configuration du Serveur",
        description="Utilisez les boutons ci-dessous pour configurer le bot:",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=view)
# ============= SYSTÈME DE TICKETS =============
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Créer un Ticket", style=discord.ButtonStyle.success, emoji="🎫", custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        config = server_config[interaction.guild.id]
        
        if not config.get("ticket_category"):
            return await interaction.response.send_message("❌ Système de tickets non configuré!", ephemeral=True)
        
        # Vérifier si l'utilisateur a déjà un ticket ouvert
        for ticket in tickets_data[interaction.guild.id]:
            channel = interaction.guild.get_channel(ticket["channel_id"])
            if channel and ticket["user_id"] == interaction.user.id:
                return await interaction.response.send_message(f"❌ Vous avez déjà un ticket ouvert: {channel.mention}", ephemeral=True)
        
        category = interaction.guild.get_channel(config["ticket_category"])
        if not category:
            return await interaction.response.send_message("❌ Catégorie de tickets introuvable!", ephemeral=True)
        
        config["ticket_counter"] += 1
        ticket_number = config["ticket_counter"]
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        if config.get("ticket_role"):
            role = interaction.guild.get_role(config["ticket_role"])
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        ticket_channel = await category.create_text_channel(
            name=f"ticket-{ticket_number}",
            overwrites=overwrites
        )
        
        tickets_data[interaction.guild.id].append({
            "channel_id": ticket_channel.id,
            "user_id": interaction.user.id,
            "created_at": datetime.now()
        })
        
        embed = discord.Embed(
            title=f"🎫 Ticket #{ticket_number}",
            description=f"Bienvenue {interaction.user.mention}!\n\nUn membre du staff va bientôt vous répondre.\nDécrivez votre problème en détail.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Ticket créé par {interaction.user}")
        
        close_view = TicketCloseView()
        await ticket_channel.send(embed=embed, view=close_view)
        
        if config.get("ticket_role"):
            role = interaction.guild.get_role(config["ticket_role"])
            if role:
                await ticket_channel.send(f"{role.mention}")
        
        await interaction.response.send_message(f"✅ Ticket créé: {ticket_channel.mention}", ephemeral=True)
        await log_action(interaction.guild, "modération", f"🎫 Ticket créé par {interaction.user.mention}")

class TicketCloseView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Fermer le Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        for ticket in tickets_data[interaction.guild.id]:
            if ticket["channel_id"] == interaction.channel.id:
                tickets_data[interaction.guild.id].remove(ticket)
                break
        
        await interaction.response.send_message("🔒 Fermeture du ticket dans 5 secondes...")
        await asyncio.sleep(5)
        await log_action(interaction.guild, "modération", f"🎫 Ticket fermé par {interaction.user.mention}")
        await interaction.channel.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def ticketsetup(ctx):
    config = server_config[ctx.guild.id]
    
    embed = discord.Embed(
        title="🎫 Système de Tickets",
        description="Cliquez sur le bouton ci-dessous pour créer un ticket et contacter le staff!",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Serveur: {ctx.guild.name}")
    
    view = TicketView()
    await ctx.send(embed=embed, view=view)
    await ctx.message.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def ticketcategory(ctx, category: discord.CategoryChannel):
    server_config[ctx.guild.id]["ticket_category"] = category.id
    await ctx.send(f"✅ Catégorie des tickets définie: {category.name}")

@bot.command()
@commands.has_permissions(administrator=True)
async def ticketrole(ctx, role: discord.Role):
    server_config[ctx.guild.id]["ticket_role"] = role.id
    await ctx.send(f"✅ Rôle des tickets défini: {role.mention}")

# ============= VOCAL TEMPORAIRE =============
@bot.command()
@commands.has_permissions(administrator=True)
async def tempvoc(ctx, channel: discord.VoiceChannel, category: discord.CategoryChannel = None):
    server_config[ctx.guild.id]["tempvoc_channel"] = channel.id
    if category:
        server_config[ctx.guild.id]["tempvoc_category"] = category.id
    await ctx.send(f"✅ Vocal temporaire configuré sur {channel.mention}")

# ============= MODÉRATION AVANCÉE =============
@bot.command()
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    if seconds < 0 or seconds > 21600:
        return await ctx.send("❌ Le slowmode doit être entre 0 et 21600 secondes (6h)")
    
    await ctx.channel.edit(slowmode_delay=seconds)
    if seconds == 0:
        await ctx.send("✅ Slowmode désactivé!")
    else:
        await ctx.send(f"⏱️ Slowmode activé: {seconds} secondes")
    await log_action(ctx.guild, "modération", f"⏱️ Slowmode défini à {seconds}s dans {ctx.channel.mention} par {ctx.author.mention}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def nuke(ctx):
    confirm_msg = await ctx.send("⚠️ **ATTENTION!** Cette action va supprimer et recréer le salon (tous les messages seront perdus).\nConfirmez en réagissant avec ✅")
    await confirm_msg.add_reaction("✅")
    await confirm_msg.add_reaction("❌")
    
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
    
    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=30, check=check)
        
        if str(reaction.emoji) == "✅":
            position = ctx.channel.position
            new_channel = await ctx.channel.clone(reason=f"Nuke par {ctx.author}")
            await ctx.channel.delete()
            await new_channel.edit(position=position)
            await new_channel.send("💥 Salon nucléarisé!")
            await log_action(ctx.guild, "modération", f"💥 Salon {ctx.channel.name} nuke par {ctx.author.mention}")
        else:
            await confirm_msg.delete()
            await ctx.send("❌ Nuke annulé.")
    except asyncio.TimeoutError:
        await confirm_msg.delete()
        await ctx.send("⏰ Temps écoulé!")

@bot.command()
@commands.has_permissions(administrator=True)
async def lockdown(ctx):
    locked = 0
    for channel in ctx.guild.text_channels:
        try:
            await channel.set_permissions(ctx.guild.default_role, send_messages=False)
            locked += 1
        except:
            pass
    
    await ctx.send(f"🔒 **LOCKDOWN ACTIVÉ!** {locked} salons verrouillés.")
    await log_action(ctx.guild, "modération", f"🔒 Lockdown activé par {ctx.author.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def antispam(ctx, mode: str):
    if mode.lower() == "on":
        server_config[ctx.guild.id]["antispam"]["enabled"] = True
        await ctx.send("✅ Anti-spam activé!")
    elif mode.lower() == "off":
        server_config[ctx.guild.id]["antispam"]["enabled"] = False
        await ctx.send("✅ Anti-spam désactivé!")
    else:
        await ctx.send("❌ Utilisez: !antispam on/off")

# ============= ÉCONOMIE AVANCÉE =============
@bot.command()
async def rob(ctx, member: discord.Member):
    if member == ctx.author:
        return await ctx.send("❌ Vous ne pouvez pas vous voler vous-même!")
    
    if member.bot:
        return await ctx.send("❌ Vous ne pouvez pas voler un bot!")
    
    robber_key = f"{ctx.guild.id}_{ctx.author.id}"
    victim_key = f"{ctx.guild.id}_{member.id}"
    
    robber_data = economy_data[robber_key]
    victim_data = economy_data[victim_key]
    
    if robber_data["money"] < 500:
        return await ctx.send("❌ Vous avez besoin d'au moins 500€ pour tenter un vol!")
    
    if victim_data["money"] < 200:
        return await ctx.send(f"❌ {member.mention} n'a pas assez d'argent à voler!")
    
    success_rate = random.random()
    
    if success_rate > 0.5:
        amount = random.randint(100, min(victim_data["money"], 1000))
        victim_data["money"] -= amount
        robber_data["money"] += amount
        await ctx.send(f"💰 Succès! Vous avez volé {amount}€ à {member.mention}!")
    else:
        fine = random.randint(200, 500)
        robber_data["money"] -= fine
        await ctx.send(f"🚔 Vous vous êtes fait attraper! Amende de {fine}€")

@bot.command()
async def deposit(ctx, amount: str):
    key = f"{ctx.guild.id}_{ctx.author.id}"
    user_data = economy_data[key]
    
    if amount.lower() == "all":
        amount = user_data["money"]
    else:
        amount = int(amount)
    
    if amount > user_data["money"]:
        return await ctx.send("❌ Vous n'avez pas assez d'argent!")
    
    user_data["money"] -= amount
    user_data["bank"] += amount
    await ctx.send(f"🏦 Vous avez déposé {amount}€ à la banque!")

@bot.command()
async def withdraw(ctx, amount: str):
    key = f"{ctx.guild.id}_{ctx.author.id}"
    user_data = economy_data[key]
    
    if amount.lower() == "all":
        amount = user_data["bank"]
    else:
        amount = int(amount)
    
    if amount > user_data["bank"]:
        return await ctx.send("❌ Vous n'avez pas assez d'argent en banque!")
    
    user_data["bank"] -= amount
    user_data["money"] += amount
    await ctx.send(f"🏦 Vous avez retiré {amount}€ de la banque!")

@bot.command()
async def slots(ctx, bet: int = 100):
    key = f"{ctx.guild.id}_{ctx.author.id}"
    user_data = economy_data[key]
    
    if bet > user_data["money"]:
        return await ctx.send("❌ Vous n'avez pas assez d'argent!")
    
    if bet < 50:
        return await ctx.send("❌ Mise minimum: 50€")
    
    symbols = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]
    
    embed = discord.Embed(title="🎰 Machine à Sous", color=discord.Color.gold())
    embed.description = f"**[ {result[0]} | {result[1]} | {result[2]} ]**"
    
    if result[0] == result[1] == result[2]:
        if result[0] == "💎":
            winnings = bet * 10
            embed.add_field(name="💎 JACKPOT! 💎", value=f"Vous gagnez {winnings}€!")
            embed.color = discord.Color.purple()
        elif result[0] == "7️⃣":
            winnings = bet * 7
            embed.add_field(name="🎉 777! 🎉", value=f"Vous gagnez {winnings}€!")
            embed.color = discord.Color.red()
        else:
            winnings = bet * 3
            embed.add_field(name="✨ Trois identiques!", value=f"Vous gagnez {winnings}€!")
            embed.color = discord.Color.green()
        user_data["money"] += winnings
    elif result[0] == result[1] or result[1] == result[2]:
        winnings = bet
        embed.add_field(name="👍 Deux identiques", value=f"Vous récupérez votre mise: {winnings}€")
        embed.color = discord.Color.blue()
    else:
        user_data["money"] -= bet
        embed.add_field(name="❌ Perdu!", value=f"Vous perdez {bet}€")
        embed.color = discord.Color.red()
    
    await ctx.send(embed=embed)

@bot.command()
async def blackjack(ctx, bet: int = 100):
    key = f"{ctx.guild.id}_{ctx.author.id}"
    user_data = economy_data[key]
    
    if bet > user_data["money"]:
        return await ctx.send("❌ Vous n'avez pas assez d'argent!")
    
    if bet < 50:
        return await ctx.send("❌ Mise minimum: 50€")
    
    cards = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"] * 4
    
    def card_value(hand):
        value = 0
        aces = 0
        for card in hand:
            if card in ["J", "Q", "K"]:
                value += 10
            elif card == "A":
                aces += 1
                value += 11
            else:
                value += int(card)
        
        while value > 21 and aces:
            value -= 10
            aces -= 1
        
        return value
    
    player_hand = [random.choice(cards), random.choice(cards)]
    dealer_hand = [random.choice(cards), random.choice(cards)]
    
    player_value = card_value(player_hand)
    dealer_value = card_value(dealer_hand)
    
    embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.green())
    embed.add_field(name="Vos cartes", value=f"{' '.join(player_hand)} (Total: {player_value})", inline=False)
    embed.add_field(name="Carte du croupier", value=f"{dealer_hand[0]} ?", inline=False)
    
    if player_value == 21:
        winnings = int(bet * 2.5)
        user_data["money"] += winnings
        embed.add_field(name="🎉 BLACKJACK!", value=f"Vous gagnez {winnings}€!", inline=False)
        return await ctx.send(embed=embed)
    
    class BlackjackView(View):
        def __init__(self):
            super().__init__(timeout=60)
            self.value = None
        
        @discord.ui.button(label="Tirer", style=discord.ButtonStyle.success, emoji="🎴")
        async def hit(self, interaction: discord.Interaction, button: Button):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("❌ Ce n'est pas votre partie!", ephemeral=True)
            
            player_hand.append(random.choice(cards))
            player_value = card_value(player_hand)
            
            if player_value > 21:
                user_data["money"] -= bet
                embed.clear_fields()
                embed.add_field(name="Vos cartes", value=f"{' '.join(player_hand)} (Total: {player_value})", inline=False)
                embed.add_field(name="❌ BUST!", value=f"Vous perdez {bet}€", inline=False)
                embed.color = discord.Color.red()
                self.stop()
                await interaction.response.edit_message(embed=embed, view=None)
            else:
                embed.clear_fields()
                embed.add_field(name="Vos cartes", value=f"{' '.join(player_hand)} (Total: {player_value})", inline=False)
                embed.add_field(name="Carte du croupier", value=f"{dealer_hand[0]} ?", inline=False)
                await interaction.response.edit_message(embed=embed, view=self)
        
        @discord.ui.button(label="Rester", style=discord.ButtonStyle.danger, emoji="✋")
        async def stand(self, interaction: discord.Interaction, button: Button):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("❌ Ce n'est pas votre partie!", ephemeral=True)
            
            while card_value(dealer_hand) < 17:
                dealer_hand.append(random.choice(cards))
            
            dealer_value = card_value(dealer_hand)
            player_value = card_value(player_hand)
            
            embed.clear_fields()
            embed.add_field(name="Vos cartes", value=f"{' '.join(player_hand)} (Total: {player_value})", inline=False)
            embed.add_field(name="Cartes du croupier", value=f"{' '.join(dealer_hand)} (Total: {dealer_value})", inline=False)
            
            if dealer_value > 21 or player_value > dealer_value:
                winnings = bet * 2
                user_data["money"] += winnings
                embed.add_field(name="✅ VICTOIRE!", value=f"Vous gagnez {winnings}€!", inline=False)
                embed.color = discord.Color.green()
            elif player_value == dealer_value:
                embed.add_field(name="🤝 ÉGALITÉ", value="Mise rendue", inline=False)
                embed.color = discord.Color.blue()
            else:
                user_data["money"] -= bet
                embed.add_field(name="❌ DÉFAITE", value=f"Vous perdez {bet}€", inline=False)
                embed.color = discord.Color.red()
            
            self.stop()
            await interaction.response.edit_message(embed=embed, view=None)
    
    view = BlackjackView()
    await ctx.send(embed=embed, view=view)

@bot.command()
async def inventory(ctx, member: discord.Member = None):
    member = member or ctx.author
    key = f"{ctx.guild.id}_{member.id}"
    items = economy_data[key]["inventory"]
    
    if not items:
        return await ctx.send(f"📦 {member.mention} n'a aucun objet dans son inventaire!")
    
    embed = discord.Embed(title=f"📦 Inventaire de {member.name}", color=discord.Color.blue())
    for item in items:
        embed.add_field(name=item["name"], value=f"ID: {item['id']}", inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def gift(ctx, member: discord.Member, item_id: int):
    if member == ctx.author:
        return await ctx.send("❌ Vous ne pouvez pas vous offrir un cadeau!")
    
    sender_key = f"{ctx.guild.id}_{ctx.author.id}"
    receiver_key = f"{ctx.guild.id}_{member.id}"
    
    item = next((i for i in economy_data[sender_key]["inventory"] if i["id"] == item_id), None)
    
    if not item:
        return await ctx.send("❌ Vous ne possédez pas cet objet!")
    
    economy_data[sender_key]["inventory"].remove(item)
    economy_data[receiver_key]["inventory"].append(item)
    
    await ctx.send(f"🎁 Vous avez offert **{item['name']}** à {member.mention}!")

# ============= JEUX =============
@bot.command()
async def rps(ctx, choice: str):
    choices = {"pierre": "🪨", "papier": "📄", "ciseaux": "✂️"}
    
    if choice.lower() not in choices:
        return await ctx.send("❌ Choisissez entre: pierre, papier, ciseaux")
    
    bot_choice = random.choice(list(choices.keys()))
    
    embed = discord.Embed(title="🎮 Pierre-Papier-Ciseaux", color=discord.Color.blue())
    embed.add_field(name="Vous", value=f"{choices[choice.lower()]}", inline=True)
    embed.add_field(name="Bot", value=f"{choices[bot_choice]}", inline=True)
    
    if choice.lower() == bot_choice:
        result = "🤝 Égalité!"
    elif (choice.lower() == "pierre" and bot_choice == "ciseaux") or \
         (choice.lower() == "papier" and bot_choice == "pierre") or \
         (choice.lower() == "ciseaux" and bot_choice == "papier"):
        result = "✅ Vous gagnez!"
    else:
        result = "❌ Vous perdez!"
    
    embed.add_field(name="Résultat", value=result, inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def tictactoe(ctx, member: discord.Member):
    if member == ctx.author:
        return await ctx.send("❌ Vous ne pouvez pas jouer contre vous-même!")
    
    if member.bot:
        return await ctx.send("❌ Vous ne pouvez pas jouer contre un bot!")
    
    board = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
    current_player = ctx.author
    players = {ctx.author: "❌", member: "⭕"}
    
    def check_winner():
        winning_combos = [
            [0,1,2], [3,4,5], [6,7,8],  # rows
            [0,3,6], [1,4,7], [2,5,8],  # columns
            [0,4,8], [2,4,6]  # diagonals
        ]
        for combo in winning_combos:
            if board[combo[0]] == board[combo[1]] == board[combo[2]]:
                if board[combo[0]] in ["❌", "⭕"]:
                    return True
        return False
    
    def is_board_full():
        return all(cell in ["❌", "⭕"] for cell in board)
    
    class TicTacToeButton(Button):
        def __init__(self, position):
            super().__init__(style=discord.ButtonStyle.secondary, label=str(position+1), custom_id=str(position))
            self.position = position
        
        async def callback(self, interaction: discord.Interaction):
            nonlocal current_player
            
            if interaction.user != current_player:
                return await interaction.response.send_message("❌ Ce n'est pas votre tour!", ephemeral=True)
            
            if board[self.position] in ["❌", "⭕"]:
                return await interaction.response.send_message("❌ Case déjà prise!", ephemeral=True)
            
            board[self.position] = players[current_player]
            self.label = players[current_player]
            self.disabled = True
            
            if check_winner():
                for child in view.children:
                    child.disabled = True
                embed.description = f"🎉 {current_player.mention} a gagné!"
                embed.color = discord.Color.green()
                await interaction.response.edit_message(embed=embed, view=view)
                return
            
            if is_board_full():
                for child in view.children:
                    child.disabled = True
                embed.description = "🤝 Match nul!"
                embed.color = discord.Color.blue()
                await interaction.response.edit_message(embed=embed, view=view)
                return
            
            current_player = member if current_player == ctx.author else ctx.author
            embed.description = f"Tour de {current_player.mention} ({players[current_player]})"
            await interaction.response.edit_message(embed=embed, view=view)
    
    view = View(timeout=300)
    for i in range(9):
        view.add_item(TicTacToeButton(i))
    
    embed = discord.Embed(
        title="⭕ Morpion ❌",
        description=f"Tour de {current_player.mention} ({players[current_player]})",
        color=discord.Color.blue()
    )
    embed.add_field(name="Joueurs", value=f"{ctx.author.mention} (❌) vs {member.mention} (⭕)", inline=False)
    
    await ctx.send(embed=embed, view=view)

# Continue dans PARTIE 3...
# ============= PARTIE 3/3 - Hangman, Trivia, Stats, Giveaways, Utilitaires =============

# ============= HANGMAN =============
hangman_games = {}

@bot.command()
async def hangman(ctx):
    if ctx.author.id in hangman_games:
        return await ctx.send("❌ Vous avez déjà une partie en cours!")
    
    words = ["python", "discord", "moderation", "economie", "giveaway", "ticket", "serveur", "commande"]
    word = random.choice(words).upper()
    
    hangman_games[ctx.author.id] = {
        "word": word,
        "guessed": ["_"] * len(word),
        "attempts": 6,
        "letters_used": []
    }
    
    embed = discord.Embed(title="🎮 Pendu", color=discord.Color.blue())
    embed.add_field(name="Mot", value=" ".join(hangman_games[ctx.author.id]["guessed"]), inline=False)
    embed.add_field(name="Tentatives restantes", value=f"{hangman_games[ctx.author.id]['attempts']} ❤️", inline=False)
    embed.set_footer(text="Tapez une lettre pour deviner!")
    
    await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and len(m.content) == 1
    
    while ctx.author.id in hangman_games:
        try:
            msg = await bot.wait_for('message', check=check, timeout=60)
            letter = msg.content.upper()
            
            game = hangman_games[ctx.author.id]
            
            if letter in game["letters_used"]:
                await ctx.send("❌ Lettre déjà utilisée!", delete_after=3)
                continue
            
            game["letters_used"].append(letter)
            
            if letter in game["word"]:
                for i, char in enumerate(game["word"]):
                    if char == letter:
                        game["guessed"][i] = letter
                
                if "_" not in game["guessed"]:
                    embed = discord.Embed(title="🎉 VICTOIRE!", color=discord.Color.green())
                    embed.add_field(name="Mot", value=" ".join(game["guessed"]), inline=False)
                    await ctx.send(embed=embed)
                    del hangman_games[ctx.author.id]
                    break
            else:
                game["attempts"] -= 1
                
                if game["attempts"] == 0:
                    embed = discord.Embed(title="💀 DÉFAITE!", color=discord.Color.red())
                    embed.add_field(name="Le mot était", value=game["word"], inline=False)
                    await ctx.send(embed=embed)
                    del hangman_games[ctx.author.id]
                    break
            
            embed = discord.Embed(title="🎮 Pendu", color=discord.Color.blue())
            embed.add_field(name="Mot", value=" ".join(game["guessed"]), inline=False)
            embed.add_field(name="Tentatives restantes", value=f"{game['attempts']} ❤️", inline=False)
            embed.add_field(name="Lettres utilisées", value=" ".join(game["letters_used"]), inline=False)
            await ctx.send(embed=embed)
            
        except asyncio.TimeoutError:
            await ctx.send("⏰ Temps écoulé! Partie annulée.")
            if ctx.author.id in hangman_games:
                del hangman_games[ctx.author.id]
            break

# ============= TRIVIA =============
@bot.command()
async def trivia(ctx):
    questions = [
        {"q": "Quelle est la capitale de la France?", "a": ["paris"], "points": 10},
        {"q": "Combien font 2+2?", "a": ["4", "quatre"], "points": 5},
        {"q": "Quel est le langage de programmation de ce bot?", "a": ["python"], "points": 15},
        {"q": "En quelle année Discord a été créé?", "a": ["2015"], "points": 20},
        {"q": "Quel est l'animal le plus rapide du monde?", "a": ["guépard", "guepard"], "points": 15}
    ]
    
    question = random.choice(questions)
    
    embed = discord.Embed(title="❓ Trivia", color=discord.Color.gold())
    embed.add_field(name="Question", value=question["q"], inline=False)
    embed.add_field(name="Points", value=f"🏆 {question['points']}", inline=False)
    embed.set_footer(text="Vous avez 15 secondes pour répondre!")
    
    await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=15)
        
        if msg.content.lower().strip() in question["a"]:
            key = f"{ctx.guild.id}_{ctx.author.id}"
            economy_data[key]["money"] += question["points"]
            
            embed = discord.Embed(title="✅ BONNE RÉPONSE!", color=discord.Color.green())
            embed.add_field(name="Récompense", value=f"+{question['points']}€", inline=False)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title="❌ MAUVAISE RÉPONSE", color=discord.Color.red())
            embed.add_field(name="La réponse était", value=question["a"][0], inline=False)
            await ctx.send(embed=embed)
            
    except asyncio.TimeoutError:
        await ctx.send(f"⏰ Temps écoulé! La réponse était: **{question['a'][0]}**")

# ============= STATISTIQUES =============
@bot.command()
async def serverstats(ctx):
    guild = ctx.guild
    
    total_members = guild.member_count
    humans = len([m for m in guild.members if not m.bot])
    bots = len([m for m in guild.members if m.bot])
    
    online = len([m for m in guild.members if m.status == discord.Status.online])
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    roles = len(guild.roles)
    
    embed = discord.Embed(title=f"📊 Stats de {guild.name}", color=discord.Color.blue())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    
    embed.add_field(name="👥 Membres", value=f"**Total:** {total_members}\n**Humains:** {humans}\n**Bots:** {bots}", inline=True)
    embed.add_field(name="🟢 En ligne", value=f"{online} membres", inline=True)
    embed.add_field(name="📅 Créé le", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="💬 Salons Textuels", value=text_channels, inline=True)
    embed.add_field(name="🎤 Salons Vocaux", value=voice_channels, inline=True)
    embed.add_field(name="🎭 Rôles", value=roles, inline=True)
    embed.add_field(name="👑 Propriétaire", value=guild.owner.mention, inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def userstats(ctx, member: discord.Member = None):
    member = member or ctx.author
    key = f"{ctx.guild.id}_{member.id}"
    stats = stats_data[key]
    
    embed = discord.Embed(title=f"📊 Stats de {member.name}", color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    
    voice_hours = stats["voice_time"] / 3600
    embed.add_field(name="💬 Messages Envoyés", value=f"{stats['messages']}", inline=True)
    embed.add_field(name="🎤 Temps Vocal", value=f"{voice_hours:.1f}h", inline=True)
    embed.add_field(name="📅 Rejoint le", value=member.joined_at.strftime("%d/%m/%Y"), inline=True)
    
    user_data = economy_data[key]
    embed.add_field(name="💰 Argent", value=f"{user_data['money']}€", inline=True)
    embed.add_field(name="🏆 Niveau", value=f"{user_data['level']}", inline=True)
    embed.add_field(name="⭐ Réputation", value=f"{user_data['rep']}", inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    key = f"{ctx.guild.id}_{member.id}"
    user_data = economy_data[key]
    
    # Créer une carte de rang simple
    embed = discord.Embed(title=f"📊 Rang de {member.name}", color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    
    xp_needed = user_data['level'] * 100
    progress = (user_data['xp'] / xp_needed) * 100
    bar_length = 20
    filled = int((progress / 100) * bar_length)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    embed.add_field(name="🏆 Niveau", value=user_data['level'], inline=True)
    embed.add_field(name="✨ XP", value=f"{user_data['xp']}/{xp_needed}", inline=True)
    embed.add_field(name="💰 Argent", value=f"{user_data['money']}€", inline=True)
    embed.add_field(name="Progression", value=f"{bar} {progress:.1f}%", inline=False)
    
    await ctx.send(embed=embed)

# ============= GIVEAWAY =============
@bot.command()
@commands.has_permissions(manage_guild=True)
async def giveaway(ctx, duration: str, *, prize: str):
    # Parse duration (ex: 1h, 30m, 1d)
    time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    time_value = int(duration[:-1])
    time_unit = duration[-1].lower()
    
    if time_unit not in time_units:
        return await ctx.send("❌ Format invalide! Utilisez: s, m, h, d (ex: 1h, 30m)")
    
    seconds = time_value * time_units[time_unit]
    end_time = datetime.now() + timedelta(seconds=seconds)
    
    embed = discord.Embed(title="🎉 GIVEAWAY!", color=discord.Color.purple())
    embed.add_field(name="Prix", value=prize, inline=False)
    embed.add_field(name="Durée", value=duration, inline=True)
    embed.add_field(name="Se termine", value=end_time.strftime("%d/%m/%Y %H:%M"), inline=True)
    embed.set_footer(text="Réagissez avec 🎉 pour participer!")
    
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎉")
    
    giveaways_data.append({
        "message_id": msg.id,
        "channel_id": ctx.channel.id,
        "prize": prize,
        "end_time": end_time
    })

# ============= POLL =============
@bot.command()
async def poll(ctx, *, content: str):
    if "|" not in content:
        return await ctx.send("❌ Format: !poll Question | Option1 | Option2 ...")
    
    parts = [p.strip() for p in content.split("|")]
    question = parts[0]
    options = parts[1:]
    
    if len(options) < 2 or len(options) > 10:
        return await ctx.send("❌ Il faut entre 2 et 10 options!")
    
    embed = discord.Embed(title="📊 Sondage", description=question, color=discord.Color.blue())
    
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, option in enumerate(options):
        embed.add_field(name=f"{emojis[i]} Option {i+1}", value=option, inline=False)
    
    embed.set_footer(text=f"Sondage créé par {ctx.author}")
    
    poll_msg = await ctx.send(embed=embed)
    
    for i in range(len(options)):
        await poll_msg.add_reaction(emojis[i])

# ============= REMINDERS =============
@bot.command()
async def remind(ctx, duration: str, *, message: str):
    time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    time_value = int(duration[:-1])
    time_unit = duration[-1].lower()
    
    if time_unit not in time_units:
        return await ctx.send("❌ Format invalide! Utilisez: s, m, h, d (ex: 1h, 30m)")
    
    seconds = time_value * time_units[time_unit]
    
    await ctx.send(f"⏰ Je vous rappellerai dans {duration}!")
    await asyncio.sleep(seconds)
    
    embed = discord.Embed(title="⏰ RAPPEL", description=message, color=discord.Color.orange())
    await ctx.send(f"{ctx.author.mention}", embed=embed)

# ============= EMBED GENERATOR =============
@bot.command()
@commands.has_permissions(manage_messages=True)
async def embed(ctx):
    await ctx.send("**Générateur d'Embed**\nEnvoyez le titre de l'embed:")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        title_msg = await bot.wait_for('message', check=check, timeout=60)
        title = title_msg.content
        
        await ctx.send("Envoyez la description de l'embed:")
        desc_msg = await bot.wait_for('message', check=check, timeout=60)
        description = desc_msg.content
        
        await ctx.send("Envoyez la couleur (hex) ou 'skip':")
        color_msg = await bot.wait_for('message', check=check, timeout=60)
        
        if color_msg.content.lower() == "skip":
            color = discord.Color.blue()
        else:
            color = discord.Color(int(color_msg.content.replace("#", ""), 16))
        
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=f"Créé par {ctx.author}")
        
        await ctx.send("✅ Aperçu de l'embed:", embed=embed)
        await ctx.send("Réagissez avec ✅ pour envoyer ou ❌ pour annuler")
        
        preview = await ctx.channel.fetch_message((await ctx.channel.history(limit=1).flatten())[0].id)
        await preview.add_reaction("✅")
        await preview.add_reaction("❌")
        
        def reaction_check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"]
        
        reaction, user = await bot.wait_for('reaction_add', check=reaction_check, timeout=60)
        
        if str(reaction.emoji) == "✅":
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Annulé!")
            
    except asyncio.TimeoutError:
        await ctx.send("⏰ Temps écoulé!")

# ============= ANNOUNCE =============
@bot.command()
@commands.has_permissions(manage_messages=True)
async def announce(ctx, channel: discord.TextChannel, *, message: str):
    embed = discord.Embed(description=message, color=discord.Color.blue())
    embed.set_author(name=f"Annonce de {ctx.author}", icon_url=ctx.author.display_avatar.url)
    embed.timestamp = datetime.now()
    
    await channel.send(embed=embed)
    await ctx.send(f"✅ Annonce envoyée dans {channel.mention}")

# ============= REACTION =============
@bot.command()
@commands.has_permissions(manage_messages=True)
async def reaction(ctx, message_id: int, *emojis):
    try:
        msg = await ctx.channel.fetch_message(message_id)
        for emoji in emojis:
            await msg.add_reaction(emoji)
        await ctx.send(f"✅ Réactions ajoutées!")
    except:
        await ctx.send("❌ Message introuvable!")

# ============= AVATAR & BANNER =============
@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    
    embed = discord.Embed(title=f"Avatar de {member.name}", color=member.color)
    embed.set_image(url=member.display_avatar.url)
    embed.add_field(name="Télécharger", value=f"[Clique ici]({member.display_avatar.url})")
    
    await ctx.send(embed=embed)

@bot.command()
async def banner(ctx, member: discord.Member = None):
    member = member or ctx.author
    
    user = await bot.fetch_user(member.id)
    
    if user.banner:
        embed = discord.Embed(title=f"Bannière de {member.name}", color=member.color)
        embed.set_image(url=user.banner.url)
        embed.add_field(name="Télécharger", value=f"[Clique ici]({user.banner.url})")
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ {member.mention} n'a pas de bannière!")

# ============= WEATHER =============
@bot.command()
async def weather(ctx, *, city: str):
    await ctx.send("⚠️ Fonctionnalité Weather nécessite une API (OpenWeatherMap). Configurez votre clé API!")

# ============= TRANSLATE =============
@bot.command()
async def translate(ctx, target_lang: str, *, text: str):
    await ctx.send("⚠️ Fonctionnalité Translate nécessite une API (Google Translate). Configurez votre clé API!")

# ============= TIMER =============
@bot.command()
async def timer(ctx, duration: str, *, reason: str = "Timer"):
    time_units = {"s": 1, "m": 60, "h": 3600}
    time_value = int(duration[:-1])
    time_unit = duration[-1].lower()
    
    if time_unit not in time_units:
        return await ctx.send("❌ Format invalide! Utilisez: s, m, h (ex: 1h, 30m)")
    
    seconds = time_value * time_units[time_unit]
    
    embed = discord.Embed(title="⏱️ Timer démarré!", color=discord.Color.blue())
    embed.add_field(name="Durée", value=duration, inline=True)
    embed.add_field(name="Raison", value=reason, inline=True)
    
    await ctx.send(embed=embed)
    await asyncio.sleep(seconds)
    
    await ctx.send(f"⏰ {ctx.author.mention} Timer terminé: **{reason}**")

# ============= COINFLIP =============
@bot.command()
async def coinflip(ctx):
    result = random.choice(["Pile", "Face"])
    emoji = "🪙" if result == "Pile" else "💿"
    
    embed = discord.Embed(title="🪙 Pile ou Face", color=discord.Color.gold())
    embed.add_field(name="Résultat", value=f"{emoji} **{result}**")
    
    await ctx.send(embed=embed)

# ============= DICE =============
@bot.command()
async def dice(ctx, bet: int = 0):
    result = random.randint(1, 6)
    
    embed = discord.Embed(title="🎲 Lancer de Dé", color=discord.Color.blue())
    embed.add_field(name="Résultat", value=f"**{result}**")
    
    if bet > 0:
        key = f"{ctx.guild.id}_{ctx.author.id}"
        user_data = economy_data[key]
        
        if bet > user_data["money"]:
            return await ctx.send("❌ Vous n'avez pas assez d'argent!")
        
        if result >= 4:
            winnings = bet * 2
            user_data["money"] += winnings
            embed.add_field(name="✅ Gagné!", value=f"+{winnings}€")
            embed.color = discord.Color.green()
        else:
            user_data["money"] -= bet
            embed.add_field(name="❌ Perdu!", value=f"-{bet}€")
            embed.color = discord.Color.red()
    
    await ctx.send(embed=embed)

# ============= SETRANKROLE =============
@bot.command()
@commands.has_permissions(administrator=True)
async def setrankrole(ctx, level: int, role: discord.Role):
    server_config[ctx.guild.id]["level_roles"][level] = role.id
    await ctx.send(f"✅ Rôle {role.mention} sera donné au niveau {level}")

# ============= REACTIONROLE SYSTEM =============
reaction_roles = defaultdict(dict)

@bot.command()
@commands.has_permissions(administrator=True)
async def reactionrole(ctx):
    await ctx.send("**Configuration Reaction Roles**\n1. Envoyez l'ID du message\n2. Ensuite: emoji role (ex: 🎮 @Gamer)")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg_id_msg = await bot.wait_for('message', check=check, timeout=60)
        msg_id = int(msg_id_msg.content)
        
        try:
            message = await ctx.channel.fetch_message(msg_id)
        except:
            return await ctx.send("❌ Message introuvable!")
        
        await ctx.send("Envoyez les reaction roles (emoji @role), ou 'done' pour terminer:")
        
        while True:
            response = await bot.wait_for('message', check=check, timeout=120)
            
            if response.content.lower() == "done":
                break
            
            parts = response.content.split()
            if len(parts) < 2:
                await ctx.send("❌ Format: emoji @role")
                continue
            
            emoji = parts[0]
            role = response.role_mentions[0] if response.role_mentions else None
            
            if not role:
                await ctx.send("❌ Mentionnez un rôle!")
                continue
            
            reaction_roles[msg_id][emoji] = role.id
            await message.add_reaction(emoji)
            await ctx.send(f"✅ {emoji} → {role.mention} ajouté!")
        
        await ctx.send("✅ Configuration terminée!")
        
    except asyncio.TimeoutError:
        await ctx.send("⏰ Temps écoulé!")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    
    if payload.message_id in reaction_roles:
        emoji = str(payload.emoji)
        if emoji in reaction_roles[payload.message_id]:
            guild = bot.get_guild(payload.guild_id)
            role = guild.get_role(reaction_roles[payload.message_id][emoji])
            member = guild.get_member(payload.user_id)
            
            if role and member:
                await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.message_id in reaction_roles:
        emoji = str(payload.emoji)
        if emoji in reaction_roles[payload.message_id]:
            guild = bot.get_guild(payload.guild_id)
            role = guild.get_role(reaction_roles[payload.message_id][emoji])
            member = guild.get_member(payload.user_id)
            
            if role and member:
                await member.remove_roles(role)

# ============= LEADERBOARD =============
@bot.command()
async def leaderboard(ctx, mode: str = "money"):
    if mode not in ["money", "level", "xp"]:
        return await ctx.send("❌ Modes disponibles: money, level, xp")
    
    guild_members = [f"{ctx.guild.id}_{m.id}" for m in ctx.guild.members if not m.bot]
    
    sorted_data = sorted(
        [(key, economy_data[key]) for key in guild_members if key in economy_data],
        key=lambda x: x[1][mode],
        reverse=True
    )[:10]
    
    embed = discord.Embed(title=f"🏆 Classement - {mode.upper()}", color=discord.Color.gold())
    
    medals = ["🥇", "🥈", "🥉"]
    
    for i, (key, data) in enumerate(sorted_data):
        user_id = int(key.split("_")[1])
        member = ctx.guild.get_member(user_id)
        
        if member:
            medal = medals[i] if i < 3 else f"{i+1}."
            value = f"{data[mode]}{'€' if mode == 'money' else ''}"
            embed.add_field(
                name=f"{medal} {member.name}",
                value=value,
                inline=False
            )
    
    await ctx.send(embed=embed)

# ============= FINAL TOKEN START =============
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.getenv('DISCORD_TOKEN')
    
    if not TOKEN:
        print("❌ ERREUR: Token Discord manquant!")
        print("Ajoutez DISCORD_TOKEN dans vos variables d'environnement")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"❌ Erreur de démarrage: {e}")
