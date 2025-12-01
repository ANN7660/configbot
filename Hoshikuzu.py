// ======================================
// BOT DISCORD COMPLET - PARTIE 1/2
// ======================================

const { 
    Client, 
    GatewayIntentBits, 
    EmbedBuilder, 
    ActionRowBuilder, 
    ButtonBuilder, 
    ButtonStyle, 
    StringSelectMenuBuilder,
    ChannelType,
    PermissionFlagsBits,
    ModalBuilder,
    TextInputBuilder,
    TextInputStyle
} = require('discord.js');
const fs = require('fs');

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.GuildMembers,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.GuildMessageReactions
    ]
});

// Base de données JSON
const DB_FILE = './config.json';
let config = {};

function loadConfig() {
    if (fs.existsSync(DB_FILE)) {
        config = JSON.parse(fs.readFileSync(DB_FILE, 'utf8'));
    } else {
        config = {};
        saveConfig();
    }
}

function saveConfig() {
    fs.writeFileSync(DB_FILE, JSON.stringify(config, null, 2));
}

function getGuildConfig(guildId) {
    if (!config[guildId]) {
        config[guildId] = {
            welcomeEmbed: null,
            welcomeText: null,
            leaveEmbed: null,
            leaveText: null,
            welcomeChannel: null,
            leaveChannel: null,
            ticketCategory: null,
            ticketRoles: [],
            ticketCounter: 0,
            logChannel: null,
            joinRole: null,
            tempVocCategory: null,
            tempVocChannels: []
        };
        saveConfig();
    }
    return config[guildId];
}

client.once('ready', () => {
    console.log(`✅ Bot connecté en tant que ${client.user.tag}`);
    loadConfig();
});

// ======================================
// COMMANDE !HELP
// ======================================
client.on('messageCreate', async message => {
    if (message.author.bot || !message.content.startsWith('!')) return;

    const args = message.content.slice(1).trim().split(/ +/);
    const command = args.shift().toLowerCase();

    // !HELP
    if (command === 'help') {
        const embed = new EmbedBuilder()
            .setTitle('📚 Menu d\'aide du Bot')
            .setDescription('Sélectionnez une catégorie pour voir les commandes')
            .setColor('#3498db')
            .setTimestamp();

        const row = new ActionRowBuilder()
            .addComponents(
                new StringSelectMenuBuilder()
                    .setCustomId('help_menu')
                    .setPlaceholder('Sélectionner une catégorie')
                    .addOptions([
                        {
                            label: '👋 Bienvenue & Départ',
                            description: 'Messages de bienvenue et départ',
                            value: 'welcome'
                        },
                        {
                            label: '🎫 Système de Tickets',
                            description: 'Gestion des tickets',
                            value: 'tickets'
                        },
                        {
                            label: '🛡️ Modération',
                            description: 'Commandes de modération',
                            value: 'moderation'
                        },
                        {
                            label: '🎭 Rôles & Réactions',
                            description: 'Gestion des rôles',
                            value: 'roles'
                        },
                        {
                            label: '🔊 Vocaux Temporaires',
                            description: 'Salons vocaux temporaires',
                            value: 'voice'
                        },
                        {
                            label: '⚙️ Configuration',
                            description: 'Configuration du bot',
                            value: 'config'
                        }
                    ])
            );

        await message.reply({ embeds: [embed], components: [row] });
    }

    // !BVNTEXT - Message de bienvenue en texte
    if (command === 'bvntext') {
        if (!message.member.permissions.has(PermissionFlagsBits.Administrator)) {
            return message.reply('❌ Vous devez être administrateur pour utiliser cette commande.');
        }

        const text = args.join(' ');
        if (!text) {
            return message.reply('❌ Usage: `!bvntext <message>`\nVariables: `{user}` `{server}` `{membercount}`');
        }

        const guildConfig = getGuildConfig(message.guild.id);
        guildConfig.welcomeText = text;
        saveConfig();

        message.reply('✅ Message de bienvenue (texte) configuré!\nExemple: ' + text.replace('{user}', message.author.toString()).replace('{server}', message.guild.name).replace('{membercount}', message.guild.memberCount));
    }

    // !BVNEMBED - Message de bienvenue en embed
    if (command === 'bvnembed') {
        if (!message.member.permissions.has(PermissionFlagsBits.Administrator)) {
            return message.reply('❌ Vous devez être administrateur pour utiliser cette commande.');
        }

        const modal = new ModalBuilder()
            .setCustomId('welcome_embed_modal')
            .setTitle('Configuration Embed de Bienvenue');

        // Comme on ne peut pas utiliser de modals avec les messages prefix, on va utiliser un système simple
        const description = args.join(' ');
        if (!description) {
            return message.reply('❌ Usage: `!bvnembed <description>`\nVariables: `{user}` `{server}` `{membercount}`');
        }

        const guildConfig = getGuildConfig(message.guild.id);
        guildConfig.welcomeEmbed = {
            title: '👋 Bienvenue!',
            description: description,
            color: '#00ff00'
        };
        saveConfig();

        const previewEmbed = new EmbedBuilder()
            .setTitle(guildConfig.welcomeEmbed.title)
            .setDescription(description.replace('{user}', message.author.toString()).replace('{server}', message.guild.name).replace('{membercount}', message.guild.memberCount))
            .setColor(guildConfig.welcomeEmbed.color);

        message.reply({ content: '✅ Embed de bienvenue configuré! Aperçu:', embeds: [previewEmbed] });
    }

    // !LEAVETEXT - Message de départ en texte
    if (command === 'leavetxt') {
        if (!message.member.permissions.has(PermissionFlagsBits.Administrator)) {
            return message.reply('❌ Vous devez être administrateur pour utiliser cette commande.');
        }

        const text = args.join(' ');
        if (!text) {
            return message.reply('❌ Usage: `!leavetxt <message>`\nVariables: `{user}` `{server}` `{membercount}`');
        }

        const guildConfig = getGuildConfig(message.guild.id);
        guildConfig.leaveText = text;
        saveConfig();

        message.reply('✅ Message de départ (texte) configuré!');
    }

    // !LEAVEEMBED - Message de départ en embed
    if (command === 'leaveembed') {
        if (!message.member.permissions.has(PermissionFlagsBits.Administrator)) {
            return message.reply('❌ Vous devez être administrateur pour utiliser cette commande.');
        }

        const description = args.join(' ');
        if (!description) {
            return message.reply('❌ Usage: `!leaveembed <description>`\nVariables: `{user}` `{server}` `{membercount}`');
        }

        const guildConfig = getGuildConfig(message.guild.id);
        guildConfig.leaveEmbed = {
            title: '👋 Au revoir!',
            description: description,
            color: '#ff0000'
        };
        saveConfig();

        message.reply('✅ Embed de départ configuré!');
    }

    // !TICKETPANEL - Créer le panel de tickets
    if (command === 'ticketpanel') {
        if (!message.member.permissions.has(PermissionFlagsBits.Administrator)) {
            return message.reply('❌ Vous devez être administrateur pour utiliser cette commande.');
        }

        const embed = new EmbedBuilder()
            .setTitle('🎫 Support Tickets')
            .setDescription('Cliquez sur le bouton ci-dessous pour créer un ticket de support.\n\nNotre équipe vous répondra dès que possible!')
            .setColor('#3498db')
            .setTimestamp();

        const row = new ActionRowBuilder()
            .addComponents(
                new ButtonBuilder()
                    .setCustomId('create_ticket')
                    .setLabel('📩 Créer un Ticket')
                    .setStyle(ButtonStyle.Primary)
            );

        await message.channel.send({ embeds: [embed], components: [row] });
        message.delete().catch(() => {});
    }

    // !TICKETROLE - Ajouter un rôle à mentionner dans les tickets
    if (command === 'ticketrole') {
        if (!message.member.permissions.has(PermissionFlagsBits.Administrator)) {
            return message.reply('❌ Vous devez être administrateur pour utiliser cette commande.');
        }

        const role = message.mentions.roles.first();
        if (!role) {
            return message.reply('❌ Usage: `!ticketrole @role`');
        }

        const guildConfig = getGuildConfig(message.guild.id);
        if (guildConfig.ticketRoles.includes(role.id)) {
            return message.reply('❌ Ce rôle est déjà dans la liste des rôles de ticket.');
        }

        guildConfig.ticketRoles.push(role.id);
        saveConfig();

        message.reply(`✅ Le rôle ${role} sera maintenant mentionné dans les nouveaux tickets.`);
    }

    // !BAN
    if (command === 'ban') {
        if (!message.member.permissions.has(PermissionFlagsBits.BanMembers)) {
            return message.reply('❌ Vous n\'avez pas la permission de bannir des membres.');
        }

        const user = message.mentions.users.first();
        if (!user) {
            return message.reply('❌ Usage: `!ban @utilisateur [raison]`');
        }

        const reason = args.slice(1).join(' ') || 'Aucune raison fournie';

        try {
            await message.guild.members.ban(user, { reason });
            
            const embed = new EmbedBuilder()
                .setTitle('🔨 Membre Banni')
                .setDescription(`**Membre:** ${user.tag}\n**Raison:** ${reason}\n**Modérateur:** ${message.author.tag}`)
                .setColor('#e74c3c')
                .setTimestamp();

            message.reply({ embeds: [embed] });
            logAction(message.guild.id, embed);
        } catch (error) {
            message.reply('❌ Impossible de bannir cet utilisateur.');
        }
    }

    // !UNBAN
    if (command === 'unban') {
        if (!message.member.permissions.has(PermissionFlagsBits.BanMembers)) {
            return message.reply('❌ Vous n\'avez pas la permission de débannir des membres.');
        }

        const userId = args[0];
        if (!userId) {
            return message.reply('❌ Usage: `!unban <ID utilisateur>`');
        }

        try {
            await message.guild.members.unban(userId);
            message.reply(`✅ L'utilisateur avec l'ID \`${userId}\` a été débanni.`);
        } catch (error) {
            message.reply('❌ Impossible de débannir cet utilisateur.');
        }
    }

    // !MUTE - Timeout temporaire
    if (command === 'mute') {
        if (!message.member.permissions.has(PermissionFlagsBits.ModerateMembers)) {
            return message.reply('❌ Vous n\'avez pas la permission de mute des membres.');
        }

        const member = message.mentions.members.first();
        const duration = args[1];
        const reason = args.slice(2).join(' ') || 'Aucune raison fournie';

        if (!member || !duration) {
            return message.reply('❌ Usage: `!mute @membre <durée> [raison]`\nExemples de durée: 10m, 1h, 1d');
        }

        const time = parseDuration(duration);
        if (!time) {
            return message.reply('❌ Durée invalide. Utilisez: 10m, 1h, 1d, etc.');
        }

        try {
            await member.timeout(time, reason);
            
            const embed = new EmbedBuilder()
                .setTitle('🔇 Membre Mute')
                .setDescription(`**Membre:** ${member.user.tag}\n**Durée:** ${duration}\n**Raison:** ${reason}\n**Modérateur:** ${message.author.tag}`)
                .setColor('#e67e22')
                .setTimestamp();

            message.reply({ embeds: [embed] });
            logAction(message.guild.id, embed);
        } catch (error) {
            message.reply('❌ Impossible de mute ce membre.');
        }
    }

    // !UNMUTE
    if (command === 'unmute') {
        if (!message.member.permissions.has(PermissionFlagsBits.ModerateMembers)) {
            return message.reply('❌ Vous n\'avez pas la permission de unmute des membres.');
        }

        const member = message.mentions.members.first();
        if (!member) {
            return message.reply('❌ Usage: `!unmute @membre`');
        }

        try {
            await member.timeout(null);
            message.reply(`✅ ${member.user.tag} a été unmute.`);
        } catch (error) {
            message.reply('❌ Impossible de unmute ce membre.');
        }
    }
});

// Fonction pour parser la durée
function parseDuration(duration) {
    const match = duration.match(/^(\d+)([smhd])$/);
    if (!match) return null;

    const value = parseInt(match[1]);
    const unit = match[2];

    const multipliers = {
        s: 1000,
        m: 60000,
        h: 3600000,
        d: 86400000
    };

    return value * multipliers[unit];
}

// Fonction de log
async function logAction(guildId, embed) {
    const guildConfig = getGuildConfig(guildId);
    if (!guildConfig.logChannel) return;

    const guild = client.guilds.cache.get(guildId);
    const channel = guild.channels.cache.get(guildConfig.logChannel);
    if (channel) {
        await channel.send({ embeds: [embed] });
    }
}

// Événement membre rejoins
client.on('guildMemberAdd', async member => {
    const guildConfig = getGuildConfig(member.guild.id);

    // Ajouter le rôle de bienvenue
    if (guildConfig.joinRole) {
        try {
            const role = member.guild.roles.cache.get(guildConfig.joinRole);
            if (role) await member.roles.add(role);
        } catch (error) {
            console.error('Erreur lors de l\'ajout du rôle:', error);
        }
    }

    // Envoyer le message de bienvenue
    if (guildConfig.welcomeChannel) {
        const channel = member.guild.channels.cache.get(guildConfig.welcomeChannel);
        if (!channel) return;

        if (guildConfig.welcomeEmbed) {
            const embed = new EmbedBuilder()
                .setTitle(guildConfig.welcomeEmbed.title)
                .setDescription(
                    guildConfig.welcomeEmbed.description
                        .replace('{user}', member.toString())
                        .replace('{server}', member.guild.name)
                        .replace('{membercount}', member.guild.memberCount)
                )
                .setColor(guildConfig.welcomeEmbed.color)
                .setThumbnail(member.user.displayAvatarURL())
                .setTimestamp();

            await channel.send({ embeds: [embed] });
        }

        if (guildConfig.welcomeText) {
            const text = guildConfig.welcomeText
                .replace('{user}', member.toString())
                .replace('{server}', member.guild.name)
                .replace('{membercount}', member.guild.memberCount);

            await channel.send(text);
        }
    }

    // Log
    const logEmbed = new EmbedBuilder()
        .setTitle('📥 Membre Rejoint')
        .setDescription(`**Membre:** ${member.user.tag}\n**ID:** ${member.id}\n**Compte créé:** <t:${Math.floor(member.user.createdTimestamp / 1000)}:R>`)
        .setColor('#2ecc71')
        .setThumbnail(member.user.displayAvatarURL())
        .setTimestamp();

    logAction(member.guild.id, logEmbed);
});

// Suite dans la partie 2...
// ======================================
// BOT DISCORD COMPLET - PARTIE 2/2
// ======================================
// Suite du code de la partie 1...

// Événement membre quitte
client.on('guildMemberRemove', async member => {
    const guildConfig = getGuildConfig(member.guild.id);

    // Envoyer le message de départ
    if (guildConfig.leaveChannel) {
        const channel = member.guild.channels.cache.get(guildConfig.leaveChannel);
        if (!channel) return;

        if (guildConfig.leaveEmbed) {
            const embed = new EmbedBuilder()
                .setTitle(guildConfig.leaveEmbed.title)
                .setDescription(
                    guildConfig.leaveEmbed.description
                        .replace('{user}', member.user.tag)
                        .replace('{server}', member.guild.name)
                        .replace('{membercount}', member.guild.memberCount)
                )
                .setColor(guildConfig.leaveEmbed.color)
                .setThumbnail(member.user.displayAvatarURL())
                .setTimestamp();

            await channel.send({ embeds: [embed] });
        }

        if (guildConfig.leaveText) {
            const text = guildConfig.leaveText
                .replace('{user}', member.user.tag)
                .replace('{server}', member.guild.name)
                .replace('{membercount}', member.guild.memberCount);

            await channel.send(text);
        }
    }

    // Log
    const logEmbed = new EmbedBuilder()
        .setTitle('📤 Membre Parti')
        .setDescription(`**Membre:** ${member.user.tag}\n**ID:** ${member.id}`)
        .setColor('#e74c3c')
        .setThumbnail(member.user.displayAvatarURL())
        .setTimestamp();

    logAction(member.guild.id, logEmbed);
});

// Suite des commandes
client.on('messageCreate', async message => {
    if (message.author.bot || !message.content.startsWith('!')) return;

    const args = message.content.slice(1).trim().split(/ +/);
    const command = args.shift().toLowerCase();

    // !LOCK - Verrouiller un salon
    if (command === 'lock') {
        if (!message.member.permissions.has(PermissionFlagsBits.ManageChannels)) {
            return message.reply('❌ Vous n\'avez pas la permission de gérer les salons.');
        }

        await message.channel.permissionOverwrites.edit(message.guild.id, {
            SendMessages: false
        });

        message.reply('🔒 Salon verrouillé! Seuls les modérateurs peuvent écrire.');
    }

    // !UNLOCK - Déverrouiller un salon
    if (command === 'unlock') {
        if (!message.member.permissions.has(PermissionFlagsBits.ManageChannels)) {
            return message.reply('❌ Vous n\'avez pas la permission de gérer les salons.');
        }

        await message.channel.permissionOverwrites.edit(message.guild.id, {
            SendMessages: null
        });

        message.reply('🔓 Salon déverrouillé!');
    }

    // !MODLENT - Activer le mode lent
    if (command === 'modlent') {
        if (!message.member.permissions.has(PermissionFlagsBits.ManageChannels)) {
            return message.reply('❌ Vous n\'avez pas la permission de gérer les salons.');
        }

        const seconds = parseInt(args[0]) || 5;
        if (seconds < 0 || seconds > 21600) {
            return message.reply('❌ Le délai doit être entre 0 et 21600 secondes (6 heures).');
        }

        await message.channel.setRateLimitPerUser(seconds);
        message.reply(`🐌 Mode lent activé: ${seconds} secondes entre chaque message.`);
    }

    // !MODERAPIDE - Désactiver le mode lent
    if (command === 'moderapide') {
        if (!message.member.permissions.has(PermissionFlagsBits.ManageChannels)) {
            return message.reply('❌ Vous n\'avez pas la permission de gérer les salons.');
        }

        await message.channel.setRateLimitPerUser(0);
        message.reply('⚡ Mode lent désactivé!');
    }

    // !ROLEREACT - Créer un role reaction
    if (command === 'rolereact') {
        if (!message.member.permissions.has(PermissionFlagsBits.ManageRoles)) {
            return message.reply('❌ Vous n\'avez pas la permission de gérer les rôles.');
        }

        const role = message.mentions.roles.first();
        const emoji = args[1];
        const description = args.slice(2).join(' ') || 'Réagissez pour obtenir ce rôle!';

        if (!role || !emoji) {
            return message.reply('❌ Usage: `!rolereact @role <emoji> [description]`');
        }

        const embed = new EmbedBuilder()
            .setTitle('🎭 Rôles Réactifs')
            .setDescription(`${emoji} - ${role}\n\n${description}`)
            .setColor('#9b59b6')
            .setTimestamp();

        const msg = await message.channel.send({ embeds: [embed] });
        await msg.react(emoji);

        // Sauvegarder le message pour le système de réaction
        const guildConfig = getGuildConfig(message.guild.id);
        if (!guildConfig.roleReacts) guildConfig.roleReacts = {};
        guildConfig.roleReacts[msg.id] = { roleId: role.id, emoji: emoji };
        saveConfig();

        message.delete().catch(() => {});
    }

    // !CREATEVOC - Créer un système de vocal temporaire
    if (command === 'createvoc') {
        if (!message.member.permissions.has(PermissionFlagsBits.ManageChannels)) {
            return message.reply('❌ Vous n\'avez pas la permission de gérer les salons.');
        }

        try {
            // Créer une catégorie si elle n'existe pas
            let category = message.guild.channels.cache.find(
                c => c.name === '🔊 Vocaux Temporaires' && c.type === ChannelType.GuildCategory
            );

            if (!category) {
                category = await message.guild.channels.create({
                    name: '🔊 Vocaux Temporaires',
                    type: ChannelType.GuildCategory
                });
            }

            // Créer le salon "Rejoindre pour créer"
            const joinChannel = await message.guild.channels.create({
                name: '➕ Rejoindre pour créer',
                type: ChannelType.GuildVoice,
                parent: category.id
            });

            const guildConfig = getGuildConfig(message.guild.id);
            guildConfig.tempVocCategory = category.id;
            guildConfig.tempVocJoinChannel = joinChannel.id;
            saveConfig();

            message.reply('✅ Système de vocal temporaire créé! Rejoignez le salon pour créer votre propre vocal.');
        } catch (error) {
            message.reply('❌ Erreur lors de la création du système de vocal temporaire.');
        }
    }

    // !JOINROLE - Définir le rôle des nouveaux membres
    if (command === 'joinrole') {
        if (!message.member.permissions.has(PermissionFlagsBits.Administrator)) {
            return message.reply('❌ Vous devez être administrateur pour utiliser cette commande.');
        }

        const role = message.mentions.roles.first();
        if (!role) {
            return message.reply('❌ Usage: `!joinrole @role`');
        }

        const guildConfig = getGuildConfig(message.guild.id);
        guildConfig.joinRole = role.id;
        saveConfig();

        message.reply(`✅ Le rôle ${role} sera maintenant donné aux nouveaux membres.`);
    }

    // !CONFIG - Configuration interactive
    if (command === 'config') {
        if (!message.member.permissions.has(PermissionFlagsBits.Administrator)) {
            return message.reply('❌ Vous devez être administrateur pour utiliser cette commande.');
        }

        const embed = new EmbedBuilder()
            .setTitle('⚙️ Configuration du Bot')
            .setDescription('Sélectionnez ce que vous souhaitez configurer')
            .setColor('#3498db')
            .setTimestamp();

        const row = new ActionRowBuilder()
            .addComponents(
                new StringSelectMenuBuilder()
                    .setCustomId('config_menu')
                    .setPlaceholder('Sélectionner une option')
                    .addOptions([
                        {
                            label: '👋 Salon de Bienvenue',
                            description: 'Définir le salon des messages de bienvenue',
                            value: 'welcome_channel',
                            emoji: '👋'
                        },
                        {
                            label: '👋 Salon de Départ',
                            description: 'Définir le salon des messages de départ',
                            value: 'leave_channel',
                            emoji: '👋'
                        },
                        {
                            label: '🎫 Catégorie Tickets',
                            description: 'Définir la catégorie pour les tickets',
                            value: 'ticket_category',
                            emoji: '🎫'
                        },
                        {
                            label: '📝 Salon de Logs',
                            description: 'Définir le salon des logs',
                            value: 'log_channel',
                            emoji: '📝'
                        },
                        {
                            label: '👤 Rôle Nouveaux Membres',
                            description: 'Définir le rôle des nouveaux membres',
                            value: 'join_role',
                            emoji: '👤'
                        }
                    ])
            );

        await message.reply({ embeds: [embed], components: [row] });
    }
});

// Gestion des menus de sélection
client.on('interactionCreate', async interaction => {
    if (!interaction.isStringSelectMenu()) return;

    // Menu d'aide
    if (interaction.customId === 'help_menu') {
        const category = interaction.values[0];
        let embed;

        switch (category) {
            case 'welcome':
                embed = new EmbedBuilder()
                    .setTitle('👋 Commandes de Bienvenue & Départ')
                    .setDescription(
                        '**!bvntext** `<message>` - Message de bienvenue en texte\n' +
                        '**!bvnembed** `<description>` - Message de bienvenue en embed\n' +
                        '**!leavetxt** `<message>` - Message de départ en texte\n' +
                        '**!leaveembed** `<description>` - Message de départ en embed\n\n' +
                        '**Variables disponibles:**\n' +
                        '`{user}` - Mention du membre\n' +
                        '`{server}` - Nom du serveur\n' +
                        '`{membercount}` - Nombre de membres'
                    )
                    .setColor('#2ecc71');
                break;

            case 'tickets':
                embed = new EmbedBuilder()
                    .setTitle('🎫 Commandes de Tickets')
                    .setDescription(
                        '**!ticketpanel** - Créer un panel de tickets\n' +
                        '**!ticketrole** `@role` - Ajouter un rôle à mentionner dans les tickets'
                    )
                    .setColor('#3498db');
                break;

            case 'moderation':
                embed = new EmbedBuilder()
                    .setTitle('🛡️ Commandes de Modération')
                    .setDescription(
                        '**!ban** `@membre [raison]` - Bannir un membre\n' +
                        '**!unban** `<ID> [raison]` - Débannir un membre\n' +
                        '**!mute** `@membre <durée> [raison]` - Mute temporaire\n' +
                        '**!unmute** `@membre` - Unmute un membre\n' +
                        '**!lock** - Verrouiller le salon\n' +
                        '**!unlock** - Déverrouiller le salon\n' +
                        '**!modlent** `<secondes>` - Activer le mode lent\n' +
                        '**!moderapide** - Désactiver le mode lent\n\n' +
                        '**Durées:** 10s, 5m, 1h, 1d'
                    )
                    .setColor('#e74c3c');
                break;

            case 'roles':
                embed = new EmbedBuilder()
                    .setTitle('🎭 Commandes de Rôles')
                    .setDescription(
                        '**!rolereact** `@role <emoji> [description]` - Créer un rôle réactif\n' +
                        '**!joinrole** `@role` - Rôle automatique pour nouveaux membres'
                    )
                    .setColor('#9b59b6');
                break;

            case 'voice':
                embed = new EmbedBuilder()
                    .setTitle('🔊 Vocaux Temporaires')
                    .setDescription(
                        '**!createvoc** - Créer le système de vocaux temporaires\n\n' +
                        'Les membres peuvent rejoindre le salon "Rejoindre pour créer" et un vocal temporaire sera créé à leur nom. ' +
                        'Le salon se supprime automatiquement quand il est vide.'
                    )
                    .setColor('#f39c12');
                break;

            case 'config':
                embed = new EmbedBuilder()
                    .setTitle('⚙️ Commandes de Configuration')
                    .setDescription(
                        '**!config** - Menu de configuration interactif\n' +
                        '**!help** - Afficher ce menu d\'aide\n\n' +
                        'Utilisez !config pour définir les salons et paramètres du bot.'
                    )
                    .setColor('#95a5a6');
                break;
        }

        await interaction.update({ embeds: [embed] });
    }

    // Menu de configuration
    if (interaction.customId === 'config_menu') {
        const option = interaction.values[0];
        const guildConfig = getGuildConfig(interaction.guild.id);

        await interaction.reply({
            content: `📝 Mentionnez le salon/rôle/catégorie pour **${option.replace('_', ' ')}** dans les 30 prochaines secondes:`,
            ephemeral: true
        });

        const filter = m => m.author.id === interaction.user.id;
        const collector = interaction.channel.createMessageCollector({ filter, time: 30000, max: 1 });

        collector.on('collect', async m => {
            let target;

            if (option.includes('channel')) {
                target = m.mentions.channels.first();
                if (target) {
                    if (option === 'welcome_channel') guildConfig.welcomeChannel = target.id;
                    if (option === 'leave_channel') guildConfig.leaveChannel = target.id;
                    if (option === 'log_channel') guildConfig.logChannel = target.id;
                    saveConfig();
                    await m.reply(`✅ Salon configuré: ${target}`);
                }
            } else if (option.includes('category')) {
                target = m.mentions.channels.first();
                if (target && target.type === ChannelType.GuildCategory) {
                    guildConfig.ticketCategory = target.id;
                    saveConfig();
                    await m.reply(`✅ Catégorie configurée: ${target.name}`);
                }
            } else if (option.includes('role')) {
                target = m.mentions.roles.first();
                if (target) {
                    guildConfig.joinRole = target.id;
                    saveConfig();
                    await m.reply(`✅ Rôle configuré: ${target}`);
                }
            }

            if (!target) {
                await m.reply('❌ Élément invalide ou non trouvé.');
            }
        });
    }
});

// Gestion des boutons
client.on('interactionCreate', async interaction => {
    if (!interaction.isButton()) return;

    // Bouton créer un ticket
    if (interaction.customId === 'create_ticket') {
        const guildConfig = getGuildConfig(interaction.guild.id);
        
        // Vérifier si l'utilisateur a déjà un ticket ouvert
        const existingTicket = interaction.guild.channels.cache.find(
            c => c.name === `ticket-${interaction.user.username.toLowerCase()}` && c.type === ChannelType.GuildText
        );

        if (existingTicket) {
            return interaction.reply({ content: `❌ Vous avez déjà un ticket ouvert: ${existingTicket}`, ephemeral: true });
        }

        await interaction.deferReply({ ephemeral: true });

        try {
            // Créer le salon de ticket
            const ticketChannel = await interaction.guild.channels.create({
                name: `ticket-${interaction.user.username}`,
                type: ChannelType.GuildText,
                parent: guildConfig.ticketCategory,
                permissionOverwrites: [
                    {
                        id: interaction.guild.id,
                        deny: [PermissionFlagsBits.ViewChannel]
                    },
                    {
                        id: interaction.user.id,
                        allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages, PermissionFlagsBits.ReadMessageHistory]
                    }
                ]
            });

            // Ajouter les permissions pour les rôles de support
            for (const roleId of guildConfig.ticketRoles) {
                await ticketChannel.permissionOverwrites.create(roleId, {
                    ViewChannel: true,
                    SendMessages: true,
                    ReadMessageHistory: true
                });
            }

            // Message dans le ticket
            const ticketEmbed = new EmbedBuilder()
                .setTitle('🎫 Nouveau Ticket')
                .setDescription(
                    `Bienvenue ${interaction.user}!\n\n` +
                    `Notre équipe va vous répondre dès que possible.\n` +
                    `Décrivez votre problème ou votre question en détail.`
                )
                .setColor('#3498db')
                .setTimestamp();

            const closeButton = new ActionRowBuilder()
                .addComponents(
                    new ButtonBuilder()
                        .setCustomId('close_ticket')
                        .setLabel('🔒 Fermer le Ticket')
                        .setStyle(ButtonStyle.Danger)
                );

            // Mention des rôles
            let mentions = `${interaction.user}`;
            for (const roleId of guildConfig.ticketRoles) {
                mentions += ` <@&${roleId}>`;
            }

            await ticketChannel.send({ content: mentions, embeds: [ticketEmbed], components: [closeButton] });

            await interaction.editReply({ content: `✅ Ticket créé: ${ticketChannel}` });

            // Log
            const logEmbed = new EmbedBuilder()
                .setTitle('🎫 Ticket Créé')
                .setDescription(`**Créé par:** ${interaction.user.tag}\n**Salon:** ${ticketChannel}`)
                .setColor('#3498db')
                .setTimestamp();

            logAction(interaction.guild.id, logEmbed);
        } catch (error) {
            console.error(error);
            await interaction.editReply({ content: '❌ Erreur lors de la création du ticket.' });
        }
    }

    // Bouton fermer le ticket
    if (interaction.customId === 'close_ticket') {
        const embed = new EmbedBuilder()
            .setTitle('❓ Confirmer la Fermeture')
            .setDescription('Êtes-vous sûr de vouloir fermer ce ticket?')
            .setColor('#e74c3c');

        const row = new ActionRowBuilder()
            .addComponents(
                new ButtonBuilder()
                    .setCustomId('confirm_close')
                    .setLabel('✅ Confirmer')
                    .setStyle(ButtonStyle.Danger),
                new ButtonBuilder()
                    .setCustomId('cancel_close')
                    .setLabel('❌ Annuler')
                    .setStyle(ButtonStyle.Secondary)
            );

        await interaction.reply({ embeds: [embed], components: [row], ephemeral: true });
    }

    if (interaction.customId === 'confirm_close') {
        await interaction.update({ content: '🔒 Fermeture du ticket...', embeds: [], components: [] });
        
        setTimeout(async () => {
            await interaction.channel.delete();
        }, 3000);

        // Log
        const logEmbed = new EmbedBuilder()
            .setTitle('🔒 Ticket Fermé')
            .setDescription(`**Fermé par:** ${interaction.user.tag}\n**Salon:** ${interaction.channel.name}`)
            .setColor('#e74c3c')
            .setTimestamp();

        logAction(interaction.guild.id, logEmbed);
    }

    if (interaction.customId === 'cancel_close') {
        await interaction.update({ content: '✅ Fermeture annulée.', embeds: [], components: [] });
    }
});

// Système de rôles réactifs
client.on('messageReactionAdd', async (reaction, user) => {
    if (user.bot) return;
    if (reaction.partial) await reaction.fetch();

    const guildConfig = getGuildConfig(reaction.message.guild.id);
    if (!guildConfig.roleReacts || !guildConfig.roleReacts[reaction.message.id]) return;

    const roleReact = guildConfig.roleReacts[reaction.message.id];
    if (reaction.emoji.name !== roleReact.emoji && reaction.emoji.id !== roleReact.emoji) return;

    const member = await reaction.message.guild.members.fetch(user.id);
    const role = reaction.message.guild.roles.cache.get(roleReact.roleId);

    if (role) {
        await member.roles.add(role);
    }
});

client.on('messageReactionRemove', async (reaction, user) => {
    if (user.bot) return;
    if (reaction.partial) await reaction.fetch();

    const guildConfig = getGuildConfig(reaction.message.guild.id);
    if (!guildConfig.roleReacts || !guildConfig.roleReacts[reaction.message.id]) return;

    const roleReact = guildConfig.roleReacts[reaction.message.id];
    if (reaction.emoji.name !== roleReact.emoji && reaction.emoji.id !== roleReact.emoji) return;

    const member = await reaction.message.guild.members.fetch(user.id);
    const role = reaction.message.guild.roles.cache.get(roleReact.roleId);

    if (role) {
        await member.roles.remove(role);
    }
});

// Système de vocaux temporaires
client.on('voiceStateUpdate', async (oldState, newState) => {
    const guildConfig = getGuildConfig(newState.guild.id);
    if (!guildConfig.tempVocJoinChannel) return;

    // Rejoindre le salon "Rejoindre pour créer"
    if (newState.channelId === guildConfig.tempVocJoinChannel && !oldState.channelId) {
        try {
            const tempChannel = await newState.guild.channels.create({
                name: `🎤 ${newState.member.user.username}`,
                type: ChannelType.GuildVoice,
                parent: guildConfig.tempVocCategory,
                permissionOverwrites: [
                    {
                        id: newState.member.id,
                        allow: [PermissionFlagsBits.ManageChannels, PermissionFlagsBits.MoveMembers]
                    }
                ]
            });

            await newState.member.voice.setChannel(tempChannel);

            if (!guildConfig.tempVocChannels) guildConfig.tempVocChannels = [];
            guildConfig.tempVocChannels.push(tempChannel.id);
            saveConfig();
        } catch (error) {
            console.error('Erreur création vocal temporaire:', error);
        }
    }

    // Supprimer les vocaux vides
    if (oldState.channel && guildConfig.tempVocChannels && guildConfig.tempVocChannels.includes(oldState.channelId)) {
        if (oldState.channel.members.size === 0) {
            try {
                await oldState.channel.delete();
                guildConfig.tempVocChannels = guildConfig.tempVocChannels.filter(id => id !== oldState.channelId);
                saveConfig();
            } catch (error) {
                console.error('Erreur suppression vocal:', error);
            }
        }
    }
});

// ======================================
// INSTRUCTIONS D'INSTALLATION
// ======================================
/*
1. Créer un fichier package.json avec:
{
  "name": "bot-discord-complet",
  "version": "1.0.0",
  "main": "index.js",
  "dependencies": {
    "discord.js": "^14.14.1"
  }
}

2. Installer les dépendances:
npm install

3. Remplacer 'VOTRE_TOKEN_ICI' par votre token de bot Discord

4. Lancer le bot:
node index.js

5. Inviter le bot avec ces permissions:
- Gérer les rôles
- Gérer les salons
- Bannir des membres
- Expulser des membres
- Gérer les messages
- Lire les messages
- Envoyer des messages
- Gérer les webhooks
- Ajouter des réactions
- Gérer les événements
- Tous les intents nécessaires

🎉 Votre bot est maintenant opérationnel!
*/

client.login('VOTRE_TOKEN_ICI');
