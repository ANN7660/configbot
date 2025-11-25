import disnake as discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Select
import asyncio
import aiohttp
import json
import os
from datetime import datetime, timedelta
import random
from collections import defaultdict
from flask import Flask
from threading import Thread

# ============= CONFIGURATION =============
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ============= DONNÉES =============
economy_data = defaultdict(lambda: {"money": 0, "xp": 0, "level": 1, "rep": 0, "daily_claimed": None, "work_claimed": None})
warnings_data = defaultdict(list)
server_config = defaultdict(lambda: {
    "welcome_channel": None,
    "leave_channel": None,
    "welcome_msg": "Bienvenue {user} sur {server}!",
    "leave_msg": "{user} a quitté {server}",
    "welcome_embed": None,
    "leave_embed": None,
    "automod_words": [],
    "shop": []
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
    await bot.change_presence(activity=discord.Game(name="!help"))

@tasks.loop(hours=23)
async def auto_reboot():
    print("🔄 Auto-reboot check...")

@bot.event
async def on_member_join(member):
    config = server_config[member.guild.id]
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

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # Automod
    config = server_config[message.guild.id]
    for word in config["automod_words"]:
        if word.lower() in message.content.lower():
            await message.delete()
            await message.channel.send(f"{message.author.mention}, ce mot est interdit!", delete_after=5)
            return
    
    # XP système
    user_data = economy_data[f"{message.guild.id}_{message.author.id}"]
    xp_gain = random.randint(10, 25)
    user_data["xp"] += xp_gain
    
    xp_needed = user_data["level"] * 100
    if user_data["xp"] >= xp_needed:
        user_data["level"] += 1
        user_data["xp"] = 0
        await message.channel.send(f"🎉 {message.author.mention} a atteint le niveau {user_data['level']}!")
    
    await bot.process_commands(message)

# ============= HELP COMMAND =============
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
    
    def get_embed(self):
        embeds = {
            "moderation": discord.Embed(
                title="🛡️ Commandes de Modération",
                description=(
                    "**!mute** `<membre> <temps> [raison]` - Met en sourdine un membre\n"
                    "**!unmute** `<membre>` - Retire la sourdine\n"
                    "**!kick** `<membre> [raison]` - Expulse un membre\n"
                    "**!ban** `<membre> [raison]` - Banni un membre\n"
                    "**!lock** `[salon]` - Verrouille un salon\n"
                    "**!unlock** `[salon]` - Déverrouille un salon\n"
                    "**!clear** `<nombre>` - Supprime des messages\n"
                    "**!warn** `<membre> <raison>` - Avertit un membre\n"
                    "**!warnings** `<membre>` - Affiche les avertissements\n"
                    "**!clearwarn** `<membre> [index]` - Retire un avertissement"
                ),
                color=discord.Color.blue()
            ),
            "economy": discord.Embed(
                title="💰 Commandes d'Économie",
                description=(
                    "**!daily** - Récompense journalière\n"
                    "**!balance** `[membre]` - Affiche la monnaie\n"
                    "**!rep** `<membre>` - Donne de la réputation\n"
                    "**!shop** - Affiche la boutique\n"
                    "**!buy** `<id>` - Achète un rôle\n"
                    "**!dice** `[montant]` - Jeu de dés\n"
                    "**!pay** `<membre> <montant>` - Transfère de l'argent\n"
                    "**!leaderboard** - Classement des joueurs\n"
                    "**!work** - Gagne de l'argent\n"
                    "**!beg** - Demande l'aumône"
                ),
                color=discord.Color.gold()
            ),
            "fun": discord.Embed(
                title="🎮 Commandes Fun",
                description=(
                    "**!8ball** `<question>` - Boule magique\n"
                    "**!joke** - Envoie une blague\n"
                    "**!quote** - Citation inspirante\n"
                    "**!ascii** `<texte>` - Convertit en ASCII art\n"
                    "**!coinflip** - Lance une pièce\n"
                    "**!rate** `<chose>` - Évalue quelque chose\n"
                    "**!ship** `<membre1> <membre2>` - Calcule l'affinité\n"
                    "**!choose** `<opt1>, <opt2>...` - Aide à choisir"
                ),
                color=discord.Color.red()
            ),
            "utility": discord.Embed(
                title="🔧 Commandes Utilitaires",
                description=(
                    "**!userinfo** `[membre]` - Info sur un membre\n"
                    "**!serverinfo** - Info sur le serveur\n"
                    "**!timer** `<temps> [raison]` - Minuteur\n"
                    "**!automod** `add/list` - Gère les mots interdits\n"
                    "**!config** - Menu de configuration\n"
                    "**!bvntext** `[message]` - Message de bienvenue\n"
                    "**!bvnembed** `[titre | description]` - Embed de bienvenue\n"
                    "**!leavetext** `[message]` - Message de départ\n"
                    "**!leaveembed** `[titre | description]` - Embed de départ"
                ),
                color=discord.Color.greyple()
            )
        }
        return embeds[self.category]

@bot.command()
async def help(ctx):
    view = HelpView()
    await ctx.send(embed=view.get_embed(), view=view)

# ============= CONFIG COMMAND =============
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
    
    @discord.ui.button(label="Voir Config", style=discord.ButtonStyle.success, emoji="📋")
    async def view_config(self, interaction: discord.Interaction, button: Button):
        config = server_config[self.guild_id]
        embed = discord.Embed(title="⚙️ Configuration du Serveur", color=discord.Color.blue())
        
        welcome_ch = bot.get_channel(config["welcome_channel"]) if config["welcome_channel"] else None
        leave_ch = bot.get_channel(config["leave_channel"]) if config["leave_channel"] else None
        
        embed.add_field(name="Salon Bienvenue", value=welcome_ch.mention if welcome_ch else "Non défini", inline=False)
        embed.add_field(name="Salon Départ", value=leave_ch.mention if leave_ch else "Non défini", inline=False)
        embed.add_field(name="Mots Interdits", value=f"{len(config['automod_words'])} mots", inline=False)
        embed.add_field(name="Articles Boutique", value=f"{len(config['shop'])} articles", inline=False)
        
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

# ============= MODERATION COMMANDS =============
@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, duration: str, *, reason="Aucune raison"):
    time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    unit = duration[-1]
    if unit not in time_units:
        return await ctx.send("❌ Format: 10s, 5m, 2h, 1d")
    
    amount = int(duration[:-1])
    seconds = amount * time_units[unit]
    
    await member.timeout(timedelta(seconds=seconds), reason=reason)
    embed = discord.Embed(title="🔇 Membre Muté", color=discord.Color.orange())
    embed.add_field(name="Membre", value=member.mention, inline=False)
    embed.add_field(name="Durée", value=duration, inline=False)
    embed.add_field(name="Raison", value=reason, inline=False)
    embed.add_field(name="Modérateur", value=ctx.author.mention, inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(f"✅ {member.mention} n'est plus en sourdine.")

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Aucune raison"):
    await member.kick(reason=reason)
    embed = discord.Embed(title="👢 Membre Expulsé", color=discord.Color.red())
    embed.add_field(name="Membre", value=f"{member}", inline=False)
    embed.add_field(name="Raison", value=reason, inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison"):
    await member.ban(reason=reason)
    embed = discord.Embed(title="🔨 Membre Banni", color=discord.Color.dark_red())
    embed.add_field(name="Membre", value=f"{member}", inline=False)
    embed.add_field(name="Raison", value=reason, inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(f"🔒 {channel.mention} est maintenant verrouillé.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send(f"🔓 {channel.mention} est maintenant déverrouillé.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    deleted = await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"🗑️ {len(deleted)-1} messages supprimés.")
    await asyncio.sleep(3)
    await msg.delete()

@bot.command()
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason):
    key = f"{ctx.guild.id}_{member.id}"
    warnings_data[key].append({
        "reason": reason,
        "moderator": str(ctx.author),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    await ctx.send(f"⚠️ {member.mention} a reçu un avertissement.\n**Raison:** {reason}")

@bot.command()
async def warnings(ctx, member: discord.Member):
    key = f"{ctx.guild.id}_{member.id}"
    warns = warnings_data[key]
    
    if not warns:
        return await ctx.send(f"{member.mention} n'a aucun avertissement.")
    
    embed = discord.Embed(title=f"⚠️ Avertissements de {member}", color=discord.Color.orange())
    for i, warn in enumerate(warns, 1):
        embed.add_field(
            name=f"#{i} - {warn['date']}",
            value=f"**Raison:** {warn['reason']}\n**Par:** {warn['moderator']}",
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(moderate_members=True)
async def clearwarn(ctx, member: discord.Member, index: int = None):
    key = f"{ctx.guild.id}_{member.id}"
    
    if index is None:
        warnings_data[key] = []
        await ctx.send(f"✅ Tous les avertissements de {member.mention} ont été supprimés.")
    else:
        if 1 <= index <= len(warnings_data[key]):
            warnings_data[key].pop(index - 1)
            await ctx.send(f"✅ Avertissement #{index} supprimé pour {member.mention}.")
        else:
            await ctx.send("❌ Index invalide.")

# ============= ECONOMY COMMANDS =============
@bot.command()
async def daily(ctx):
    key = f"{ctx.guild.id}_{ctx.author.id}"
    user_data = economy_data[key]
    
    last_claim = user_data.get("daily_claimed")
    if last_claim:
        next_claim = datetime.fromisoformat(last_claim) + timedelta(days=1)
        if datetime.now() < next_claim:
            remaining = next_claim - datetime.now()
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes = remainder // 60
            return await ctx.send(f"⏰ Revenez dans {hours}h {minutes}m pour votre récompense quotidienne!")
    
    reward = random.randint(500, 1000)
    user_data["money"] += reward
    user_data["daily_claimed"] = datetime.now().isoformat()
    
    embed = discord.Embed(title="🎁 Récompense Quotidienne", color=discord.Color.green())
    embed.description = f"Vous avez reçu **{reward}€**!"
    await ctx.send(embed=embed)

@bot.command(aliases=["bal"])
async def balance(ctx, member: discord.Member = None):
    member = member or ctx.author
    key = f"{ctx.guild.id}_{member.id}"
    user_data = economy_data[key]
    
    embed = discord.Embed(title=f"💰 Profil de {member.name}", color=discord.Color.gold())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Argent", value=f"{user_data['money']}€", inline=True)
    embed.add_field(name="Niveau", value=user_data['level'], inline=True)
    embed.add_field(name="XP", value=f"{user_data['xp']}/{user_data['level']*100}", inline=True)
    embed.add_field(name="Réputation", value=user_data['rep'], inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def rep(ctx, member: discord.Member):
    if member == ctx.author:
        return await ctx.send("❌ Vous ne pouvez pas vous donner de réputation!")
    
    key = f"{ctx.guild.id}_{member.id}"
    economy_data[key]["rep"] += 1
    await ctx.send(f"⭐ Vous avez donné 1 point de réputation à {member.mention}!")

@bot.command()
async def shop(ctx):
    config = server_config[ctx.guild.id]
    shop_items = config["shop"]
    
    if not shop_items:
        return await ctx.send("🛒 La boutique est vide!")
    
    embed = discord.Embed(title="🛒 Boutique du Serveur", color=discord.Color.blue())
    for item in shop_items:
        role = ctx.guild.get_role(item["role_id"])
        if role:
            embed.add_field(
                name=f"{role.name}",
                value=f"Prix: {item['price']}€\nID: {item['role_id']}",
                inline=False
            )
    await ctx.send(embed=embed)

@bot.command()
async def buy(ctx, role_id: int):
    config = server_config[ctx.guild.id]
    item = next((i for i in config["shop"] if i["role_id"] == role_id), None)
    
    if not item:
        return await ctx.send("❌ Cet article n'existe pas!")
    
    key = f"{ctx.guild.id}_{ctx.author.id}"
    user_data = economy_data[key]
    
    if user_data["money"] < item["price"]:
        return await ctx.send(f"❌ Vous n'avez pas assez d'argent! (Besoin: {item['price']}€)")
    
    role = ctx.guild.get_role(role_id)
    if not role:
        return await ctx.send("❌ Ce rôle n'existe plus!")
    
    if role in ctx.author.roles:
        return await ctx.send("❌ Vous avez déjà ce rôle!")
    
    user_data["money"] -= item["price"]
    await ctx.author.add_roles(role)
    await ctx.send(f"✅ Vous avez acheté le rôle {role.mention}!")

@bot.command()
async def dice(ctx, amount: int = 100):
    key = f"{ctx.guild.id}_{ctx.author.id}"
    user_data = economy_data[key]
    
    if amount > user_data["money"]:
        return await ctx.send("❌ Vous n'avez pas assez d'argent!")
    
    result = random.randint(1, 6)
    
    if result >= 4:
        winnings = amount * 2
        user_data["money"] += amount
        await ctx.send(f"🎲 Vous avez obtenu **{result}**! Vous gagnez {winnings}€!")
    else:
        user_data["money"] -= amount
        await ctx.send(f"🎲 Vous avez obtenu **{result}**... Vous perdez {amount}€.")

@bot.command()
async def pay(ctx, member: discord.Member, amount: int):
    if member == ctx.author:
        return await ctx.send("❌ Vous ne pouvez pas vous payer vous-même!")
    
    key_sender = f"{ctx.guild.id}_{ctx.author.id}"
    key_receiver = f"{ctx.guild.id}_{member.id}"
    
    if economy_data[key_sender]["money"] < amount:
        return await ctx.send("❌ Vous n'avez pas assez d'argent!")
    
    economy_data[key_sender]["money"] -= amount
    economy_data[key_receiver]["money"] += amount
    await ctx.send(f"✅ Vous avez envoyé {amount}€ à {member.mention}!")

@bot.command(aliases=["top"])
async def leaderboard(ctx, type="money"):
    guild_users = {k: v for k, v in economy_data.items() if k.startswith(f"{ctx.guild.id}_")}
    
    if not guild_users:
        return await ctx.send("❌ Aucune donnée disponible!")
    
    sorted_users = sorted(guild_users.items(), key=lambda x: x[1][type], reverse=True)[:10]
    
    embed = discord.Embed(
        title=f"🏆 Classement - {type.capitalize()}",
        color=discord.Color.gold()
    )
    
    for i, (key, data) in enumerate(sorted_users, 1):
        user_id = int(key.split("_")[1])
        user = ctx.guild.get_member(user_id)
        if user:
            value = data[type]
            emoji = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"**{i}.**"
            embed.add_field(
                name=f"{emoji} {user.name}",
                value=f"{value}{'€' if type == 'money' else ' XP' if type == 'xp' else ''}",
                inline=False
            )
    
    await ctx.send(embed=embed)

@bot.command()
async def work(ctx):
    key = f"{ctx.guild.id}_{ctx.author.id}"
    user_data = economy_data[key]
    
    last_work = user_data.get("work_claimed")
    if last_work:
        next_work = datetime.fromisoformat(last_work) + timedelta(hours=1)
        if datetime.now() < next_work:
            remaining = next_work - datetime.now()
            minutes = int(remaining.total_seconds() // 60)
            return await ctx.send(f"⏰ Vous devez attendre {minutes} minutes avant de retravailler!")
    
    jobs = ["développeur", "designer", "manager", "consultant", "vendeur"]
    job = random.choice(jobs)
    earnings = random.randint(200, 500)
    
    user_data["money"] += earnings
    user_data["work_claimed"] = datetime.now().isoformat()
    
    await ctx.send(f"💼 Vous avez travaillé comme **{job}** et gagné **{earnings}€**!")

@bot.command()
async def beg(ctx):
    if random.random() < 0.5:
        earnings = random.randint(10, 50)
        key = f"{ctx.guild.id}_{ctx.author.id}"
        economy_data[key]["money"] += earnings
        await ctx.send(f"🙏 Quelqu'un vous a donné {earnings}€!")
    else:
        await ctx.send("🙅 Personne ne vous a donné d'argent...")

# ============= FUN COMMANDS =============
@bot.command()
async def eightball(ctx, *, question):
    responses = [
        "Oui, absolument!", "C'est certain.", "Sans aucun doute.",
        "Probablement.", "Les signes pointent vers oui.",
        "Réessayez plus tard.", "Mieux vaut ne pas le dire maintenant.",
        "Je ne peux pas prédire maintenant.", "Concentrez-vous et redemandez.",
        "N'y comptez pas.", "Ma réponse est non.", "Mes sources disent non."
    ]
    await ctx.send(f"🎱 {random.choice(responses)}")

@bot.command(aliases=["blague"])
async def joke(ctx):
    jokes = [
        "Pourquoi les plongeurs plongent-ils toujours en arrière? Parce que sinon ils tombent dans le bateau!",
        "Qu'est-ce qu'un crocodile qui surveille la pharmacie? Un Lacoste-Garde!",
        "Comment appelle-t-on un chat tombé dans un pot de peinture? Un chat-peauté!",
        "Que dit un escargot quand il croise une limace? Oh, un naturiste!",
        "Qu'est-ce qu'un canif? Un petit fien!"
    ]
    await ctx.send(f"😂 {random.choice(jokes)}")

@bot.command(aliases=["citation"])
async def quote(ctx):
    quotes = [
        "Le succès c'est d'aller d'échec en échec sans perdre son enthousiasme. - Winston Churchill",
        "La vie c'est comme une bicyclette, il faut avancer pour ne pas perdre l'équilibre. - Albert Einstein",
        "L'avenir appartient à ceux qui croient en la beauté de leurs rêves. - Eleanor Roosevelt",
        "Soyez le changement que vous voulez voir dans le monde. - Gandhi",
        "Le seul moyen de faire du bon travail est d'aimer ce que vous faites. - Steve Jobs"
    ]
    await ctx.send(f"💭 {random.choice(quotes)}")

@bot.command()
async def ascii(ctx, *, text: str):
    ascii_art = {
        'a': '  ▄▀█  ', 'b': ' █▄▄  ', 'c': ' █▀▀  ', 'd': ' █▀▄  ', 'e': ' █▀▀  ',
        'f': ' █▀▀  ', 'g': ' █▀▀▀ ', 'h': ' █░█  ', 'i': ' █  ', 'j': ' █▀▀█ ',
        'k': ' █▄▀  ', 'l': ' █░░  ', 'm': ' █▀▄▀█ ', 'n': ' █▄░█ ', 'o': ' █▀█  ',
        'p': ' █▀█  ', 'q': ' █▀█▄ ', 'r': ' █▀█  ', 's': ' █▀▀  ', 't': ' ▀█▀  ',
        'u': ' █░█  ', 'v': ' █░█  ', 'w': ' █░█░█ ', 'x': ' ▀▄▀  ', 'y': ' █▄█  ',
        'z': ' ▀█  ', ' ': '    '
    }
    
    result = ""
    for char in text.lower()[:10]:
        if char in ascii_art:
            result += ascii_art[char]
    
    await ctx.send(f"```\n{result}\n```")

@bot.command()
async def coinflip(ctx):
    result = random.choice(["Pile", "Face"])
    await ctx.send(f"🪙 Résultat: **{result}**!")

@bot.command()
async def rate(ctx, *, thing: str):
    rating = random.randint(0, 100)
    await ctx.send(f"Je donne à **{thing}** un score de **{rating}/100**! {'🔥' if rating > 80 else '👍' if rating > 50 else '😐'}")

@bot.command()
async def ship(ctx, member1: discord.Member, member2: discord.Member):
    percentage = random.randint(0, 100)
    hearts = "❤️" * (percentage // 20)
    ship_name = member1.name[:len(member1.name)//2] + member2.name[len(member2.name)//2:]
    
    embed = discord.Embed(title="💕 Ship-o-mètre", color=discord.Color.pink())
    embed.add_field(name="Couple", value=f"{member1.mention} + {member2.mention}", inline=False)
    embed.add_field(name="Nom du couple", value=ship_name, inline=False)
    embed.add_field(name="Affinité", value=f"{hearts} {percentage}%", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def choose(ctx, *, choices: str):
    options = [opt.strip() for opt in choices.split(',')]
    if len(options) < 2:
        return await ctx.send("❌ Donnez au moins 2 options séparées par des virgules!")
    
    choice = random.choice(options)
    await ctx.send(f"🎯 Je choisis: **{choice}**")

# ============= UTILITY COMMANDS =============
@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    
    embed = discord.Embed(title=f"Informations sur {member}", color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=False)
    embed.add_field(name="Nom", value=str(member), inline=False)
    embed.add_field(name="Surnom", value=member.display_name, inline=False)
    embed.add_field(name="Compte créé le", value=member.created_at.strftime("%d/%m/%Y %H:%M"), inline=False)
    embed.add_field(name="A rejoint le", value=member.joined_at.strftime("%d/%m/%Y %H:%M"), inline=False)
    embed.add_field(name="Rôles", value=f"{len(member.roles)-1} rôles", inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    
    embed = discord.Embed(title=f"Informations sur {guild.name}", color=discord.Color.blue())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="ID", value=guild.id, inline=False)
    embed.add_field(name="Propriétaire", value=guild.owner.mention, inline=False)
    embed.add_field(name="Créé le", value=guild.created_at.strftime("%d/%m/%Y"), inline=False)
    embed.add_field(name="Membres", value=guild.member_count, inline=True)
    embed.add_field(name="Rôles", value=len(guild.roles), inline=True)
    embed.add_field(name="Salons", value=len(guild.channels), inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
async def timer(ctx, duration: str, *, reason="Minuteur"):
    time_units = {"s": 1, "m": 60, "h": 3600}
    unit = duration[-1]
    if unit not in time_units:
        return await ctx.send("❌ Format: 30s, 5m, 1h")
    
    amount = int(duration[:-1])
    seconds = amount * time_units[unit]
    
    await ctx.send(f"⏰ Minuteur de {duration} démarré pour: **{reason}**")
    await asyncio.sleep(seconds)
    await ctx.send(f"{ctx.author.mention} ⏰ Votre minuteur est terminé! **{reason}**")

@bot.command()
@commands.has_permissions(administrator=True)
async def automod(ctx, action: str, *, word: str = None):
    config = server_config[ctx.guild.id]
    
    if action.lower() == "add":
        if not word:
            return await ctx.send("❌ Spécifiez un mot à ajouter!")
        config["automod_words"].append(word.lower())
        await ctx.send(f"✅ Mot ajouté à l'automod: **{word}**")
    
    elif action.lower() == "list":
        if not config["automod_words"]:
            return await ctx.send("📝 Aucun mot interdit configuré.")
        
        embed = discord.Embed(title="🚫 Mots Interdits", color=discord.Color.red())
        embed.description = "\n".join([f"• {w}" for w in config["automod_words"]])
        await ctx.send(embed=embed)
    
    elif action.lower() == "remove":
        if word and word.lower() in config["automod_words"]:
            config["automod_words"].remove(word.lower())
            await ctx.send(f"✅ Mot retiré: **{word}**")
        else:
            await ctx.send("❌ Ce mot n'est pas dans la liste!")

# ============= WELCOME/LEAVE MESSAGES =============
@bot.command()
@commands.has_permissions(administrator=True)
async def bvntext(ctx, *, message: str = None):
    if not message:
        config = server_config[ctx.guild.id]
        return await ctx.send(f"Message actuel: `{config['welcome_msg']}`\n\nVariables: `{{user}}` `{{server}}`")
    
    server_config[ctx.guild.id]["welcome_msg"] = message
    server_config[ctx.guild.id]["welcome_embed"] = None
    await ctx.send(f"✅ Message de bienvenue défini!\nAperçu: {message.replace('{user}', ctx.author.mention).replace('{server}', ctx.guild.name)}")

@bot.command()
@commands.has_permissions(administrator=True)
async def bvnembed(ctx, *, content: str = None):
    if not content or '|' not in content:
        return await ctx.send("❌ Format: `!bvnembed Titre | Description`\n\nVariables: `{user}` `{server}`")
    
    parts = content.split('|', 1)
    title = parts[0].strip()
    description = parts[1].strip()
    
    server_config[ctx.guild.id]["welcome_embed"] = {"title": title, "description": description}
    server_config[ctx.guild.id]["welcome_msg"] = None
    
    preview = discord.Embed(
        title=title.replace("{user}", ctx.author.name),
        description=description.replace("{user}", ctx.author.mention).replace("{server}", ctx.guild.name),
        color=discord.Color.green()
    )
    await ctx.send("✅ Embed de bienvenue défini!\nAperçu:", embed=preview)

@bot.command()
@commands.has_permissions(administrator=True)
async def leavetext(ctx, *, message: str = None):
    if not message:
        config = server_config[ctx.guild.id]
        return await ctx.send(f"Message actuel: `{config['leave_msg']}`\n\nVariables: `{{user}}` `{{server}}`")
    
    server_config[ctx.guild.id]["leave_msg"] = message
    server_config[ctx.guild.id]["leave_embed"] = None
    await ctx.send(f"✅ Message de départ défini!\nAperçu: {message.replace('{user}', ctx.author.name).replace('{server}', ctx.guild.name)}")

@bot.command()
@commands.has_permissions(administrator=True)
async def leaveembed(ctx, *, content: str = None):
    if not content or '|' not in content:
        return await ctx.send("❌ Format: `!leaveembed Titre | Description`\n\nVariables: `{user}` `{server}`")
    
    parts = content.split('|', 1)
    title = parts[0].strip()
    description = parts[1].strip()
    
    server_config[ctx.guild.id]["leave_embed"] = {"title": title, "description": description}
    server_config[ctx.guild.id]["leave_msg"] = None
    
    preview = discord.Embed(
        title=title.replace("{user}", ctx.author.name),
        description=description.replace("{user}", ctx.author.name).replace("{server}", ctx.guild.name),
        color=discord.Color.red()
    )
    await ctx.send("✅ Embed de départ défini!\nAperçu:", embed=preview)

# ============= ADMIN ECONOMY COMMANDS =============
@bot.command()
@commands.has_permissions(administrator=True)
async def shopadd(ctx, role: discord.Role, price: int):
    config = server_config[ctx.guild.id]
    
    if any(item["role_id"] == role.id for item in config["shop"]):
        return await ctx.send("❌ Ce rôle est déjà dans la boutique!")
    
    config["shop"].append({"role_id": role.id, "price": price})
    await ctx.send(f"✅ {role.mention} ajouté à la boutique pour {price}€!")

@bot.command()
@commands.has_permissions(administrator=True)
async def shopremove(ctx, role: discord.Role):
    config = server_config[ctx.guild.id]
    config["shop"] = [item for item in config["shop"] if item["role_id"] != role.id]
    await ctx.send(f"✅ {role.mention} retiré de la boutique!")

@bot.command()
@commands.has_permissions(administrator=True)
async def givemoney(ctx, member: discord.Member, amount: int):
    key = f"{ctx.guild.id}_{member.id}"
    economy_data[key]["money"] += amount
    await ctx.send(f"✅ {amount}€ ajouté à {member.mention}!")

@bot.command()
@commands.has_permissions(administrator=True)
async def removemoney(ctx, member: discord.Member, amount: int):
    key = f"{ctx.guild.id}_{member.id}"
    economy_data[key]["money"] = max(0, economy_data[key]["money"] - amount)
    await ctx.send(f"✅ {amount}€ retiré à {member.mention}!")

@bot.command()
@commands.has_permissions(administrator=True)
async def setlevel(ctx, member: discord.Member, level: int):
    key = f"{ctx.guild.id}_{member.id}"
    economy_data[key]["level"] = level
    economy_data[key]["xp"] = 0
    await ctx.send(f"✅ Niveau de {member.mention} défini à {level}!")

# ============= ERROR HANDLING =============
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Vous n'avez pas la permission d'utiliser cette commande!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant! Utilisez `!help` pour plus d'infos.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Erreur: {error}")

# ============= LANCEMENT DU BOT =============
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.getenv('DISCORD_TOKEN')
    
    if not TOKEN:
        print("❌ ERREUR: Token Discord manquant!")
        print("Ajoutez votre token dans les variables d'environnement de Render:")
        print("DISCORD_TOKEN = votre_token_ici")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"❌ Erreur de connexion: {e}")
