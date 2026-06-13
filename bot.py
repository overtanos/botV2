import discord
from discord.ext import commands
from discord import app_commands
import traceback
import asyncio
import yt_dlp
import os

# ─── Keep-alive pour Render (évite le sleep) ─────────────────────────────────
from flask import Flask
from threading import Thread

app_flask = Flask('')

@app_flask.route('/')
def home():
    return "✅ Bot en ligne !"

def run_flask():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

Thread(target=run_flask, daemon=True).start()
# ─────────────────────────────────────────────────────────────────────────────

TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("❌ La variable d'environnement DISCORD_TOKEN est manquante !")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

queues = {}
panel_messages = {}
stopped = {}


def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]


# ─── Vue avec boutons de contrôle (panel Rythm-like) ───────────────────────

class MusicControlView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def get_vc(self):
        guild = bot.get_guild(self.guild_id)
        return guild.voice_client if guild else None

    @discord.ui.button(emoji="⏹️", label="Stop", style=discord.ButtonStyle.danger, row=0)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.get_vc()
        if vc:
            queues[self.guild_id] = []
            stopped[self.guild_id] = True
            vc.stop()
            embed = build_embed(title="Rien en cours", description="", is_playing=False)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(emoji="⏸️", label="Pause", style=discord.ButtonStyle.secondary, row=0)
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.get_vc()
        if vc and vc.is_playing():
            vc.pause()
            button.emoji = "▶️"
            button.label = "Reprendre"
            await interaction.response.edit_message(view=self)
        elif vc and vc.is_paused():
            vc.resume()
            button.emoji = "⏸️"
            button.label = "Pause"
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(emoji="⏭️", label="Skip", style=discord.ButtonStyle.secondary, row=0)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.get_vc()
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.defer()
        else:
            await interaction.response.defer()

    @discord.ui.button(emoji="📋", label="File d'attente", style=discord.ButtonStyle.secondary, row=1)
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = get_queue(self.guild_id)
        if not queue:
            await interaction.response.send_message("📋 La file est vide.", ephemeral=True)
        else:
            liste = "\n".join([f"`{i+1}.` **{title}**" for i, (_, title, _t) in enumerate(queue)])
            await interaction.response.send_message(f"📋 **File d'attente :**\n{liste}", ephemeral=True)

    @discord.ui.button(emoji="🔊", label="Déconnecter", style=discord.ButtonStyle.secondary, row=1)
    async def disconnect_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.get_vc()
        if vc:
            queues[self.guild_id] = []
            await vc.disconnect()
            embed = build_embed(title="Rien en cours", description="", is_playing=False)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()


# ─── Construction de l'embed du panel ──────────────────────────────────────

def build_embed(title: str, description: str, is_playing: bool, thumbnail_url: str = None):
    if is_playing:
        embed = discord.Embed(
            title="🎵 En cours de lecture",
            description=f"**{title}**",
            color=0x5865F2
        )
        embed.add_field(name="État", value="▶️ Lecture en cours", inline=True)
    else:
        embed = discord.Embed(
            title="🎵 Lecteur musical",
            description="*Rien n'est en cours de lecture*",
            color=0x2b2d31
        )
        embed.add_field(name="État", value="⏹️ Inactif", inline=True)

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    embed.set_footer(text="Utilise /play pour lancer une musique")
    return embed


async def send_or_update_panel(channel, guild_id, title="", is_playing=False, thumbnail_url=None):
    embed = build_embed(title=title, description="", is_playing=is_playing, thumbnail_url=thumbnail_url)
    view = MusicControlView(guild_id)

    existing_msg = panel_messages.get(guild_id)
    if existing_msg:
        try:
            await existing_msg.edit(embed=embed, view=view)
            return existing_msg
        except (discord.NotFound, discord.HTTPException) as e:
            print(f"⚠️ Edit panel échoué : {e}")
            panel_messages.pop(guild_id, None)

    try:
        msg = await channel.send(embed=embed, view=view)
        panel_messages[guild_id] = msg
        return msg
    except Exception as e:
        print(f"❌ Envoi panel échoué : {e}")
        traceback.print_exc()


# ─── Lecture suivante ────────────────────────────────────────────────────────

async def play_next(channel, guild_id, vc):
    if stopped.get(guild_id):
        stopped[guild_id] = False
        return

    queue = get_queue(guild_id)

    if not queue:
        await send_or_update_panel(channel, guild_id, is_playing=False)
        return

    url, title, thumbnail = queue.pop(0)
    source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
    vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(
        play_next(channel, guild_id, vc), bot.loop
    ))

    await send_or_update_panel(channel, guild_id, title=title, is_playing=True, thumbnail_url=thumbnail)


# ─── Events ─────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} slash commands synchronisées")
    except Exception as e:
        print(f"❌ Erreur sync : {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)


# ─── Commandes slash ─────────────────────────────────────────────────────────

@bot.tree.command(name="ping", description="Tester la latence du bot")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong ! Latence : {round(bot.latency * 1000)}ms", ephemeral=True)

@bot.tree.command(name="join", description="Rejoindre ton salon vocal")
async def join(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.voice is None:
            await interaction.followup.send("❌ Tu dois être dans un salon vocal d'abord.", ephemeral=True)
            return
        channel = interaction.user.voice.channel
        vc = interaction.guild.voice_client
        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.connect:
            await interaction.followup.send("❌ Je n'ai pas la permission de rejoindre ce salon.", ephemeral=True)
            return
        if vc is None:
            await channel.connect()
        elif vc.channel != channel:
            await vc.move_to(channel)
        else:
            await interaction.followup.send(f"✅ Je suis déjà dans **{channel.name}**.", ephemeral=True)
            return
        await interaction.followup.send(f"🔊 Connecté à **{channel.name}**", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Accès refusé — vérifie les permissions du bot.", ephemeral=True)
    except Exception:
        traceback.print_exc()
        await interaction.followup.send("❌ Erreur inattendue.", ephemeral=True)

@bot.tree.command(name="play", description="Jouer une musique depuis YouTube")
@app_commands.describe(recherche="Nom de la musique ou lien YouTube")
async def play(interaction: discord.Interaction, recherche: str):
    await interaction.response.defer(ephemeral=True)

    if interaction.user.voice is None:
        await interaction.followup.send("❌ Tu dois être dans un salon vocal.", ephemeral=True)
        return

    channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    if vc is None:
        vc = await channel.connect()
    elif vc.channel != channel:
        await vc.move_to(channel)

    try:
        def fetch_info():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(recherche, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info

        info = await asyncio.to_thread(fetch_info)
        url = info['url']
        title = info.get('title', 'Titre inconnu')
        thumbnail = info.get('thumbnail', None)

        queue = get_queue(interaction.guild_id)
        text_channel = interaction.channel

        if vc.is_playing() or vc.is_paused():
            queue.append((url, title, thumbnail))
            await interaction.followup.send(f"📋 Ajouté à la file : **{title}**", ephemeral=True)
        else:
            queue.append((url, title, thumbnail))
            await interaction.followup.send(f"▶️ Lecture de **{title}**", ephemeral=True)
            await play_next(text_channel, interaction.guild_id, vc)

    except Exception:
        traceback.print_exc()
        await interaction.followup.send("❌ Impossible de lire cette musique.", ephemeral=True)

@bot.tree.command(name="skip", description="Passer à la musique suivante")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏭️ Musique passée !", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Aucune musique en cours.", ephemeral=True)

@bot.tree.command(name="stop", description="Arrêter la musique et vider la file")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        queues[interaction.guild_id] = []
        stopped[interaction.guild_id] = True
        vc.stop()
        await interaction.response.send_message("⏹️ Musique arrêtée et file vidée.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Je ne suis pas dans un salon vocal.", ephemeral=True)

@bot.tree.command(name="queue", description="Voir la file d'attente")
async def queue_cmd(interaction: discord.Interaction):
    queue = get_queue(interaction.guild_id)
    if not queue:
        await interaction.response.send_message("📋 La file est vide.", ephemeral=True)
    else:
        liste = "\n".join([f"`{i+1}.` **{title}**" for i, (_, title, _t) in enumerate(queue)])
        await interaction.response.send_message(f"📋 **File d'attente :**\n{liste}", ephemeral=True)

@bot.tree.command(name="pause", description="Mettre en pause")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ Mis en pause.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Aucune musique en cours.", ephemeral=True)

@bot.tree.command(name="resume", description="Reprendre la lecture")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ Reprise de la lecture.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ La musique n'est pas en pause.", ephemeral=True)

@bot.tree.command(name="disconnect", description="Déconnecter le bot du salon vocal")
async def disconnect(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    vc = interaction.guild.voice_client
    if vc:
        queues[interaction.guild_id] = []
        await vc.disconnect()
        await interaction.followup.send("👋 Déconnecté", ephemeral=True)
    else:
        await interaction.followup.send("❌ Je ne suis pas dans un salon vocal.", ephemeral=True)

@bot.tree.command(name="kick", description="Expulser un membre")
@app_commands.describe(member="Le membre à expulser", reason="La raison")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison donnée"):
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 **{member.name}** a été expulsé. Raison : {reason}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission d'expulser ce membre.")
    except Exception:
        traceback.print_exc()
        await interaction.response.send_message("❌ Erreur inattendue.")

@bot.tree.command(name="ban", description="Bannir un membre")
@app_commands.describe(member="Le membre à bannir", reason="La raison")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison donnée"):
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 **{member.name}** a été banni. Raison : {reason}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission de bannir ce membre.")
    except Exception:
        traceback.print_exc()
        await interaction.response.send_message("❌ Erreur inattendue.")

bot.run(TOKEN)
