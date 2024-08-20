import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import yt_dlp as youtube_dl
import asyncio
import random
import wikipedia
from datetime import datetime, timedelta
import asyncio
from collections import deque, defaultdict
import pytz
import json
import time
import sqlite3
import requests
import matplotlib.pyplot as plt  # Assurez-vous d'avoir cette ligne d'importation
import io
from flask import Flask, render_template, request, redirect, url_for
import threading


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

app = Flask(__name__)
bot = commands.Bot(command_prefix='*', intents=intents)

# Dictionnaire pour suivre les avertissements des utilisateurs
user_warnings = defaultdict(int)
user_last_message_time = defaultdict(datetime)


# Route pour la page d'accueil
@app.route('/')
def index():
    return render_template('index.html')

# Route pour envoyer un message
@app.route('/send_message', methods=['POST'])
def send_message():
    channel_id = request.form['channel_id']
    message = request.form['message']
    channel = bot.get_channel(int(channel_id))
    if channel:
        bot.loop.create_task(channel.send(message))
    return redirect(url_for('index'))


# Configuration
spam_threshold = 5  # Nombre de messages autorisés par intervalle
interval = 10  # Intervalle de temps en secondes
mute_duration = 10  # Durée du mute en minutes
API_URL = 'https://api.coingecko.com/api/v3/simple/price'
API_URL = 'https://api.coingecko.com/api/v3/simple/price'
HISTORY_URL = 'https://api.coingecko.com/api/v3/coins/{id}/market_chart'

def get_db_connection():
    conn = sqlite3.connect('coins.db')
    conn.row_factory = sqlite3.Row
    return conn

# Connexion à la base de données
conn = sqlite3.connect('warnings.db')
c = conn.cursor()

# Création de la table "warnings" si elle n'existe pas
c.execute('''CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                reason TEXT
            )''')

conn.commit()
conn.close()


# Initialisation de la base de données
def init_db():
    conn = get_db_connection()
    with conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                coins INTEGER DEFAULT 0
            )
        ''')
    conn.close()

def init_db():
    """Initialise la base de données et crée les tables nécessaires."""
    conn = sqlite3.connect('giveaways.db')
    c = conn.cursor()

    # Crée la table pour les giveaways
    c.execute('''
        CREATE TABLE IF NOT EXISTS giveaways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            channel_id INTEGER,
            prize TEXT,
            ended INTEGER DEFAULT 0,
            start_time INTEGER
        )
    ''')

    # Crée la table pour les participants
    c.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            giveaway_id INTEGER,
            user_id INTEGER,
            FOREIGN KEY(giveaway_id) REFERENCES giveaways(id)
        )
    ''')

    conn.commit()
    conn.close()


youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'noplaylist': True,
    'cookiefile': 'path_to_your_cookies.txt',  # Ajoutez ceci pour utiliser des cookies
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

# Configuration de yt_dlp
ytdl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'api_key': 'AIzaSyAOJcRjZsWnbHSOZZh4SPbmKwVCsBapkP0',
}

# Configuration de ffmpeg
ffmpeg_opts = {
    'options': '-vn',
}


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.thumbnail = data.get('thumbnail')
        self.duration = data.get('duration')
        self.uploader = data.get('uploader')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        ytdl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
            'default_search': 'auto',
            'cookiefile': 'cookie.txt'  # Chemin vers votre fichier de cookies
        }
        ydl = youtube_dl.YoutubeDL(ytdl_opts)

        # Extract info from URL
        data = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=not stream))

        # Handle playlist case
        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ydl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **{'options': '-vn'}), data=data)


async def on_song_end(ctx):
    if ctx.guild.id in queues and queues[ctx.guild.id]:
        next_song = queues[ctx.guild.id].popleft()
        ctx.voice_client.play(next_song, after=lambda e: asyncio.run_coroutine_threadsafe(on_song_end(ctx), bot.loop))
        embed = discord.Embed(title=f'En train de jouer: {next_song.title}', color=discord.Color.blue())
        await ctx.send(embed=embed)
    else:
        await ctx.send("La file d'attente est vide.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(f"Vous n'avez pas les permissions nécessaires pour utiliser cette commande.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Argument manquant : {error.param}")
    else:
        await ctx.send(f"Une erreur est survenue : {str(error)}")


# Liste des réponses pour la commande ditmoi
magic_ball_responses = [
    "Oui", "Non", "Peut-être", "Certainement", "Je ne sais pas", "Redemande plus tard"
]

# Dictionnaires
queues = {}
giveaways = {}
last_messages = {}


@bot.event
async def on_ready():
    # Initialiser la base de données
    init_db()

    # Recharger les giveaways non terminés
    conn = sqlite3.connect('giveaways.db')
    c = conn.cursor()

    c.execute('SELECT id, message_id, channel_id FROM giveaways WHERE ended = 0')
    giveaways = c.fetchall()

    for giveaway in giveaways:
        channel = bot.get_channel(giveaway[2])
        if channel:
            try:
                message = await channel.fetch_message(giveaway[1])
                view = GiveawayView(giveaway_id=giveaway[0])
                await message.edit(view=view)
            except discord.NotFound:
                pass

    conn.close()
    print(f'{bot.user} est prêt et les giveaways ont été rechargés.')


@bot.command(name='prfx')
async def prfx(ctx):
    embed = discord.Embed(title=f'Le préfixe actuel est {bot.command_prefix}', color=discord.Color.blue())
    await ctx.send(embed=embed)


@bot.command(name='ban')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    try:
        await member.ban(reason=reason)
        await ctx.send(f'{member} a été banni.')
    except discord.Forbidden:
        await ctx.send("Je n'ai pas les permissions nécessaires pour bannir cet utilisateur.")
    except discord.HTTPException:
        await ctx.send("Une erreur est survenue lors de la tentative de bannissement de l'utilisateur.")


@bot.command(name='unban')
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, member_name):
    try:
        banned_users = [entry async for entry in ctx.guild.bans()]
        user_to_unban = None
        for ban_entry in banned_users:
            user = ban_entry.user
            if user.name == member_name:
                user_to_unban = user
                break

        if user_to_unban:
            await ctx.guild.unban(user_to_unban)
            await ctx.send(f'{user_to_unban.name} a été débanni.')
        else:
            await ctx.send(f'Membre {member_name} non trouvé.')
    except discord.Forbidden:
        await ctx.send("Je n'ai pas les permissions nécessaires pour débannir cet utilisateur.")
    except discord.HTTPException:
        await ctx.send("Une erreur est survenue lors de la tentative de débannissement de l'utilisateur.")


@bot.command(name='bjr')
async def bjr(ctx):
    await ctx.send('Bonjour!')


@bot.command(name='clear')
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    try:
        await ctx.channel.purge(limit=amount + 1)  # Ajoute 1 pour inclure la commande elle-même
        embed = discord.Embed(title=f'{amount} messages ont été supprimés.', color=discord.Color.blue())
        await ctx.send(embed=embed, delete_after=5)
    except discord.Forbidden:
        await ctx.send("Je n'ai pas les permissions nécessaires pour supprimer les messages.")
    except discord.HTTPException:
        await ctx.send("Une erreur est survenue lors de la tentative de suppression des messages.")


@bot.command(name='ditmoi')
async def ditmoi(ctx, *, question):
    response = random.choice(magic_ball_responses)
    embed = discord.Embed(title=f'Question: {question}\nRéponse: {response}', color=discord.Color.blue())
    await ctx.send(embed=embed)


@bot.command(name='ftg')
async def ftg(ctx):
    await ctx.send('Fermez-la, s\'il vous plaît.')


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = datetime.utcnow()
    user_id = message.author.id

    # Vérifie l'intervalle de temps depuis le dernier message
    if user_id in user_last_message_time:
        delta = now - user_last_message_time[user_id]
        if delta.seconds < interval:
            user_warnings[user_id] += 1
        else:
            user_warnings[user_id] = 1
    else:
        user_warnings[user_id] = 1

    user_last_message_time[user_id] = now

    # Gestion des avertissements et du mute
    if user_warnings[user_id] == 2:
        await message.channel.send(f"{message.author.mention}, ceci est votre premier avertissement pour spam.")
    elif user_warnings[user_id] == 3:
        await message.channel.send(f"{message.author.mention}, ceci est votre deuxième avertissement pour spam.")
    elif user_warnings[user_id] >= 4:
        await message.channel.send(f"{message.author.mention}, vous avez été muet pour spam.")
        mute_role = discord.utils.get(message.guild.roles, name="Muted")
        if not mute_role:
            mute_role = await message.guild.create_role(name="Muted")
            for channel in message.guild.channels:
                await channel.set_permissions(mute_role, speak=False, send_messages=False)

        await message.author.add_roles(mute_role)
        await asyncio.sleep(mute_duration * 60)
        await message.author.remove_roles(mute_role)
        user_warnings[user_id] = 0

    await bot.process_commands(message)


@bot.command(name='kick')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    try:
        await member.kick(reason=reason)
        await ctx.send(f'{member} a été expulsé.')
    except discord.Forbidden:
        await ctx.send("Je n'ai pas les permissions nécessaires pour expulser cet utilisateur.")
    except discord.HTTPException:
        await ctx.send("Une erreur est survenue lors de la tentative d'expulsion de l'utilisateur.")


@bot.command(name='lookup')
async def lookup(ctx, member: discord.Member):
    embed = discord.Embed(title=f'Informations sur {member}', description=f'Nom d\'utilisateur: {member.name}',
                          color=discord.Color.blue())
    embed.add_field(name='ID', value=member.id)
    embed.add_field(name='Rôles', value=", ".join([role.name for role in member.roles]))
    embed.add_field(name='A rejoint', value=member.joined_at)
    embed.set_thumbnail(url=member.avatar.url)
    await ctx.send(embed=embed)


# Vue personnalisée pour les boutons
class CommandView(View):
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author

    @discord.ui.button(label="Gestion du Serveur", style=discord.ButtonStyle.primary)
    async def server_management_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()  # Déférer l'interaction
        embed = discord.Embed(title="Gestion du Serveur", color=discord.Color.blue())
        embed.add_field(
            name="Gestion du Serveur - Partie 1",
            value=(
                "*ban [user]*: Ban un utilisateur du serveur (STAFF).\n"
                "*unban [user]*: Unban un utilisateur du serveur (STAFF).\n"
                "*kick [user]*: Kick un utilisateur du serveur (STAFF).\n"
                "*mute [user]*: Rend un utilisateur muet (STAFF).\n"
                "*unmute [user]*: Redonne la parole à un utilisateur (STAFF).\n"
                "*timeout [user] [duration] [reason]*: Exclut temporairement un utilisateur (STAFF).\n"
                "*report [@user] [reason]*: permet de report une infraction dun utilisateur. (STAFF)\n"
                "*viewreport*: permet de voir tout les reports des utilisateur. (STAFF)"
            ),
            inline=False
        )
        embed.add_field(
            name="Gestion du Serveur - Partie 2",
            value=(
                "*nick [user] [new_nick]*: Change le pseudonyme d'un utilisateur (STAFF).\n"
                "*clear [amount]*: Efface un nombre de messages spécifié (STAFF).\n"
                "*ftg*: Ferme les conversations inutiles.\n"
                "*bjr*: Envoie un message de salutation.\n"
                "*adc [@user] [Amount]*: Ajouter des coins à l'utilisateur mentionné (STAFF).\n"
                "*rmc [@user] [Amount]*: Retirer des coins à l'utilisateur mentionné (STAFF).\n"
                "*lookblc [@user]*: Regarder la balance d'un utilisateur (STAFF).\n"
                "*warn [@user]*: Warn un utilisateur (STAFF).\n"
                "*removewarn [@user]*: Enlever un warn à un utilisateur (STAFF).\n"
                "*clearwarns [@user]*: Enlever tous les warns à un utilisateur (STAFF).\n"
                "*auditlog*: Affiche les derniers événements importants (STAFF)."
            ),
            inline=False
        )
        await interaction.edit_original_response(embed=embed)

    # Bouton pour la catégorie "Informations"
    @discord.ui.button(label="Informations", style=discord.ButtonStyle.primary)
    async def information_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()  # Déférer l'interaction
        embed = discord.Embed(title="Informations", color=discord.Color.blue())
        embed.add_field(
            name="Informations Générales",
            value=(
                "*lookup [user]*: Affiche des informations sur un utilisateur.\n"
                "*mb*: Affiche le nombre de membres sur le serveur.\n"
                "*servinfo*: Affiche des informations sur le serveur.\n"
                "*stats*: Affiche des statistiques du serveur.\n"
                "*wiki [Recherche]*: Recherche des informations sur Wikipédia.\n"
                "*define [mot]*: Donne la définition d'un mot.\n"
                "*info*: Affiche des informations sur le bot, comme la version, le créateur, etc."
            ),
            inline=False
        )
        await interaction.edit_original_response(embed=embed)

    # Bouton pour la catégorie "Musique"
    @discord.ui.button(label="Musique", style=discord.ButtonStyle.primary)
    async def music_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()  # Déférer l'interaction
        embed = discord.Embed(title="Commandes de Musique", color=discord.Color.blue())
        embed.add_field(
            name="Commandes de Musique",
            value=(
                "*play [url]*: Joue de la musique à partir d'un lien YouTube.\n"
                "*vol [value]*: Change le volume du bot (en pourcentage).\n"
                "*pause*: Met en pause le son que le bot joue en vocal.\n"
                "*resume*: Reprend la lecture du son.\n"
                "*skip*: Passe au prochain son dans la file d'attente.\n"
                "*queue*: Montre la file d'attente.\n"
                "*leave*: Fait quitter le bot du canal vocal."
            ),
            inline=False
        )
        await interaction.edit_original_response(embed=embed)

    # Bouton pour la catégorie "Giveaways"
    @discord.ui.button(label="Giveaways", style=discord.ButtonStyle.primary)
    async def giveaways_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()  # Déférer l'interaction
        embed = discord.Embed(title="Giveaways", color=discord.Color.blue())
        embed.add_field(
            name="Commandes de Giveaways",
            value=(
                "*start_giveaway <duration> <prize>*: Lance un nouveau giveaway. Les utilisateurs peuvent participer en réagissant avec 🎉.\n"
                "*reroll <message_id>*: Relance un giveaway pour choisir un nouveau gagnant.\n"
                "*end_giveaway <message_id>*: Met fin à un giveaway prématurément et choisit un gagnant."
            ),
            inline=False
        )
        await interaction.edit_original_response(embed=embed)

    # Bouton pour la catégorie "Jeux"
    @discord.ui.button(label="Jeux", style=discord.ButtonStyle.primary)
    async def play_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()  # Déférer l'interaction
        embed = discord.Embed(title="Jeux", color=discord.Color.blue())
        embed.add_field(
            name="Commandes de Jeux",
            value=(
                "*balance*: Affiche votre solde actuel de coins.\n"
                "*guess <nombre>*: Devinez un chiffre entre 1 et 10 pour tenter de gagner 10 coins.\n"
                "*bj <mise>*: Jouez une partie de Blackjack avec la somme indiquée."
                "*rule_bj*: affiche les regle simplifiée du blackjack."
            ),
            inline=False
        )
        await interaction.edit_original_response(embed=embed)


# Commande !cmd pour afficher les commandes disponibles avec des boutons
@bot.command(name='cmd')
async def cmd(ctx):
    embed = discord.Embed(title="Choisissez une catégorie",
                          description="Cliquez sur un des boutons ci-dessous pour voir les commandes correspondantes.",
                          color=discord.Color.green())
    view = CommandView(ctx)
    await ctx.send(embed=embed, view=view)
    await ctx.message.delete()

class CryptoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Bitcoin", style=discord.ButtonStyle.primary)
    async def bitcoin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_crypto_price(interaction, 'bitcoin')

    @discord.ui.button(label="Ethereum", style=discord.ButtonStyle.primary)
    async def ethereum_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_crypto_price(interaction, 'ethereum')

    async def send_crypto_price(self, interaction: discord.Interaction, coin: str):
        # Récupération du prix actuel
        response = requests.get(API_URL, params={'ids': coin, 'vs_currencies': 'usd'})
        data = response.json()
        price = data[coin]['usd']

        # Récupération de l'historique des prix sur 7 jours
        history_response = requests.get(HISTORY_URL.format(id=coin), params={'vs_currency': 'usd', 'days': '7'})
        history_data = history_response.json()

        # Préparation des données pour le graphique
        prices = [point[1] for point in history_data['prices']]
        dates = [point[0] for point in history_data['prices']]

        # Création du graphique avec un thème sombre
        plt.style.use('dark_background')
        plt.figure(figsize=(10, 6))
        plt.plot(dates, prices, color='cyan', linestyle='-', marker='o')
        plt.title(f'{coin.capitalize()} Price Over Last 7 Days', fontsize=16, color='white')
        plt.xlabel('Date', fontsize=14, color='white')
        plt.ylabel('Price (USD)', fontsize=14, color='white')

        # Sauvegarde du graphique dans un objet BytesIO
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)

        # Création de l'embed avec l'image du graphique
        embed = discord.Embed(title=f'Prix actuel de {coin.capitalize()}: ${price}', color=discord.Color.dark_blue())
        embed.set_image(url='attachment://crypto_graph.png')

        await interaction.response.send_message(embed=embed, file=discord.File(fp=buffer, filename='crypto_graph.png'))

# Commande pour afficher les boutons de sélection de cryptomonnaie
@bot.command(name='crypto')
async def crypto(ctx):
    view = CryptoView()
    embed = discord.Embed(title="Sélectionnez une cryptomonnaie", description="Cliquez sur un bouton pour voir le prix et la courbe des 7 derniers jours.", color=discord.Color.dark_gold())
    await ctx.send(embed=embed, view=view)

@bot.event
async def on_message(message):
    if not message.author.bot:
        # Log the message content for debugging
        print(f"Message received in {message.channel.name}: {message.content}")
        last_messages[message.channel.id] = message
    await bot.process_commands(message)


@bot.command(name='auditlog')
@commands.has_permissions(administrator=True)
async def auditlog(ctx, limit: int = 5):
    """Affiche les derniers événements importants sur le serveur."""
    if limit > 10:
        await ctx.send("Veuillez limiter le nombre de logs à 10 ou moins.")
        return

    # Récupérer les logs d'audit
    logs = await ctx.guild.audit_logs(limit=limit).flatten()

    if not logs:
        await ctx.send("Aucun log d'audit trouvé.")
        return

    # Création de l'embed pour afficher les logs
    embed = discord.Embed(title="Logs d'Audit", color=discord.Color.blue())

    for log in logs:
        action_type = log.action
        if action_type == discord.AuditLogAction.ban:
            action = "Bannissement"
        elif action_type == discord.AuditLogAction.unban:
            action = "Débannissement"
        elif action_type == discord.AuditLogAction.member_update:
            action = "Mise à jour de membre"
        elif action_type == discord.AuditLogAction.role_update:
            action = "Mise à jour de rôle"
        elif action_type == discord.AuditLogAction.message_delete:
            action = "Suppression de message"
        else:
            action = "Autre"

        embed.add_field(name=f"ID de l'événement: {log.id}",
                        value=f"Action: {action}\nAuteur: {log.user}\nDate: {log.created_at}\nDetails: {log.reason or 'Aucun détail'}",
                        inline=False)

    await ctx.send(embed=embed)

@bot.command(name='warn')
@commands.has_permissions(manage_roles=True)
async def warn(ctx, member: discord.Member, *, reason=None):
    conn = sqlite3.connect('warnings.db')
    c = conn.cursor()

    c.execute("INSERT INTO warnings (user_id, guild_id, reason) VALUES (?, ?, ?)",
              (member.id, ctx.guild.id, reason))

    conn.commit()
    conn.close()

    embed = discord.Embed(title="Avertissement 🚨",
                          description=f"{member.mention} a été averti.",
                          color=discord.Color.red())
    embed.add_field(name="Raison", value=reason, inline=False)
    embed.set_footer(text=f"Averti par {ctx.author}", icon_url=ctx.author.avatar.url)

    await ctx.send(embed=embed)

@bot.command(name='warns')
async def view_warns(ctx, member: discord.Member):
    conn = sqlite3.connect('warnings.db')
    c = conn.cursor()

    c.execute("SELECT reason FROM warnings WHERE user_id = ? AND guild_id = ?",
              (member.id, ctx.guild.id))
    warns = c.fetchall()

    conn.close()

    if warns:
        embed = discord.Embed(title=f"Avertissements pour {member.display_name}", color=discord.Color.orange())
        for idx, warn in enumerate(warns, 1):
            embed.add_field(name=f"Avertissement {idx}", value=warn[0], inline=False)
        embed.set_thumbnail(url=member.avatar.url)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(description=f"{member.mention} n'a aucun avertissement.", color=discord.Color.green())
        await ctx.send(embed=embed)

@bot.command(name='clearwarns')
@commands.has_permissions(manage_roles=True)
async def clear_warns(ctx, member: discord.Member):
    conn = sqlite3.connect('warnings.db')
    c = conn.cursor()

    c.execute("DELETE FROM warnings WHERE user_id = ? AND guild_id = ?", (member.id, ctx.guild.id))
    conn.commit()
    conn.close()

    embed = discord.Embed(title="Avertissements supprimés 🧹",
                          description=f"Tous les avertissements pour {member.mention} ont été supprimés.",
                          color=discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name='lookblc')
@commands.has_permissions(administrator=True)
async def look_balance(ctx, member: discord.Member):
    user_id = member.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT coins FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        coins = result['coins']
    else:
        coins = 0  # Si l'utilisateur n'existe pas encore, il a 0 coins

    embed = discord.Embed(title="Consultation de la Balance", color=discord.Color.blue())
    embed.add_field(name="Utilisateur", value=member.mention, inline=False)
    embed.add_field(name="Coins", value=f"{coins} coins", inline=False)
    await ctx.send(embed=embed)


@bot.command(name='adc')
@commands.has_permissions(administrator=True)
async def add_coins(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("Le montant à ajouter doit être supérieur à 0.")
        return

    user_id = member.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT coins FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()

    if result:
        new_coins = result['coins'] + amount
        conn.execute('UPDATE users SET coins = ? WHERE user_id = ?', (new_coins, user_id))
    else:
        new_coins = amount
        conn.execute('INSERT INTO users (user_id, coins) VALUES (?, ?)', (user_id, new_coins))

    conn.commit()
    conn.close()

    embed = discord.Embed(title="Ajout de Coins", color=discord.Color.green())
    embed.add_field(name="Utilisateur", value=member.mention, inline=False)
    embed.add_field(name="Montant Ajouté", value=f"{amount} coins", inline=False)
    embed.add_field(name="Nouveau Solde", value=f"{new_coins} coins", inline=False)
    await ctx.send(embed=embed)


@bot.command(name='rmc')
@commands.has_permissions(administrator=True)
async def remove_coins(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("Le montant à retirer doit être supérieur à 0.")
        return

    user_id = member.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT coins FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()

    if not result:
        await ctx.send(f"L'utilisateur {member.mention} n'a pas de coins à retirer.")
        conn.close()
        return

    current_coins = result['coins']
    if amount > current_coins:
        await ctx.send(
            f"L'utilisateur {member.mention} n'a que {current_coins} coins. Vous ne pouvez pas retirer plus.")
        conn.close()
        return

    new_coins = current_coins - amount
    conn.execute('UPDATE users SET coins = ? WHERE user_id = ?', (new_coins, user_id))
    conn.commit()
    conn.close()

    embed = discord.Embed(title="Retrait de Coins", color=discord.Color.red())
    embed.add_field(name="Utilisateur", value=member.mention, inline=False)
    embed.add_field(name="Montant Retiré", value=f"{amount} coins", inline=False)
    embed.add_field(name="Nouveau Solde", value=f"{new_coins} coins", inline=False)
    await ctx.send(embed=embed)


@bot.command(name='rule_bj')
async def rule_bj(ctx):
    embed = discord.Embed(title="Règles Simplifiées du Blackjack", color=discord.Color.blue())

    # Objectif du jeu
    embed.add_field(
        name="🎯 Objectif",
        value="Atteindre un total de 21 points ou s'en approcher le plus possible, sans dépasser.",
        inline=False
    )

    # Valeur des cartes
    embed.add_field(
        name="📊 Valeur des Cartes",
        value=(
            " - **Cartes numérotées (2-10)** : Valeur égale à leur numéro.\n"
            " - **Figures (Roi, Dame, Valet)** : 10 points.\n"
            " - **As** : 1 ou 11 points, selon ce qui est le plus avantageux."
        ),
        inline=False
    )

    # Déroulement du jeu
    embed.add_field(
        name="🔄 Déroulement",
        value=(
            "1. **Vous** recevez 2 cartes, le dealer aussi.\n"
            "2. Choisissez `Hit` pour tirer une carte ou `Stand` pour garder votre main.\n"
            "3. Le dealer doit tirer jusqu'à atteindre 17 points ou plus."
        ),
        inline=False
    )

    # Victoire
    embed.add_field(
        name="🏆 Victoire",
        value=(
            " - **Blackjack** : Un As et une carte valant 10 points.\n"
            " - **Gagnez** si votre total est plus proche de 21 que celui du dealer, sans dépasser 21."
        ),
        inline=False
    )

    embed.set_footer(text="Jouez prudemment et amusez-vous bien !")

    await ctx.send(embed=embed)


@bot.command(name='dernier_message')
async def dernier_message(ctx):
    channel_id = ctx.channel.id
    if channel_id in last_messages:
        last_msg = last_messages[channel_id]
        embed = discord.Embed(
            title="Dernier Message",
            description=last_msg.content,
            color=discord.Color.blue()
        )
        embed.set_author(name=last_msg.author.display_name, icon_url=last_msg.author.avatar.url)
        embed.set_footer(text=f"Envoyé à {last_msg.created_at}")
        await ctx.send(embed=embed)
    else:
        await ctx.send("Aucun message enregistré pour ce canal.")


@bot.command(name='setprefix')
@commands.has_permissions(administrator=True)
async def setprefix(ctx, new_prefix: str):
    bot.command_prefix = new_prefix
    await ctx.send(f"Le préfixe des commandes a été changé en {new_prefix}")


@bot.command(name='rps')
async def rps(ctx, choice: str):
    choices = ['pierre', 'papier', 'ciseaux']
    if choice not in choices:
        await ctx.send("Choisissez entre 'pierre', 'papier' et 'ciseaux'.")
        return

    bot_choice = random.choice(choices)
    if choice == bot_choice:
        result = "Égalité !"
    elif (choice == 'pierre' and bot_choice == 'ciseaux') or \
            (choice == 'papier' and bot_choice == 'pierre') or \
            (choice == 'ciseaux' and bot_choice == 'papier'):
        result = "Vous avez gagné !"
    else:
        result = "Vous avez perdu !"

    await ctx.send(f"Vous avez choisi {choice}. Le bot a choisi {bot_choice}. {result}")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = datetime.utcnow()

    # Vérifie si l'utilisateur a envoyé un message récemment
    if message.author.id in user_last_message_time:
        delta = now - user_last_message_time[message.author.id]
        if delta.seconds < interval:
            user_warnings[message.author.id] += 1
        else:
            user_warnings[message.author.id] = 1
    else:
        user_warnings[message.author.id] = 1

    user_last_message_time[message.author.id] = now

    # Avertissement et mute
    if user_warnings[message.author.id] == 2:
        await message.channel.send(f"{message.author.mention}, ceci est votre premier avertissement pour spam.")
    elif user_warnings[message.author.id] == 3:
        await message.channel.send(f"{message.author.mention}, ceci est votre deuxième avertissement pour spam.")
    elif user_warnings[message.author.id] >= 4:
        await message.channel.send(f"{message.author.mention}, vous avez été muet pour spam.")
        mute_role = discord.utils.get(message.guild.roles, name="Muted")
        if not mute_role:
            mute_role = await message.guild.create_role(name="Muted")
            for channel in message.guild.channels:
                await channel.set_permissions(mute_role, speak=False, send_messages=False)

        await message.author.add_roles(mute_role)
        await asyncio.sleep(mute_duration * 60)
        await message.author.remove_roles(mute_role)
        user_warnings[message.author.id] = 0

    await bot.process_commands(message)


# Vérifie la balance des coins d'un utilisateur
@bot.command(name='balance')
async def balance(ctx):
    user_id = ctx.author.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT coins FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        coins = result['coins']
    else:
        coins = 0
        conn = get_db_connection()
        conn.execute('INSERT INTO users (user_id, coins) VALUES (?, ?)', (user_id, coins))
        conn.commit()
        conn.close()

    embed = discord.Embed(title="Votre Balance de Coins", color=discord.Color.green())
    embed.add_field(name="Utilisateur", value=ctx.author.mention, inline=False)
    embed.add_field(name="Coins", value=f"{coins} coins", inline=False)
    await ctx.send(embed=embed)


# Commande de devinette
class GuessView(View):
    def __init__(self, ctx, target_number, user_id, conn):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.target_number = target_number
        self.user_id = user_id
        self.conn = conn

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Vérifie que l'interaction provient de l'utilisateur qui a exécuté la commande
        return interaction.user == self.ctx.author

    async def handle_guess(self, interaction: discord.Interaction, guess: int):
        # Gère la réponse de l'utilisateur
        if guess == self.target_number:
            embed = discord.Embed(title="Guess the Number", color=discord.Color.green())
            embed.add_field(name="Bravo ! 🎉", value=f"Vous avez deviné correctement {guess} ! Vous gagnez 10 coins.",
                            inline=False)
            self.conn.execute('UPDATE users SET coins = coins + 10 WHERE user_id = ?', (self.user_id,))
        else:
            embed = discord.Embed(title="Dommage !", color=discord.Color.red())
            embed.add_field(name="Résultat", value=f"Le bon numéro était {self.target_number}.", inline=False)

        self.conn.commit()
        self.conn.close()
        self.clear_items()  # Désactive les boutons après la fin du jeu
        await interaction.response.edit_message(embed=embed, view=None)  # Met à jour le message avec le résultat

    @discord.ui.button(label="1", style=discord.ButtonStyle.blurple)
    async def guess_1(self, interaction: discord.Interaction, button: Button):
        await self.handle_guess(interaction, 1)

    @discord.ui.button(label="2", style=discord.ButtonStyle.blurple)
    async def guess_2(self, interaction: discord.Interaction, button: Button):
        await self.handle_guess(interaction, 2)

    @discord.ui.button(label="3", style=discord.ButtonStyle.blurple)
    async def guess_3(self, interaction: discord.Interaction, button: Button):
        await self.handle_guess(interaction, 3)

    @discord.ui.button(label="4", style=discord.ButtonStyle.blurple)
    async def guess_4(self, interaction: discord.Interaction, button: Button):
        await self.handle_guess(interaction, 4)

    @discord.ui.button(label="5", style=discord.ButtonStyle.blurple)
    async def guess_5(self, interaction: discord.Interaction, button: Button):
        await self.handle_guess(interaction, 5)

    @discord.ui.button(label="6", style=discord.ButtonStyle.blurple)
    async def guess_6(self, interaction: discord.Interaction, button: Button):
        await self.handle_guess(interaction, 6)

    @discord.ui.button(label="7", style=discord.ButtonStyle.blurple)
    async def guess_7(self, interaction: discord.Interaction, button: Button):
        await self.handle_guess(interaction, 7)

    @discord.ui.button(label="8", style=discord.ButtonStyle.blurple)
    async def guess_8(self, interaction: discord.Interaction, button: Button):
        await self.handle_guess(interaction, 8)

    @discord.ui.button(label="9", style=discord.ButtonStyle.blurple)
    async def guess_9(self, interaction: discord.Interaction, button: Button):
        await self.handle_guess(interaction, 9)

    @discord.ui.button(label="10", style=discord.ButtonStyle.blurple)
    async def guess_10(self, interaction: discord.Interaction, button: Button):
        await self.handle_guess(interaction, 10)


@bot.command(name='guess')
async def guess(ctx):
    user_id = ctx.author.id
    conn = get_db_connection()

    # Définir le numéro cible aléatoire entre 1 et 10
    target_number = random.randint(1, 10)
    view = GuessView(ctx, target_number, user_id, conn)

    embed = discord.Embed(title="Guess the Number", color=discord.Color.blue())
    embed.add_field(name="Devinez un nombre entre 1 et 10", value="Cliquez sur le bouton correspondant à votre choix.",
                    inline=False)
    embed.set_footer(text="Si vous devinez correctement, vous gagnez 10 coins !")

    await ctx.send(embed=embed, view=view)


class BlackjackView(View):
    def __init__(self, ctx, player_hand, dealer_hand, bet, user_id, conn):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.bet = bet
        self.user_id = user_id
        self.conn = conn

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author

    async def hit_button(self, interaction: discord.Interaction, button: Button):
        self.player_hand.append(random.randint(1, 11))  # Ajouter une carte aléatoire
        player_score = sum(self.player_hand)

        if player_score > 21:
            await self.end_game(interaction, "Perdu", player_score)
        else:
            embed = discord.Embed(title="Blackjack", color=discord.Color.blue())
            embed.add_field(name="Main du joueur", value=f"{self.player_hand} (Total: {player_score})", inline=False)
            embed.add_field(name="Main du dealer", value=f"{self.dealer_hand[0]} et ?", inline=False)
            await interaction.response.edit_message(embed=embed, view=self)

    async def stand_button(self, interaction: discord.Interaction, button: Button):
        player_score = sum(self.player_hand)
        dealer_score = sum(self.dealer_hand)

        while dealer_score < 17:
            self.dealer_hand.append(random.randint(1, 11))
            dealer_score = sum(self.dealer_hand)

        if dealer_score > 21 or player_score > dealer_score:
            await self.end_game(interaction, "Gagné", player_score, dealer_score)
        else:
            await self.end_game(interaction, "Perdu", player_score, dealer_score)

    async def end_game(self, interaction: discord.Interaction, result, player_score, dealer_score=None):
        if result == "Gagné":
            self.conn.execute('UPDATE users SET coins = coins + ? WHERE user_id = ?', (self.bet * 2, self.user_id))
        else:
            self.conn.execute('UPDATE users SET coins = coins - ? WHERE user_id = ?', (self.bet, self.user_id))

        self.conn.commit()
        self.conn.close()
        self.clear_items()  # Désactive les boutons après la fin du jeu

        embed = discord.Embed(title="Blackjack",
                              color=discord.Color.green() if result == "Gagné" else discord.Color.red())
        embed.add_field(name="Résultat", value=f"Vous avez {result} !", inline=False)
        embed.add_field(name="Votre main", value=f"{self.player_hand} (Total: {player_score})", inline=False)
        if dealer_score is not None:
            embed.add_field(name="Main du dealer", value=f"{self.dealer_hand} (Total: {dealer_score})", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.blurple)
    async def hit(self, interaction: discord.Interaction, button: Button):
        await self.hit_button(interaction, button)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.green)
    async def stand(self, interaction: discord.Interaction, button: Button):
        await self.stand_button(interaction, button)


@bot.command(name='bj')
async def blackjack(ctx, bet: int):
    user_id = ctx.author.id
    conn = get_db_connection()

    # Vérification du solde
    user_balance = conn.execute('SELECT coins FROM users WHERE user_id = ?', (user_id,)).fetchone()[0]
    if user_balance < bet:
        await ctx.send("Vous n'avez pas assez de coins pour parier cette somme.")
        conn.close()
        return

    player_hand = [random.randint(1, 11), random.randint(1, 11)]
    dealer_hand = [random.randint(1, 11), random.randint(1, 11)]

    embed = discord.Embed(title="Blackjack", color=discord.Color.blue())
    embed.add_field(name="Votre main", value=f"{player_hand} (Total: {sum(player_hand)})", inline=False)
    embed.add_field(name="Main du dealer", value=f"{dealer_hand[0]} et ?", inline=False)

    view = BlackjackView(ctx, player_hand, dealer_hand, bet, user_id, conn)
    await ctx.send(embed=embed, view=view)


@bot.command(name='vol')
async def vol(ctx, volume: int):
    if ctx.voice_client is None:
        embed = discord.Embed(title="Erreur", description="Je ne suis pas connecté à un canal vocal.",
                              color=discord.Color.red())
        return await ctx.send(embed=embed)

    if volume < 0:
        embed = discord.Embed(title="Erreur", description="Le volume ne peut pas être négatif.",
                              color=discord.Color.red())
        return await ctx.send(embed=embed)

    if volume > 100:
        embed = discord.Embed(
            title="Confirmation requise",
            description=f"Vous êtes sur le point de définir le volume à {volume}%. Cela peut entraîner une distorsion. Êtes-vous sûr de vouloir continuer? Réagissez avec ✅ pour confirmer ou ❌ pour annuler.",
            color=discord.Color.orange()
        )
        message = await ctx.send(embed=embed)
        await message.add_reaction('✅')
        await message.add_reaction('❌')

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['✅', '❌'] and reaction.message.id == message.id

        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await message.edit(content="Temps écoulé. Modification du volume annulée.", embed=None)
            return

        if str(reaction.emoji) == '✅':
            ctx.voice_client.source.volume = volume / 100
            embed = discord.Embed(
                title="Volume modifié",
                description=f"Le volume est maintenant à {volume}%. (Note: Au-dessus de 100% peut entraîner une distorsion.)",
                color=discord.Color.yellow()
            )
            await message.edit(embed=embed)
        else:
            await message.edit(content="Modification du volume annulée.", embed=None)
    else:
        ctx.voice_client.source.volume = volume / 100
        embed = discord.Embed(
            title="Volume modifié",
            description=f"Le volume est maintenant à {volume}%.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)


# Commande !info
@bot.command(name='info')
async def info(ctx):
    embed = discord.Embed(title="Informations sur le Bot", color=discord.Color.blue())
    embed.add_field(name="Nom du Bot", value=bot.user.name, inline=False)
    embed.add_field(name="ID du Bot", value=bot.user.id, inline=False)
    embed.add_field(name="Serveurs", value=len(bot.guilds), inline=False)
    embed.add_field(name="Utilisateurs", value=sum(len(g.members) for g in bot.guilds), inline=False)
    embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.avatar.url)  # Changement ici

    await ctx.send(embed=embed)


# Questions de trivia avec réponses correctes
trivia_questions = [
    {
        "question": "Quel est le plus grand océan sur Terre?",
        "options": ["Atlantique", "Indien", "Arctique", "Pacifique"],
        "answer": "Pacifique"
    },
    {
        "question": "Quel est l'élément chimique dont le symbole est 'O'?",
        "options": ["Oxygène", "Or", "Osmium", "Oxyde"],
        "answer": "Oxygène"
    },
    {
        "question": "Quel est le pays le plus peuplé du monde?",
        "options": ["États-Unis", "Inde", "Chine", "Brésil"],
        "answer": "Chine"
    }
]


# Commande !trivia
@bot.command(name='trivia')
async def trivia(ctx):
    # Sélectionner une question aléatoire
    question = random.choice(trivia_questions)

    # Créer une chaîne de caractères pour les options
    options = "\n".join([f"{chr(0x0031 + i) + chr(0x20E3)} {option}" for i, option in enumerate(question['options'])])

    # Envoyer la question et les options
    trivia_message = await ctx.send(f"{question['question']}\n\n{options}")

    # Ajouter des réactions pour les options (1️⃣, 2️⃣, 3️⃣, 4️⃣)
    for i in range(len(question['options'])):
        await trivia_message.add_reaction(chr(0x0031 + i) + chr(0x20E3))

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ['1️⃣', '2️⃣', '3️⃣', '4️⃣']

    try:
        # Attendre la réaction de l'utilisateur
        reaction, _ = await bot.wait_for('reaction_add', timeout=30.0, check=check)

        # Trouver l'index de la réponse sélectionnée
        selected_option_index = ['1️⃣', '2️⃣', '3️⃣', '4️⃣'].index(str(reaction.emoji))
        selected_answer = question['options'][selected_option_index]

        # Vérifier la réponse
        if selected_answer == question['answer']:
            await ctx.send(f"Bonne réponse ! La réponse correcte était '{question['answer']}'.")
        else:
            await ctx.send(f"Mauvaise réponse. La réponse correcte était '{question['answer']}'.")

    except asyncio.TimeoutError:
        await ctx.send("Délai écoulé. Veuillez réessayer.")


@bot.command(name='define')
async def define(ctx, word: str):
    api_url = f"https://api.dictionaryapi.dev/api/v2/entries/fr/{word}"
    response = requests.get(api_url)

    if response.status_code == 200:
        data = response.json()
        meaning = data[0]['meanings'][0]['definitions'][0]['definition']
        await ctx.send(f"Définition de '{word}': {meaning}")
    else:
        await ctx.send(f"Désolé, je n'ai pas pu trouver la définition pour '{word}'.")


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.participants = []
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="Participer 🎉", style=discord.ButtonStyle.primary)
    async def participate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.participants:
            await interaction.response.send_message("Vous avez déjà participé !", ephemeral=True)
        else:
            self.participants.append(interaction.user.id)
            # Ajouter le participant à la base de données
            conn = sqlite3.connect('giveaways.db')
            c = conn.cursor()
            c.execute('INSERT INTO participants (giveaway_id, user_id) VALUES (?, ?)',
                      (self.giveaway_id, interaction.user.id))
            conn.commit()
            conn.close()
            await interaction.response.send_message("Participation enregistrée !", ephemeral=True)


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.participants = []
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="Participer 🎉", style=discord.ButtonStyle.primary)
    async def participate(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = sqlite3.connect('giveaways.db')
        c = conn.cursor()

        # Vérifie si le giveaway est terminé
        c.execute('SELECT ended FROM giveaways WHERE id = ?', (self.giveaway_id,))
        giveaway = c.fetchone()
        conn.close()

        if giveaway and giveaway[0] == 1:
            await interaction.response.send_message("Ce giveaway est déjà terminé.", ephemeral=True)
            return

        if interaction.user.id in self.participants:
            await interaction.response.send_message("Vous avez déjà participé !", ephemeral=True)
        else:
            self.participants.append(interaction.user.id)
            # Ajouter le participant à la base de données
            conn = sqlite3.connect('giveaways.db')
            c = conn.cursor()
            c.execute('INSERT INTO participants (giveaway_id, user_id) VALUES (?, ?)',
                      (self.giveaway_id, interaction.user.id))
            conn.commit()
            conn.close()
            await interaction.response.send_message("Participation enregistrée !", ephemeral=True)


@bot.command(name='start_giveaway')
@commands.has_permissions(administrator=True)
async def start_giveaway(ctx, duration: int, *, prize: str):
    """Lance un giveaway avec une durée en secondes et un prix spécifié."""
    view = GiveawayView(giveaway_id=None)

    embed = discord.Embed(title="🎉 Giveaway !", description=f"Prix : **{prize}**", color=discord.Color.green())
    embed.add_field(name="Durée", value="Calcul en cours...", inline=False)
    embed.add_field(name="Participants", value="0", inline=False)
    embed.set_footer(text="Cliquez sur le bouton pour participer !")

    giveaway_message = await ctx.send(embed=embed, view=view)

    # Enregistrer dans la base de données
    conn = sqlite3.connect('giveaways.db')
    c = conn.cursor()
    c.execute('INSERT INTO giveaways (message_id, channel_id, prize, start_time) VALUES (?, ?, ?, ?)',
              (giveaway_message.id, ctx.channel.id, prize, int(time.time())))
    giveaway_id = c.lastrowid
    conn.commit()
    conn.close()

    view.giveaway_id = giveaway_id

    end_time = time.time() + duration
    while time.time() < end_time:
        remaining_time = int(end_time - time.time())
        hours, remainder = divmod(remaining_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_display = f"{hours} h {minutes} min {seconds} s"

        # Mettre à jour le nombre de participants
        conn = sqlite3.connect('giveaways.db')
        c = conn.cursor()
        c.execute('SELECT COUNT(user_id) FROM participants WHERE giveaway_id = ?', (giveaway_id,))
        participant_count = c.fetchone()[0]
        conn.close()

        embed.set_field_at(0, name="Durée", value=time_display, inline=False)
        embed.set_field_at(1, name="Participants", value=str(participant_count), inline=False)
        await giveaway_message.edit(embed=embed)

        await asyncio.sleep(1)  # Mettre à jour toutes les secondes

    # Terminer le giveaway
    await end_giveaway(ctx, giveaway_id)


async def end_giveaway(ctx, giveaway_id):
    """Termine un giveaway et sélectionne un gagnant."""
    conn = sqlite3.connect('giveaways.db')
    c = conn.cursor()

    # Obtenir les informations du giveaway
    c.execute('SELECT message_id, channel_id, prize, ended FROM giveaways WHERE id = ?', (giveaway_id,))
    giveaway = c.fetchone()

    if not giveaway:
        await ctx.send("Giveaway non trouvé ou déjà terminé.")
        conn.close()
        return

    if giveaway[3] == 1:
        await ctx.send("Le giveaway est déjà terminé.")
        conn.close()
        return

    # Obtenir les participants
    c.execute('SELECT user_id FROM participants WHERE giveaway_id = ?', (giveaway_id,))
    participants = [row[0] for row in c.fetchall()]

    if not participants:
        await ctx.send("Aucun participant au giveaway.")
        conn.close()
        return

    # Sélectionner un gagnant
    winner_id = random.choice(participants)
    winner = bot.get_user(winner_id)

    # Envoyer le message de fin
    embed = discord.Embed(title="🎉 Giveaway Terminé !",
                          description=f"Le gagnant est {winner.mention} pour **{giveaway[2]}**!",
                          color=discord.Color.gold())
    channel = bot.get_channel(giveaway[1])
    if channel:
        try:
            message = await channel.fetch_message(giveaway[0])
            await message.edit(embed=embed, view=None)
        except discord.NotFound:
            pass

    # Envoyer le message de notification
    await ctx.send(embed=embed)

    # Marquer le giveaway comme terminé dans la base de données
    c.execute('UPDATE giveaways SET ended = 1 WHERE id = ?', (giveaway_id,))
    conn.commit()
    conn.close()


@bot.event
async def on_ready():
    # Initialiser la base de données
    init_db()

    # Recharger les giveaways non terminés
    conn = sqlite3.connect('giveaways.db')
    c = conn.cursor()

    c.execute('SELECT id, message_id, channel_id FROM giveaways WHERE ended = 0')
    giveaways = c.fetchall()

    for giveaway in giveaways:
        channel = bot.get_channel(giveaway[2])
        if channel:
            try:
                message = await channel.fetch_message(giveaway[1])
                view = GiveawayView(giveaway_id=giveaway[0])
                await message.edit(view=view)
            except discord.NotFound:
                # Si le message est supprimé, le giveaway ne peut pas être rechargé
                pass


@bot.command(name='reroll')
@commands.has_permissions(administrator=True)
async def reroll(ctx, giveaway_id: int):
    """Relance le tirage au sort pour un giveaway existant."""
    conn = sqlite3.connect('giveaways.db')
    c = conn.cursor()

    # Vérifier si le giveaway est terminé
    c.execute('SELECT ended, message_id, prize FROM giveaways WHERE id = ?', (giveaway_id,))
    giveaway = c.fetchone()

    if not giveaway:
        await ctx.send("Giveaway non trouvé.")
        conn.close()
        return

    if giveaway[0] == 0:
        await ctx.send("Le giveaway est encore en cours. Vous ne pouvez pas le reroll.")
        conn.close()
        return

    # Obtenir les participants
    c.execute('SELECT user_id FROM participants WHERE giveaway_id = ?', (giveaway_id,))
    participants = [row[0] for row in c.fetchall()]

    if not participants:
        await ctx.send("Aucun participant à reroll.")
        conn.close()
        return

    # Sélectionner un nouveau gagnant
    new_winner_id = random.choice(participants)
    new_winner = bot.get_user(new_winner_id)

    # Envoyer le message de nouveau gagnant
    embed = discord.Embed(title="🎉 Nouveau Gagnant du Giveaway !",
                          description=f"Le nouveau gagnant est {new_winner.mention} pour **{giveaway[2]}**!",
                          color=discord.Color.gold())
    channel = bot.get_channel(giveaway[1])
    if channel:
        try:
            message = await channel.fetch_message(giveaway[0])
            await message.edit(embed=embed)
        except discord.NotFound:
            pass

    # Envoyer le message de notification
    await ctx.send(embed=embed)

    conn.close()


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    forbidden_words = ['Fils de pute', 'FDP', 'fdp', 'fils de pute', 'filsdepute']
    if any(word in message.content.lower() for word in forbidden_words):
        await message.delete()
        embed = discord.Embed(
            title=f"{message.author.mention}, votre message a été supprimé car il contenait un mot interdit.",
            color=discord.Color.blue())
        await message.channel.send(embed=embed)

    await bot.process_commands(message)


@bot.command(name='tempchannel')
@commands.has_permissions(administrator=True)
async def tempchannel(ctx, name, duration: int):
    guild = ctx.guild
    channel = await guild.create_text_channel(name)

    await ctx.send(f"Salon `{name}` créé pour {duration} minutes.")

    await asyncio.sleep(duration * 60)
    await channel.delete()
    await ctx.send(f"Le salon `{name}` a été supprimé.")


@bot.command(name='stats')
async def stats(ctx):
    guild = ctx.guild
    member_count = guild.member_count
    total_messages = 0

    # Compter les messages dans chaque canal texte
    for channel in guild.text_channels:
        try:
            async for _ in channel.history(limit=100):
                total_messages += 1
        except Exception as e:
            print(f"Erreur lors de l'accès au canal {channel.name}: {e}")

    embed = discord.Embed(title=f"Le serveur a {member_count} membres et a reçu un total de {total_messages} messages.",
                          color=discord.Color.blue())
    await ctx.send(embed=embed)


@bot.command(name='wiki')
async def wiki(ctx, *, query):
    try:
        summary = wikipedia.summary(query, sentences=1)
        await ctx.send(summary)
    except wikipedia.exceptions.DisambiguationError as e:
        await ctx.send(f"Le terme '{query}' est ambigu. Voici quelques options : {', '.join(e.options)}")
    except wikipedia.exceptions.PageError:
        await ctx.send(f"Aucune page trouvée pour '{query}'.")


@bot.command(name='role')
@commands.has_permissions(manage_roles=True)
async def role(ctx, member: discord.Member, role: discord.Role):
    if role in member.roles:
        # Si le membre a déjà ce rôle, le retirer
        await member.remove_roles(role)
        embed = discord.Embed(title="Rôle retiré", description=f"Le rôle {role.name} a été retiré de {member.mention}.",
                              color=discord.Color.red())
    else:
        # Sinon, ajouter le rôle
        await member.add_roles(role)
        embed = discord.Embed(title="Rôle ajouté", description=f"Le rôle {role.name} a été ajouté à {member.mention}.",
                              color=discord.Color.green())

    await ctx.send(embed=embed)


@bot.command(name='play')
async def play(ctx, url: str):
    if not ctx.author.voice:
        return await ctx.send("Vous devez être dans un canal vocal pour utiliser cette commande.")

    channel = ctx.author.voice.channel

    if ctx.voice_client is None:
        await channel.connect()

    player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)

    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = deque()

    queues[ctx.guild.id].append(player)

    if not ctx.voice_client.is_playing():
        ctx.voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(on_song_end(ctx), bot.loop))

        # Création de l'embed avec les attributs disponibles dans YTDLSource
        embed = discord.Embed(title="Lecture de musique 🎵", color=discord.Color.blue())
        embed.add_field(name="Titre", value=player.title or 'Inconnu', inline=False)
        embed.add_field(name="Durée",
                        value=f"{int(player.duration // 60)}:{int(player.duration % 60):02d}" if player.duration else "Inconnu",
                        inline=True)
        embed.add_field(name="Uploader", value=player.uploader or 'Inconnu', inline=True)
        embed.add_field(name="Lien", value=f"[Cliquez ici]({url})", inline=False)
        embed.set_thumbnail(url=player.thumbnail or 'https://via.placeholder.com/150')

        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title=f'{player.title} ajouté à la file d\'attente.', color=discord.Color.green())
        await ctx.send(embed=embed)


@bot.command(name='pause')
async def pause(ctx):
    if ctx.voice_client is None:
        embed = discord.Embed(title="Erreur", description="Je ne suis pas connecté à un canal vocal.",
                              color=discord.Color.red())
        return await ctx.send(embed=embed)

    if ctx.voice_client.is_paused():
        embed = discord.Embed(title="Information", description="La lecture est déjà en pause.",
                              color=discord.Color.orange())
        return await ctx.send(embed=embed)

    ctx.voice_client.pause()
    embed = discord.Embed(title="Succès", description="Lecture mise en pause.", color=discord.Color.green())
    await ctx.send(embed=embed)


@bot.command(name='resume')
async def resume(ctx):
    if ctx.voice_client is None:
        embed = discord.Embed(title="Erreur", description="Je ne suis pas connecté à un canal vocal.",
                              color=discord.Color.red())
        return await ctx.send(embed=embed)

    if not ctx.voice_client.is_paused():
        embed = discord.Embed(title="Information", description="La lecture n'est pas en pause.",
                              color=discord.Color.orange())
        return await ctx.send(embed=embed)

    ctx.voice_client.resume()
    embed = discord.Embed(title="Succès", description="Lecture reprise.", color=discord.Color.green())
    await ctx.send(embed=embed)


@bot.command(name='leave')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    else:
        embed = discord.Embed(title="Je ne suis pas dans un canal vocal.", color=discord.Color.blue())
        await ctx.send(embed=embed)


@bot.command(name='skip')
async def skip(ctx):
    if ctx.voice_client is None or not ctx.voice_client.is_playing():
        return await ctx.send("Je ne joue aucune musique en ce moment.")

    if ctx.guild.id not in queues or not queues[ctx.guild.id]:
        return await ctx.send("La file d'attente est vide. Aucun morceau à passer.")

    ctx.voice_client.stop()  # Arrête la chanson en cours

    # Gérer la chanson suivante
    if queues[ctx.guild.id]:
        next_song = queues[ctx.guild.id].popleft()  # Retirer la chanson actuelle de la file d'attente
        ctx.voice_client.play(next_song, after=lambda e: asyncio.run_coroutine_threadsafe(on_song_end(ctx), bot.loop))

        embed = discord.Embed(title=f'Passé à la chanson suivante: {next_song.title}', color=discord.Color.green())
        await ctx.send(embed=embed)

    else:
        await ctx.send("La file d'attente est maintenant vide.")


@bot.command(name='queue')
async def queue(ctx):
    if ctx.guild.id not in queues or not queues[ctx.guild.id]:
        embed = discord.Embed(
            title="File d'attente vide",
            description="Il n'y a actuellement aucun morceau dans la file d'attente.",
            color=discord.Color.red()
        )
        return await ctx.send(embed=embed)

    queue_list = queues[ctx.guild.id]

    # Diviser la file d'attente en plusieurs messages si nécessaire
    chunk_size = 10  # Nombre de morceaux par embed
    max_field_length = 1024  # Longueur maximale pour les champs d'embed
    chunks = [list(queue_list)[i:i + chunk_size] for i in range(0, len(queue_list), chunk_size)]

    for index, chunk in enumerate(chunks):
        queue_embed = discord.Embed(
            title=f"File d'attente (Partie {index + 1}/{len(chunks)})",
            color=discord.Color.blue()
        )

        # Préparer la description des morceaux
        description = ""
        for idx, item in enumerate(chunk, start=(index * chunk_size) + 1):
            item_str = f"{idx}. {item.title} - [URL]({item.url})\n"
            if len(description) + len(item_str) > max_field_length:
                break
            description += item_str

        queue_embed.description = description

        if ctx.voice_client.is_playing() and index == 0:
            current_song = ctx.voice_client.source
            queue_embed.add_field(
                name="En cours de lecture",
                value=f"{current_song.title}\n[URL]({current_song.url})",
                inline=False
            )

        await ctx.send(embed=queue_embed)


@bot.command(name='timeout')
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, duration: int, *, reason=None):
    try:
        # Convertir la durée en minutes en un délai en secondes
        timeout_duration = duration * 60
        await member.timeout(duration=discord.utils.utcnow() + discord.timedelta(seconds=timeout_duration),
                             reason=reason)
        embed = discord.Embed(title=f'{member.mention} a été temporairement exclu pour {duration} minutes.',
                              color=discord.Color.blue())
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("Je n'ai pas les permissions nécessaires pour exclure temporairement cet utilisateur.")

    except discord.HTTPException:
        await ctx.send("Une erreur est survenue lors de la tentative d'exclusion temporaire de l'utilisateur.")


@bot.command(name='nick')
@commands.has_permissions(manage_nicknames=True)
async def nick(ctx, member: discord.Member, *, new_nick):
    try:
        old_nick = member.nick
        await member.edit(nick=new_nick)
        embed = discord.Embed(title=f'Le pseudonyme de {member.mention} a été changé de "{old_nick}" à "{new_nick}".',
                              color=discord.Color.blue())
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("Je n'ai pas les permissions nécessaires pour changer le pseudonyme de cet utilisateur.")
    except discord.HTTPException:
        await ctx.send("Une erreur est survenue lors de la tentative de changement de pseudonyme.")


@bot.command(name='mb')
async def mb(ctx):
    embed = discord.Embed(title=f'Il y a {ctx.guild.member_count} membres sur ce serveur.', color=discord.Color.blue())
    await ctx.send(embed=embed)


@bot.command(name='mute')
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member):
    muted_role = discord.utils.get(ctx.guild.roles, name='Muted')
    if not muted_role:
        muted_role = await ctx.guild.create_role(name='Muted')
        for channel in ctx.guild.channels:
            await channel.set_permissions(muted_role, speak=False, send_messages=False)
    await member.add_roles(muted_role)
    await ctx.send(f'{member} a été rendu muet.')


@bot.command(name='unmute')
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    muted_role = discord.utils.get(ctx.guild.roles, name='Muted')
    if muted_role in member.roles:
        await member.remove_roles(muted_role)
        await ctx.send(f'{member} peut à nouveau parler.')


@bot.command(name='ping')
async def ping(ctx):
    embed = discord.Embed(title=f'Pong! Latence: {round(bot.latency * 1000)}ms', color=discord.Color.blue())
    await ctx.send(embed=embed)


@bot.command(name='servinfo')
async def servinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f'Informations sur {guild.name}', color=discord.Color.blue())
    embed.add_field(name='ID', value=guild.id)
    embed.add_field(name='Propriétaire', value=str(guild.owner))
    embed.add_field(name='Membres', value=guild.member_count)
    embed.add_field(name='Créé le', value=guild.created_at.strftime("%d %B %Y à %H:%M:%S"))
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await ctx.send(embed=embed)


# ID du canal de suggestions (remplace par l'ID du canal où tu veux recevoir les suggestions)
SUGGESTION_CHANNEL_ID = 1269741313994133525


# Commande !suggest
@bot.command(name='suggest')
async def suggest(ctx, *, suggestion: str):
    # Vérifie si l'utilisateur a fourni une suggestion
    if not suggestion:
        await ctx.send("Vous devez fournir une suggestion.")
        return

    # Obtient le canal de suggestions
    channel = bot.get_channel(SUGGESTION_CHANNEL_ID)

    if channel is None:
        await ctx.send("Le canal de suggestions n'a pas été trouvé.")
        return

    # Crée un message de suggestion formaté
    suggestion_message = (f"**Suggestion de {ctx.author}**\n"
                          f"```{suggestion}```")

    # Envoie la suggestion dans le canal de suggestions
    await channel.send(suggestion_message)

    # Confirme la réception de la suggestion à l'utilisateur
    await ctx.send("Votre suggestion a été envoyée avec succès.")


# Commande !poll
@bot.command(name='poll')
async def poll(ctx, question: str, *options: str):
    if len(options) < 2:
        await ctx.send("Vous devez fournir au moins deux options.")
        return

    # Limite le nombre d'options à 10 (Discord permet un maximum de 10 réactions)
    options = options[:10]

    # Crée une chaîne de caractères pour les options avec des émojis
    options_text = "\n".join([f"{chr(0x0031 + i) + chr(0x20E3)} {option}" for i, option in enumerate(options)])

    # Crée un embed pour le sondage
    embed = discord.Embed(title="Sondage", description=f"{question}\n\n{options_text}", color=discord.Color.green())
    poll_message = await ctx.send(embed=embed)

    # Ajouter des réactions pour les options (1️⃣, 2️⃣, 3️⃣, etc.)
    for i in range(len(options)):
        await poll_message.add_reaction(chr(0x0031 + i) + chr(0x20E3))


token = 'MTI1NzY2ODQwMDE2Mzg1MjI5OQ.GGjt0h.HX1t5q2QYUmXIiH0ouwdM6JO_mlwu-d0nt-pas'

bot.run(token)

# Fonction pour lancer le serveur web Flask
def run_web():
    app.run(debug=True, use_reloader=False)

# Lancer le bot et le serveur web dans des threads séparés
if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    threading.Thread(target=run_web).start()