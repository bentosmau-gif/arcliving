import discord
import os
import asyncio
import yt_dlp
import spotipy
import patreon
import google.generativeai as genai
from spotipy.oauth2 import SpotifyClientCredentials
from collections import deque

# Cargar el token desde los Secrets de Replit
TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
SPOTIFY_ID = os.environ.get('SPOTIFY_CLIENT_ID')
SPOTIFY_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
PATREON_ACCESS_TOKEN = os.environ.get('PATREON_ACCESS_TOKEN')

# Configuración de Spotify
sp = None
if SPOTIFY_ID and SPOTIFY_SECRET:
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIFY_ID, client_secret=SPOTIFY_SECRET))
    except Exception as e:
        print(f"Error al configurar Spotify: {e}")

# Configuración de Patreon
patreon_client = None
if PATREON_ACCESS_TOKEN:
    try:
        patreon_client = patreon.API(PATREON_ACCESS_TOKEN)
    except Exception as e:
        print(f"Error al configurar Patreon: {e}")

# Configuración de Gemini
GEMINI_KEY = os.environ.get('GOOGLE_API_KEY')
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    # Cambiado de gemini-pro a gemini-1.5-flash para mejor compatibilidad y velocidad
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    print("Error: No se encontró GOOGLE_API_KEY para Gemini.")

# Configuración de yt-dlp
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': 'True',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extract_flat': 'in_playlist', # Para manejar links de SoundCloud/Patreon mejor
}

# Opciones de FFMPEG con optimizaciones para streaming
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.5"'
}

class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prefixes = ['/', '#']
        self.queues = {} # {guild_id: deque()}
        self.radio_map = {
            "1️⃣": "https://ice1.somafm.com/groovesalad-128-mp3",
            "2️⃣": "http://64.71.79.181:5234/stream",
            "3️⃣": "http://ice.somafm.com/spacestation",
            "4️⃣": "http://chill.friskyradio.com/friskychill_mp3_high",
            "5️⃣": "http://ice1.somafm.com/secretagent-128-mp3",
            "📻": "attached_assets/https.iceliving-radio_1772378342036.mp3"
        }
        self.radio_messages = {} # {message_id: guild_id}

    async def on_ready(self):
        print(f'Logueado como {self.user} (ID: {self.user.id})')
        print(f'📍 Ejecutándose en: {os.uname().nodename if hasattr(os, "uname") else "Windows/Other"}')
        print('------')

    def play_next(self, guild_id, message_channel):
        if guild_id in self.queues and self.queues[guild_id]:
            next_song = self.queues[guild_id].popleft()
            vc = next_song['vc']
            url = next_song['url']
            title = next_song['title']
            
            try:
                # Usar FFmpegOpusAudio directamente con el URL, saltándose el probe
                source = discord.FFmpegOpusAudio(url, **FFMPEG_OPTIONS)
                vc.play(source, after=lambda e: self.play_next(guild_id, message_channel))
                # Usar el loop del cliente para enviar el mensaje
                self.loop.create_task(message_channel.send(f"Reproduciendo ahora: **{title}**"))
            except Exception as e:
                print(f"Error en play_next: {e}")
        else:
            # Si no hay más canciones, podríamos desconectar después de un tiempo
            pass

    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        message_id = reaction.message.id
        if message_id in self.radio_messages:
            guild_id = self.radio_messages[message_id]
            guild = self.get_guild(guild_id)
            if not guild: return
            
            emoji = str(reaction.emoji)
            if emoji in self.radio_map:
                url = self.radio_map[emoji]
                
                # Buscar al usuario en los canales de voz del gremio
                member = guild.get_member(user.id)
                if not member or not member.voice:
                    await reaction.message.channel.send(f"{user.mention}, debes estar en un canal de voz.")
                    return

                # Intentar conectar o recuperar cliente de voz existente
                try:
                    if guild.voice_client is None:
                        # Usar wait_for para evitar bloqueos infinitos si hay problemas de red
                        # Aumentar timeout y forzar reconexión con opciones específicas
                        # Forzamos self_deaf para ahorrar ancho de banda y mejorar estabilidad en Replit
                        vc = await asyncio.wait_for(voice_channel.connect(timeout=60.0, reconnect=True, self_deaf=True), timeout=65.0)
                    else:
                        vc = guild.voice_client
                        if not isinstance(vc, discord.VoiceClient):
                            return
                        if vc.channel != voice_channel:
                            await vc.move_to(voice_channel)
                    
                    # Esperar estabilidad (aumentado para Replit)
                    await asyncio.sleep(5)
                    
                    if vc and vc.is_playing():
                        vc.stop()
                    
                    if guild_id in self.queues:
                        self.queues[guild_id].clear()

                    source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
                    if vc:
                        vc.play(source)
                        await reaction.message.channel.send(f"🎶【✦】Conectándome con la radio online: {url}")
                except Exception as e:
                    try:
                        source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
                        if vc:
                            vc.play(discord.PCMVolumeTransformer(source))
                            await reaction.message.channel.send(f"🎶【✦】Conectándome con la radio online (respaldo): {url}")
                    except Exception as e2:
                        await reaction.message.channel.send(f"Error al conectar a la radio: {e2}")

    async def on_message(self, message):
        if message.author.id == self.user.id:
            return

        msg = message.content
        active_prefix = None
        for p in self.prefixes:
            if msg.startswith(p):
                active_prefix = p
                break
        
        if not active_prefix:
            return

        command_body = msg[len(active_prefix):].strip()
        parts = command_body.split(' ', 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        guild_id = message.guild.id

        if command == "play" or command == "ytplay":
            # Verificar si el comando es premium y el usuario tiene acceso
            if command == "ytplay" and str(message.author) != "gamermauri_900":
                # En el futuro, aquí se podría añadir la lógica real de Patreon
                # Por ahora, solo permitimos al dueño y bloqueamos al resto con el mensaje solicitado
                await message.channel.send("Este comando es premium. Ve a https://patreon.com/ShilterTikTok?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink y dona para usar este comando.")
                return

            if not args:
                await message.channel.send(f"Uso: {active_prefix}{command} [canción/url]")
                return
            # ... rest of play logic remains the same ...
            
            if not message.author.voice:
                await message.channel.send("Debes estar en un canal de voz para que me una.")
                return

            voice_channel = message.author.voice.channel
            
            # Intentar conectar o recuperar cliente de voz existente
            try:
                if message.guild.voice_client is None:
                    # Usar wait_for para evitar bloqueos infinitos si hay problemas de red
                    # Aumentar timeout y forzar reconexión con opciones específicas
                    # Forzamos self_deaf para mejorar estabilidad en Replit
                    vc = await asyncio.wait_for(voice_channel.connect(timeout=60.0, reconnect=True, self_deaf=True), timeout=65.0)
                else:
                    vc = message.guild.voice_client
                    if vc.channel != voice_channel:
                        await vc.move_to(voice_channel)
            
                # Esperar un momento para asegurar que el estado de voz se estabilice
                await asyncio.sleep(5)
            
                # Forzar que el bot esté en el canal correcto y con estado limpio
                if not vc.is_connected():
                    await vc.connect(timeout=60.0, reconnect=True, self_deaf=True)
                    await asyncio.sleep(2)

                # Pequeño truco para Replit: enviar una trama de silencio para despertar la conexión
                if vc.is_connected():
                    try:
                        # Silencio corto para "despertar" el canal de voz de Discord
                        vc.play(discord.FFmpegPCMAudio("/dev/zero", before_options="-f s16le -ar 48000 -ac 2 -t 1"))
                        await asyncio.sleep(1)
                    except:
                        pass
            except asyncio.TimeoutError:
                await message.channel.send("No pude conectarme al canal de voz. Intenta cambiar la región a 'US East' o 'US Central', Brazil suele dar problemas con Replit.")
                return
            except Exception as e:
                await message.channel.send(f"Error de conexión: {str(e)}")
                return

            async with message.channel.typing():
                # Manejo de Spotify
                if 'spotify.com' in args and sp:
                    try:
                        if 'track' in args:
                            track_info = sp.track(args)
                            search_query = f"{track_info['name']} {track_info['artists'][0]['name']}"
                        else:
                            await message.channel.send("Por ahora solo soporto canciones individuales de Spotify.")
                            return
                        args = search_query # Cambiar el link por búsqueda para yt-dlp
                    except Exception as e:
                        print(f"Error de Spotify: {e}")

                with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                    try:
                        info = ydl.extract_info(args, download=False)
                        if 'entries' in info:
                            info = info['entries'][0]
                        url = info['url']
                        title = info.get('title', 'Canción desconocida')
                        
                        # Análisis de Licencias y Copyright
                        license = info.get('license', '').lower()
                        description = info.get('description', '').lower()
                        uploader = info.get('uploader', '').lower()
                        
                        # Lista blanca de autores (SoundCloud/YouTube) que tienen permiso explícito
                        # mauri-minuano es el usuario que dio permiso en el chat
                        author_whitelist = ['mauri-minuano', 'mauri minuano', 'gamermauri_900']
                        is_whitelisted = any(author in uploader or author in description for author in author_whitelist)

                        is_public_domain = any(x in license or x in description for x in ['public domain', 'dominio público', 'no rights reserved'])
                        is_creative_commons = 'creative commons' in license or 'cc' in license or 'creativecommons' in description
                        is_royalty_free = 'royalty free' in license or 'royalty-free' in description
                        
                        # 1. Denegar si hay Copyright explícito y no es CC/RF/PD o Autor Autorizado
                        if not (is_creative_commons or is_royalty_free or is_public_domain or is_whitelisted):
                            await message.channel.send("❌ **Error de Licencia**: Esta canción tiene Copyright. No puedo reproducirla para proteger los derechos de autor.")
                            return

                        # 2. Autor Autorizado (Whitelist)
                        if is_whitelisted and not (is_creative_commons or is_royalty_free or is_public_domain):
                            await message.channel.send(f"✅ **Autorización Especial**: Reproduciendo contenido de **{info.get('uploader', 'Autor Verificado')}** con permiso explícito.")

                        # 2. Dominio Público: Opciones de créditos
                        if is_public_domain:
                            class PDView(discord.ui.View):
                                def __init__(self, song_data, guild_id, client):
                                    super().__init__(timeout=30)
                                    self.song_data = song_data
                                    self.guild_id = guild_id
                                    self.client = client

                                @discord.ui.button(label="Dar Créditos", style=discord.ButtonStyle.success)
                                async def credit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                                    await interaction.response.send_message(f"📢 Créditos otorgados a la obra original.")
                                    await self.play_now(interaction)

                                @discord.ui.button(label="No dar Créditos", style=discord.ButtonStyle.secondary)
                                async def no_credit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                                    await interaction.response.send_message(f"Reproduciendo sin créditos adicionales.")
                                    await self.play_now(interaction)

                                async def play_now(self, interaction):
                                    vc = self.song_data['vc']
                                    if vc.is_playing() or vc.is_paused():
                                        self.client.queues[self.guild_id].append(self.song_data)
                                    else:
                                        source = await discord.FFmpegOpusAudio.from_probe(self.song_data['url'], **FFMPEG_OPTIONS)
                                        vc.play(source, after=lambda e: self.client.play_next(self.guild_id, interaction.channel))
                                    self.stop()

                            view = PDView({'url': url, 'title': title, 'vc': vc}, guild_id, self)
                            await message.channel.send(f"📜 **Dominio Público**: '{title}' es una obra antigua. ¿Deseas dar créditos antes de reproducir?", view=view)
                            return

                        # 3. Creative Commons
                        if is_creative_commons:
                            credits_msg = "✅ **Creative Commons detectado**: "
                            if 'by-nc' in license or 'by-nc' in description:
                                await message.channel.send("⚠️ **Restricción**: Licencia CC BY-NC detectada. **No puedes vender ni comercializar esta música**.")
                            if 'by' in license or 'cc by' in description:
                                credits_msg += f"Créditos obligatorios a: **{info.get('uploader', 'el autor original')}**."
                            await message.channel.send(credits_msg)

                        # 4. Royalty Free
                        if is_royalty_free:
                            if 'paid' in description or 'comprar' in description:
                                await message.channel.send("❌ **Royalty Free de pago**: Detecto que esta canción requiere una licencia comprada. No puedo reproducirla.")
                                return
                            await message.channel.send(f"🎵 **Royalty Free (Gratis)**: Atribución a **{info.get('uploader', 'el autor')}**.")

                        song_data = {'url': url, 'title': title, 'vc': vc}
                        
                        if guild_id not in self.queues:
                            self.queues[guild_id] = deque()
                        
                        if vc.is_playing() or vc.is_paused():
                            self.queues[guild_id].append(song_data)
                            await message.channel.send(f"Añadido a la cola: **{title}**")
                        else:
                            try:
                                # Usar FFmpegOpusAudio directamente sin probe para evitar el error de ffprobe
                                source = discord.FFmpegOpusAudio(url, **FFMPEG_OPTIONS)
                                vc.play(source, after=lambda e: self.play_next(guild_id, message.channel))
                                await message.channel.send(f"Reproduciendo: **{title}**")
                            except Exception as e:
                                print(f"Error al reproducir: {e}")
                                await message.channel.send("Hubo un problema al iniciar la reproducción.")
                    except Exception as e:
                        await message.channel.send(f"Error al procesar el audio: {str(e)}")

        elif command == "scplay":
            if not args:
                await message.channel.send(f"Uso: {active_prefix}scplay [canción/url de SoundCloud]")
                return
            # Forzar búsqueda en SoundCloud si no es URL
            if not args.startswith("http"):
                args = f"scsearch:{args}"
            # Re-utilizar la lógica de play llamando a la misma sección o duplicando mínimamente
            # Por simplicidad en Fast Mode, lo manejaremos como 'play' pero con el prefijo scsearch
            msg_content_original = message.content
            message.content = f"{active_prefix}play {args}"
            await self.on_message(message)
            return

        elif command == "radio":
            menu_radio = (
                "Selecciona una radio con emoji:\n"
                "1️⃣: Groove Salad (Chill / Ambient)\n"
                "2️⃣: Radio 35 Hip Hop (CC)\n"
                "3️⃣: Space Station (SomaFM)\n"
                "4️⃣: Frisky Chill (Electrónica)\n"
                "5️⃣: Secret Agent (Lounge / Downtempo)\n"
                "📻: **IceLiving Radio (Original)**\n"
                "「❖」𝖲𝖾𝗅𝖾𝖼𝖼𝗂𝗈𝗇𝖺 𝖾𝗅 𝖾𝗆𝗈𝗃𝗂 𝖼𝗈𝗋𝗋𝖾𝗌𝗉𝗈𝗇𝖽𝗂𝖾𝗇𝗍𝖾."
            )
            radio_msg = await message.channel.send(menu_radio)
            self.radio_messages[radio_msg.id] = guild_id
            for emoji in self.radio_map.keys():
                await radio_msg.add_reaction(emoji)

        elif command == "pause":
            if message.guild.voice_client and message.guild.voice_client.is_playing():
                message.guild.voice_client.pause()
                await message.channel.send("Música pausada")
            else:
                await message.channel.send("No hay nada reproduciéndose")

        elif command == "resume":
            if message.guild.voice_client and message.guild.voice_client.is_paused():
                message.guild.voice_client.resume()
                await message.channel.send("Música reanudada")
            else:
                await message.channel.send("La música no está pausada")

        elif command == "skip":
            if message.guild.voice_client and (message.guild.voice_client.is_playing() or message.guild.voice_client.is_paused()):
                message.guild.voice_client.stop()
                await message.channel.send("Canción saltada")
            else:
                await message.channel.send("No hay nada que saltar")

        elif command == "queue" or command == "cola":
            if guild_id in self.queues and self.queues[guild_id]:
                queue_list = "\n".join([f"{i+1}. {song['title']}" for i, song in enumerate(list(self.queues[guild_id])[:10])])
                await message.channel.send(f"**Cola actual (primeras 10):**\n{queue_list}")
            else:
                await message.channel.send("La cola está vacía")

        elif command == "stop":
            if message.guild.voice_client:
                if guild_id in self.queues:
                    self.queues[guild_id].clear()
                await message.guild.voice_client.disconnect()
                await message.channel.send("Música detenida y cola limpiada")
            else:
                await message.channel.send("No estoy en ningún canal de voz")

        elif command == "checkpatron":
            if not patreon_client:
                await message.channel.send("El sistema de Patreon no está configurado.")
                return
            
            async with message.channel.typing():
                try:
                    # Usar la API v2 de Patreon para obtener la identidad
                    # El SDK de patreon puede variar, intentamos una forma compatible
                    response = patreon_client.get_identity().data()
                    name = response.attribute('full_name')
                    await message.channel.send(f"Conectado a Patreon como: **{name}**. El sistema de verificación está listo.")
                except Exception as e:
                    await message.channel.send(f"Error al verificar Patreon: {str(e)}")

        elif command == "podcast":
            # Verificar si el usuario es premium o gamermauri_900
            premium_users = [] # Aquí irían los IDs de usuarios premium
            is_vip = str(message.author) == "gamermauri_900"
            is_premium = str(message.author.id) in premium_users

            if not is_vip and not is_premium:
                await message.channel.send("Este comando es premium. Ve a https://patreon.com/ShilterTikTok?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink y dona para usar este comando.")
                return

            if not message.author.voice:
                await message.channel.send("Debes estar en un canal de voz para reproducir el podcast!")
                return

            voice_channel = message.author.voice.channel
            podcast_url = 'https://archive.org/download/testmp3/test.mp3'

            try:
                if message.guild.voice_client is None:
                    vc = await asyncio.wait_for(voice_channel.connect(timeout=60.0, reconnect=True), timeout=65.0)
                else:
                    vc = message.guild.voice_client
                    if vc.channel != voice_channel:
                        await vc.move_to(voice_channel)
                
                # Esperar estabilidad
                await asyncio.sleep(2)

                # vc es garantizado por la lógica anterior
                if vc.is_playing() or vc.is_paused():
                    vc.stop()
                
                if guild_id in self.queues:
                    self.queues[guild_id].clear()

                source = await discord.FFmpegOpusAudio.from_probe(podcast_url, **FFMPEG_OPTIONS)
                vc.play(source)
                await message.channel.send(f"🎧 Reproduciendo el podcast de Archive.org para **{message.author.name}**")
            except Exception as e:
                try:
                    source = discord.FFmpegPCMAudio(podcast_url, **FFMPEG_OPTIONS)
                    vc.play(discord.PCMVolumeTransformer(source))
                    await message.channel.send(f"🎧 Reproduciendo el podcast (respaldo) para **{message.author.name}**")
                except Exception as e2:
                    await message.channel.send(f"Error al reproducir el podcast: {str(e2)}")

        elif command == "status":
            await message.channel.send(f"🤖 **Estado del Bot**\n📍 **Servidor actual**: {os.uname().nodename if hasattr(os, 'uname') else 'Windows/Other'}\n⏱️ **Latencia**: {round(self.latency * 1000)}ms")

        elif command == "mute":
            if not message.author.guild_permissions.moderate_members:
                await message.channel.send("No tienes permisos para usar este comando.")
                return
            
            if not message.mentions:
                await message.channel.send(f"Uso: {active_prefix}mute @usuario")
                return
            
            target = message.mentions[0]
            try:
                # En discord.py 2.0+, mute se hace a menudo con timeout o quitando roles
                # Intentamos mutear en voz si está conectado
                if target.voice:
                    await target.edit(mute=True)
                    await message.channel.send(f"🔇 {target.display_name} ha sido silenciado en voz.")
                else:
                    await message.channel.send(f"El usuario {target.display_name} no está en un canal de voz.")
            except Exception as e:
                await message.channel.send(f"Error al mutear: {str(e)}")

        elif command == "unmute":
            if not message.author.guild_permissions.moderate_members:
                await message.channel.send("No tienes permisos para usar este comando.")
                return
            
            if not message.mentions:
                await message.channel.send(f"Uso: {active_prefix}unmute @usuario")
                return
            
            target = message.mentions[0]
            try:
                if target.voice:
                    await target.edit(mute=False)
                    await message.channel.send(f"🔊 {target.display_name} ya no está silenciado en voz.")
                else:
                    await message.channel.send(f"El usuario {target.display_name} no está en un canal de voz.")
            except Exception as e:
                await message.channel.send(f"Error al desmutear: {str(e)}")

        elif command == "kick":
            if not message.author.guild_permissions.kick_members:
                await message.channel.send("No tienes permisos para expulsar miembros.")
                return
            
            if not message.mentions:
                await message.channel.send(f"Uso: {active_prefix}kick @usuario")
                return
            
            target = message.mentions[0]
            try:
                await target.kick(reason=f"Expulsado por {message.author}")
                await message.channel.send(f"👢 {target.display_name} ha sido expulsado.")
            except Exception as e:
                await message.channel.send(f"Error al expulsar: {str(e)}")

        elif command == "create":
            if not args:
                await message.channel.send(f"Uso: {active_prefix}create [nombre]")
                return
            
            # Guardar el nombre deseado en una propiedad del cliente temporalmente o pasarlo en el botón
            # Para simplificar en discord.py, usamos una vista con botones
            class TicketView(discord.ui.View):
                def __init__(self, ticket_name, author_id):
                    super().__init__(timeout=60)
                    self.ticket_name = ticket_name
                    self.author_id = author_id

                @discord.ui.button(label="Canal de Texto", style=discord.ButtonStyle.primary)
                async def text_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.author_id:
                        await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
                        return
                    
                    guild = interaction.guild
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                    }
                    channel = await guild.create_text_channel(name=f"ticket-{self.ticket_name}", overwrites=overwrites)
                    await interaction.response.send_message(f"✅ Canal de texto privado creado: {channel.mention}", ephemeral=True)
                    await channel.send(f"Hola {interaction.user.mention}, este es tu ticket privado para '{self.ticket_name}'.")
                    self.stop()

                @discord.ui.button(label="Hilo", style=discord.ButtonStyle.secondary)
                async def thread_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.author_id:
                        await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
                        return
                    
                    # Crear un hilo privado
                    thread = await interaction.channel.create_thread(
                        name=f"ticket-{self.ticket_name}",
                        type=discord.ChannelType.private_thread,
                        auto_archive_duration=60
                    )
                    await thread.add_user(interaction.user)
                    await interaction.response.send_message(f"✅ Hilo privado creado: {thread.mention}", ephemeral=True)
                    await thread.send(f"Hola {interaction.user.mention}, este es tu hilo privado para '{self.ticket_name}'.")
                    self.stop()

            view = TicketView(args, message.author.id)
            await message.channel.send("¿Qué tipo de ticket desea crear?", view=view)

        elif command == "add":
            if not message.channel.type == discord.ChannelType.public_thread:
                await message.channel.send("Este comando solo funciona dentro de un ticket (hilo).")
                return
            
            if not message.mentions:
                await message.channel.send(f"Uso: {active_prefix}add @usuario")
                return
            
            target = message.mentions[0]
            try:
                await message.channel.add_user(target)
                await message.channel.send(f"✅ {target.mention} ha sido añadido al ticket.")
            except Exception as e:
                await message.channel.send(f"Error al añadir usuario: {str(e)}")

        elif command == "delete" or command == "borrar":
            if not message.channel.type == discord.ChannelType.public_thread:
                await message.channel.send("Este comando solo funciona dentro de un ticket (hilo).")
                return
            
            try:
                await message.channel.send("⚠️ Cerrando y eliminando este ticket en 5 segundos...")
                await asyncio.sleep(5)
                await message.channel.delete()
            except Exception as e:
                await message.channel.send(f"Error al borrar el ticket: {str(e)}")

        elif command == "ia":
            if not args:
                await message.channel.send(f"Uso: {active_prefix}ia texto: [tu mensaje]")
                return
            
            prompt = args
            if prompt.lower().startswith("texto:"):
                prompt = prompt[6:].strip()
            
            if not prompt:
                await message.channel.send("Por favor, escribe un mensaje para la IA.")
                return

            async with message.channel.typing():
                try:
                    if GEMINI_KEY:
                        # Usar un prompt que fuerce una respuesta compatible con Discord (evitar bloqueos de seguridad si es posible)
                        safe_prompt = f"Responde de forma concisa y amigable en español: {prompt}"
                        # Ejecutar en hilo para no bloquear el bot
                        response = await asyncio.to_thread(model.generate_content, safe_prompt)
                        
                        if response and hasattr(response, 'text'):
                            text = response.text
                            if len(text) > 1900:
                                text = text[:1900] + "..."
                            await message.channel.send(f"🤖 **Gemini AI:**\n{text}")
                        else:
                            await message.channel.send("La IA no pudo generar una respuesta. Puede que el contenido haya sido filtrado por seguridad.")
                    else:
                        await message.channel.send("El servicio de IA no está configurado (falta GOOGLE_API_KEY).")
                except Exception as e:
                    error_str = str(e)
                    if "safety" in error_str.lower():
                        await message.channel.send("La IA no puede responder a eso debido a sus filtros de seguridad.")
                    else:
                        await message.channel.send(f"Error al procesar con la IA: {error_str}")

        elif command == "menu":
            menu = (
                "🎛️ **Menú del Bot** 🎛️\n"
                "🔐 **Moderación**: `mute` (@usuario)\n"
                "🎵 **Música**: `play` (link/nombre), `pause`, `resume`, `skip`, `queue`, `stop`\n"
                "💎 **Patreon**: `checkpatron` (verifica estado)\n"
                "🧾 **Tickets**: `create` (nombre), `add`, `delete`, `borrar`"
            )
            await message.channel.send(menu)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

client = MyClient(intents=intents)

if TOKEN:
    client.run(TOKEN)
else:
    print("Error: No se encontró DISCORD_BOT_TOKEN en los Secrets.")
