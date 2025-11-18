# === VOC / TEMPORAIRE ===
VOC_TRIGGER_NAME = "🔊Créer un voc"

@bot.command(name="setupvoc")
@commands.has_permissions(manage_guild=True)
async def setup_voc(ctx, channel: discord.VoiceChannel):
    """Définir le salon trigger pour les vocaux temporaires"""
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
    gid = str(member.guild.id)
    trigger_id = get_conf(member.guild.id, "voc_trigger_channel")
    
    # Création vocaux temporaires
    if after.channel and after.channel.id == trigger_id:
        category = after.channel.category
        voc = await member.guild.create_voice_channel(name=f"🔊 {member.display_name}", category=category)
        data.setdefault("temp_vocs", {})[str(voc.id)] = {"owner": member.id, "created_at": datetime.datetime.utcnow().isoformat()}
        save_data(data)
        await member.move_to(voc)

    # Suppression vocaux temporaires vides
    if before.channel and str(before.channel.id) in data.get("temp_vocs", {}):
        if len(before.channel.members) == 0:
            await before.channel.delete()
            del data["temp_vocs"][str(before.channel.id)]
            save_data(data)

# === INVITATIONS / ROLES ===
@bot.command(name="roleinvite")
@commands.has_permissions(manage_guild=True)
async def role_invite(ctx, nombre: int, role: discord.Role):
    gid = str(ctx.guild.id)
    data.setdefault("roles_invites", {}).setdefault(gid, {})[str(nombre)] = role.id
    save_data(data)
    await ctx.send(f"✅ Les membres ayant {nombre} invitations recevront le rôle {role.mention}")

@bot.command(name="invites")
async def invites_cmd(ctx, member: discord.Member = None):
    member = member or ctx.author
    gid = str(ctx.guild.id)
    count = data.get("user_invites", {}).get(gid, {}).get(str(member.id), 0)
    e = discord.Embed(title=f"📊 Invitations de {member.display_name}", color=discord.Color.blue())
    e.add_field(name="Total", value=f"**{count}** invitation(s)", inline=False)
    e.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=e)

# === LIENS AUTORISÉS / BLOQUÉS ===
@bot.command(name="allowlink")
@commands.has_permissions(manage_guild=True)
async def allow_link(ctx, channel: discord.TextChannel):
    gid = str(ctx.guild.id)
    data.setdefault("allowed_links", {}).setdefault(gid, [])
    if channel.id not in data["allowed_links"][gid]:
        data["allowed_links"][gid].append(channel.id)
        save_data(data)
        await ctx.send(f"✅ Liens autorisés dans {channel.mention}")

@bot.command(name="disallowlink")
@commands.has_permissions(manage_guild=True)
async def disallow_link(ctx, channel: discord.TextChannel):
    gid = str(ctx.guild.id)
    if channel.id in data.get("allowed_links", {}).get(gid, []):
        data["allowed_links"][gid].remove(channel.id)
        save_data(data)
        await ctx.send(f"✅ Liens bloqués dans {channel.mention}")

@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    
    gid = str(message.guild.id) if message.guild else None
    if gid:
        allowed = data.get("allowed_links", {}).get(gid, [])
        if message.channel.id not in allowed:
            url_regex = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
            if re.search(url_regex, message.content):
                await message.delete()
                await message.channel.send(f"❌ {message.author.mention}, les liens ne sont pas autorisés ici !", delete_after=5)
    await bot.process_commands(message)

# === LOCK / UNLOCK ===
@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Salon verrouillé !")
    
@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 Salon déverrouillé !")

# === RÔLES RÉACTION ===
@bot.command(name="reactionrole")
@commands.has_permissions(manage_roles=True)
async def reaction_role(ctx, channel: discord.TextChannel, message_id: int, emoji: str, role: discord.Role):
    try:
        message = await channel.fetch_message(message_id)
        await message.add_reaction(emoji)
        gid = str(ctx.guild.id)
        data.setdefault("reaction_roles", {}).setdefault(gid, {})[f"{message_id}_{emoji}"] = {"role_id": role.id, "channel_id": channel.id}
        save_data(data)
        await ctx.send(f"✅ Rôle réaction créé : {emoji} → {role.mention}")
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    gid = str(guild.id)
    key = f"{payload.message_id}_{payload.emoji}"
    role_id = data.get("reaction_roles", {}).get(gid, {}).get(key, {}).get("role_id")
    if role_id:
        role = guild.get_role(role_id)
        if role and member and role not in member.roles:
            await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    gid = str(guild.id)
    key = f"{payload.message_id}_{payload.emoji}"
    role_id = data.get("reaction_roles", {}).get(gid, {}).get(key, {}).get("role_id")
    if role_id:
        role = guild.get_role(role_id)
        if role and member and role in member.roles:
            await member.remove_roles(role)

# === SAY / TEST WELCOME / LEAVE ===
@bot.command(name="say")
@commands.has_permissions(manage_messages=True)
async def say(ctx, *, msg: str):
    await ctx.message.delete()
    await ctx.send(msg)

@bot.command(name="testwelcome")
@commands.has_permissions(manage_guild=True)
async def test_welcome(ctx):
    embed_id = get_conf(ctx.guild.id, "welcome_embed_channel")
    text_id = get_conf(ctx.guild.id, "welcome_text_channel")
    if embed_id:
        channel = ctx.guild.get_channel(embed_id)
        if channel:
            e = discord.Embed(title="🎉 Bienvenue !", description=f"{ctx.author.mention} (TEST)", color=discord.Color.green())
            await channel.send(embed=e)
    if text_id:
        channel = ctx.guild.get_channel(text_id)
        if channel:
            await channel.send(f"🎉 Bienvenue {ctx.author.mention} ! (TEST)")
    await ctx.send("✅ Test bienvenue envoyé !", delete_after=5)

@bot.command(name="testleave")
@commands.has_permissions(manage_guild=True)
async def test_leave(ctx):
    embed_id = get_conf(ctx.guild.id, "leave_embed_channel")
    text_id = get_conf(ctx.guild.id, "leave_text_channel")
    if embed_id:
        channel = ctx.guild.get_channel(embed_id)
        if channel:
            e = discord.Embed(title="👋 Au revoir", description=f"{ctx.author.mention} (TEST)", color=discord.Color.red())
            await channel.send(embed=e)
    if text_id:
        channel = ctx.guild.get_channel(text_id)
        if channel:
            await channel.send(f"👋 {ctx.author.mention} a quitté le serveur ! (TEST)")
    await ctx.send("✅ Test au revoir envoyé !", delete_after=5)
