package com.bot;

import net.dv8tion.jda.api.JDABuilder;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Role;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.dv8tion.jda.api.entities.channel.concrete.ThreadChannel;
import net.dv8tion.jda.api.entities.channel.unions.MessageChannelUnion;
import net.dv8tion.jda.api.events.message.MessageReceivedEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.requests.GatewayIntent;
import net.dv8tion.jda.api.entities.channel.concrete.VoiceChannel;
import net.dv8tion.jda.api.audio.AudioSendHandler;
import net.dv8tion.jda.api.utils.MemberCachePolicy;

import com.sedmelluq.discord.lavaplayer.player.AudioPlayer;
import com.sedmelluq.discord.lavaplayer.player.AudioPlayerManager;
import com.sedmelluq.discord.lavaplayer.player.DefaultAudioPlayerManager;
import com.sedmelluq.discord.lavaplayer.source.youtube.YoutubeAudioSourceManager;
import com.sedmelluq.discord.lavaplayer.track.AudioTrack;
import com.sedmelluq.discord.lavaplayer.track.playback.MutableAudioFrame;

import java.nio.ByteBuffer;
import java.util.List;
import java.util.Random;

public class Main extends ListenerAdapter {
    private final MusicManager musicManager = new MusicManager();
    private final String[] prefixes = {"/", "#"};

    public static void main(String[] args) {
        String token = System.getenv("DISCORD_TOKEN");
        if (token == null || token.isEmpty()) {
            System.err.println("Por favor, configura la variable de entorno DISCORD_TOKEN");
            return;
        }
        JDABuilder.createDefault(token)
                .enableIntents(GatewayIntent.GUILD_MESSAGES, GatewayIntent.MESSAGE_CONTENT, GatewayIntent.GUILD_MEMBERS, GatewayIntent.GUILD_VOICE_STATES)
                .setMemberCachePolicy(MemberCachePolicy.ALL)
                .addEventListeners(new Main())
                .build();
    }

    @Override
    public void onMessageReceived(MessageReceivedEvent event) {
        if (event.getAuthor().isBot()) return;

        String msg = event.getMessage().getContentRaw();
        String activePrefix = null;
        for (String p : prefixes) {
            if (msg.startsWith(p)) {
                activePrefix = p;
                break;
            }
        }

        if (activePrefix == null) return;

        MessageChannelUnion channel = event.getChannel();
        Member author = event.getMember();

        if (msg.startsWith(activePrefix + "mute")) {
            if (author != null && author.hasPermission(net.dv8tion.jda.api.Permission.MANAGE_ROLES)) {
                List<Member> members = event.getMessage().getMentions().getMembers();
                if (!members.isEmpty()) {
                    Member target = members.get(0);
                    List<Role> roles = event.getGuild().getRolesByName("Muted", true);
                    if (!roles.isEmpty()) {
                        Role muteRole = roles.get(0);
                        event.getGuild().addRoleToMember(target, muteRole).queue();
                        channel.sendMessage("Usuario silenciado: " + target.getEffectiveName()).queue();
                    } else channel.sendMessage("Rol 'Muted' no encontrado").queue();
                } else channel.sendMessage("Uso: " + activePrefix + "mute @usuario").queue();
            } else channel.sendMessage("No tienes permisos para silenciar").queue();
        }

        if (msg.startsWith(activePrefix + "create")) {
            String[] parts = msg.split(" ", 2);
            if (parts.length < 2) { channel.sendMessage("Debes indicar nombre del ticket").queue(); return; }
            String ticketName = parts[1];
            if (channel instanceof TextChannel textChannel) {
                textChannel.createThreadChannel(ticketName).queue(thread -> {
                    channel.sendMessage("Ticket creado: " + ticketName).queue();
                });
            }
        }

        if (msg.startsWith(activePrefix + "add")) {
            List<Member> members = event.getMessage().getMentions().getMembers();
            if (!members.isEmpty() && channel instanceof ThreadChannel thread) {
                thread.addThreadMember(members.get(0)).queue();
                channel.sendMessage("Usuario añadido al ticket").queue();
            }
        }

        if (msg.startsWith(activePrefix + "delete")) {
            List<Member> members = event.getMessage().getMentions().getMembers();
            if (!members.isEmpty() && channel instanceof ThreadChannel thread) {
                thread.removeThreadMember(members.get(0)).queue();
                channel.sendMessage("Usuario eliminado del ticket").queue();
            }
        }

        if (msg.startsWith(activePrefix + "borrar")) {
            if (channel instanceof ThreadChannel thread) {
                thread.delete().queue();
            }
        }

        if (msg.startsWith(activePrefix + "menu")) {
            String menu = """
                    🎛️ Menú del Bot 🎛️
                    🔐 Moderación: mute, ban, warn, clear 
                    🎵 Música: play, stop, skip, queque, radio
                    🧾 Tickets: create, add, delete, borrar
                    🎥 Streams: stream
                    🎮 Juegos: trivia, adivina
                    """;
            channel.sendMessage(menu).queue();
        }

        if (msg.startsWith(activePrefix + "play")) {
            String[] parts = msg.split(" ", 2);
            if (parts.length < 2) { channel.sendMessage("Uso: " + activePrefix + "play [canción/url]").queue(); return; }
            if (event.getMember().getVoiceState().getChannel() instanceof VoiceChannel vc) {
                musicManager.play(parts[1], vc, channel);
            } else {
                channel.sendMessage("Debes estar en un canal de voz").queue();
            }
        }

        if (msg.startsWith(activePrefix + "stop")) {
            if (event.getMember().getVoiceState().getChannel() instanceof VoiceChannel vc) {
                musicManager.stop(vc);
                channel.sendMessage("Música detenida").queue();
            }
        }
    }
}

class MusicManager {
    private final AudioPlayerManager playerManager;
    private final AudioPlayer player;

    public MusicManager() {
        this.playerManager = new DefaultAudioPlayerManager();
        playerManager.registerSourceManager(new YoutubeAudioSourceManager());
        this.player = playerManager.createPlayer();
    }

    public void play(String query, VoiceChannel vc, MessageChannelUnion channel) {
        String url = query.startsWith("https://") ? query : "ytsearch:" + query;
        playerManager.loadItem(url, new com.sedmelluq.discord.lavaplayer.player.AudioLoadResultHandler() {
            @Override
            public void trackLoaded(AudioTrack track) {
                player.playTrack(track);
                joinChannel(vc);
                channel.sendMessage("Reproduciendo: " + track.getInfo().title).queue();
            }

            @Override
            public void playlistLoaded(com.sedmelluq.discord.lavaplayer.track.AudioPlaylist playlist) {
                AudioTrack track = playlist.getTracks().get(0);
                player.playTrack(track);
                joinChannel(vc);
                channel.sendMessage("Reproduciendo: " + track.getInfo().title).queue();
            }

            @Override
            public void noMatches() {
                channel.sendMessage("No se encontró la canción").queue();
            }

            @Override
            public void loadFailed(com.sedmelluq.discord.lavaplayer.tools.FriendlyException exception) {
                channel.sendMessage("Error: " + exception.getMessage()).queue();
            }
        });
    }

    private void joinChannel(VoiceChannel vc) {
        vc.getGuild().getAudioManager().openAudioConnection(vc);
        vc.getGuild().getAudioManager().setSendingHandler(new AudioSendHandler() {
            private final ByteBuffer buffer = ByteBuffer.allocate(1024);
            private final MutableAudioFrame frame = new MutableAudioFrame();
            { frame.setBuffer(buffer); }
            @Override public boolean canProvide() { return player.provide(frame); }
            @Override public ByteBuffer provide20MsAudio() { buffer.flip(); return buffer; }
            @Override public boolean isOpus() { return true; }
        });
    }

    public void stop(VoiceChannel vc) {
        player.stopTrack();
        vc.getGuild().getAudioManager().closeAudioConnection();
    }
}
AudioPlayerManager playerManager = new DefaultAudioPlayerManager();
AudioPlayer player = playerManager.createPlayer();

// Metadata simulada (viene de Spotify / Apple Music)
String title = "Blinding Lights"
String artist = "The Weeknd"

// Query para otra fuente
String searchQuery = artist + " - " + title;

// Buscar en YouTube
playerManager.loadItem(
    "ytsearch:" + searchQuery,
    new AudioLoadResultHandler() {

        @Override
        public void trackLoaded(AudioTrack track) {
            player.playTrack(track);
        }

        @Override
        public void playlistLoaded(AudioPlaylist playlist) {
            player.playTrack(playlist.getTracks().get(0));
        }

        @Override
        public void noMatches() {
            System.out.println("No se encontró la canción");
        }

        @Override
        public void loadFailed(FriendlyException e) {
            e.printStackTrace();
        }
    }
);
// Buscar en Soundcloud
playerManager = new DefaultAudioPlayerManager();
"scsearch:" + searchQuery
    public class ModerationCommands extends ListenerAdapter {
    if (message.startsWith("#kick")) {

        if (!member.hasPermission(Permission.KICK_MEMBERS)) {
            channel.sendMessage("❌ No tienes permisos.").queue();
            return;
        }

        Member target = mentions.get(0);
        guild.kick(target)
            .queue(
                v -> channel.sendMessage("👢 Usuario ha sido expulsado.").queue(),
                e -> channel.sendMessage("❌ Error del sistema al expulsar.").queue()
            );
    }
if (message.startsWith("#warn")) {

    if (!member.hasPermission(Permission.MODERATE_MEMBERS)) {
        channel.sendMessage("❌ No tienes permisos.").queue();
        return;
    }

    Member target = mentions.get(0);
    String reason = message.replace("#warn", "")
                           .replace(target.getAsMention(), "")
                           .trim();

    channel.sendMessage(
        "⚠️ " + target.getAsMention() + " advertido\n📄 Razón: " + reason
    ).queue();
}
if (message.startsWith("#clear")) {

    if (!member.hasPermission(Permission.MESSAGE_MANAGE)) {
        channel.sendMessage("❌ Sin permisos").queue();
        return;
    }

    int amount = Integer.parseInt(args[1]);

    channel.getHistory().retrievePast(amount)
        .queue(messages -> {
            channel.deleteMessages(messages).queue();
            channel.sendMessage("🧹 " + amount + " mensajes eliminados del canal.")
                   .queue(m -> m.delete().queueAfter(5, TimeUnit.SECONDS));
        });
}
guild.upsertCommand("kick", "Expulsa a un usuario")
     .addOption(OptionType.USER, "usuario", "Usuario", true)
     .queue();

guild.upsertCommand("warn", "Advierte a un usuario")
     .addOption(OptionType.USER, "usuario", "Usuario", true)
     .addOption(OptionType.STRING, "razon", "Razón", true)
     .queue();

guild.upsertCommand("clear", "Borra mensajes")
     .addOption(OptionType.INTEGER, "cantidad", "Cantidad", true)
     .queue();
if (event.getName().equals("kick")) {
    Member target = event.getOption("usuario").getAsMember();
    guild.kick(target).queue();
    event.reply("👢 Usuario ha sido expulsado.").queue();
      event.reply("❌ Error del sistema al expulsar.").queue();
    if (event.getName().equals("warn")) {
        Member target = event.getOption("usuario").getAsMember();
        String reason = event.getOption("razon").getAsString();

        event.reply("⚠️ " + target.getAsMention() +
                    "\n📄 Razón: " + reason).queue();
    }
    if (event.getName().equals("clear")) {
        int amount = event.getOption("cantidad").getAsInt();

        event.getChannel().getHistory()
             .retrievePast(amount)
             .queue(msgs -> {
                 event.getChannel().deleteMessages(msgs).queue();
                 event.reply(""🧹 " + amount + " mensajes eliminados del canal.")
                      .setEphemeral(true).queue();
             });
    }
    import net.dv8tion.jda.api.*;
    import net.dv8tion.jda.api.entities.*;
    import net.dv8tion.jda.api.events.message.MessageReceivedEvent;
    import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
    import net.dv8tion.jda.api.hooks.ListenerAdapter;
    import net.dv8tion.jda.api.Permission;
    import net.dv8tion.jda.api.interactions.commands.OptionType;

    import java.util.EnumSet;
    import java.util.concurrent.TimeUnit;

    public class TicketBot extends ListenerAdapter {

        private static final String TICKET_CATEGORY = "Tickets";

        // ===================== PREFIX COMMANDS =====================
        @Override
        public void onMessageReceived(MessageReceivedEvent event) {
            if (event.getAuthor().isBot()) return;

            String msg = event.getMessage().getContentRaw().toLowerCase();
            Guild guild = event.getGuild();
            Member member = event.getMember();
            TextChannel channel = event.getChannel().asTextChannel();

            // ---------- CREATE TICKET ----------
            if (msg.startsWith("#create")) {
                createTicket(guild, member, channel);
            }

            // ---------- ADD USER ----------
            if (msg.startsWith("#add")) {
                addUser(event);
            }

            // ---------- DELETE TICKET ----------
            if (msg.startsWith("#delete") || msg.startsWith("#borrar")) {
                deleteTicket(channel);
            }
        }

        // ===================== SLASH COMMANDS =====================
        @Override
        public void onSlashCommandInteraction(SlashCommandInteractionEvent event) {
            Guild guild = event.getGuild();
            Member member = event.getMember();
            TextChannel channel = event.getChannel().asTextChannel();

            switch (event.getName()) {
                case "create":
                    createTicket(guild, member, channel);
                    event.reply("🎫 Ticket creado").setEphemeral(true).queue();
                    break;
                case "add":
                    Member target = event.getOption("usuario").getAsMember();
                    channel.upsertPermissionOverride(target)
                            .setAllowed(Permission.VIEW_CHANNEL, Permission.MESSAGE_SEND)
                            .queue();
                    event.reply("➕ Usuario agregado").queue();
                    break;
                case "delete":
                    deleteTicket(channel);
                    event.reply("🔒 Ticket cerrado").setEphemeral(true).queue();
                    break;
            }
        }

        // ===================== MÉTODOS =====================
        private void createTicket(Guild guild, Member member, TextChannel channel) {
            // Buscar o crear categoría Tickets
            Category category = guild.getCategoriesByName(TICKET_CATEGORY, true)
                    .stream().findFirst()
                    .orElse(guild.createCategory(TICKET_CATEGORY).complete());

            String channelName = "ticket-" + member.getUser().getName().toLowerCase();

            guild.createTextChannel(channelName, category)
                    .addPermissionOverride(guild.getPublicRole(), null,
                            EnumSet.of(Permission.VIEW_CHANNEL))
                    .addPermissionOverride(member,
                            EnumSet.of(Permission.VIEW_CHANNEL, Permission.MESSAGE_SEND),
                            null)
                    .queue(tc -> tc.sendMessage("🎫 Ticket creado por " + member.getAsMention()).queue());
        }

        private void addUser(MessageReceivedEvent event) {
            if (event.getMessage().getMentions().getMembers().isEmpty()) return;

            Member target = event.getMessage().getMentions().getMembers().get(0);
            TextChannel channel = event.getChannel().asTextChannel();

            channel.upsertPermissionOverride(target)
                    .setAllowed(Permission.VIEW_CHANNEL, Permission.MESSAGE_SEND)
                    .queue();

            channel.sendMessage("➕ " + target.getAsMention() + " agregado al ticket").queue();
        }

        private void deleteTicket(TextChannel channel) {
            if (!channel.getName().startsWith("ticket-")) return;
            channel.sendMessage("🔒 Cerrando ticket..").queue(msg ->
                            channel.delete().queueAfter(5, TimeUnit.SECONDS));
                }
            }
    import com.sedmelluq.discord.lavaplayer.player.AudioPlayer;
    import com.sedmelluq.discord.lavaplayer.track.playback.AudioFrame;
    import net.dv8tion.jda.api.audio.AudioSendHandler;

    import java.nio.ByteBuffer;

    public class AudioPlayerSendHandler implements AudioSendHandler {
        private final AudioPlayer audioPlayer;
        private AudioFrame lastFrame;

        public AudioPlayerSendHandler(AudioPlayer player) {
            this.audioPlayer = player;
        }

        @Override
        public boolean canProvide() {
            lastFrame = audioPlayer.provide();
            return lastFrame != null;
        }

        @Override
        public ByteBuffer provide20MsAudio() {
            return ByteBuffer.wrap(lastFrame.getData());
        }

        @Override
        public boolean isOpus() {
            return true;
        }
    }
    import net.dv8tion.jda.api.events.message.MessageReceivedEvent;
    import net.dv8tion.jda.api.hooks.ListenerAdapter;
    import net.dv8tion.jda.api.entities.Message;
    import net.dv8tion.jda.api.entities.TextChannel;
    import net.dv8tion.jda.api.entities.User;
    import java.util.HashMap;
    import java.util.Map;

    public class RadioCommand extends ListenerAdapter {

        // Mapa de emojis → URL de radios libres
        private final Map<String, String> radioMap = new HashMap<>();

        public RadioCommand() {
            radioMap.put("1️⃣", "https://ice1.somafm.com/groovesalad-128-mp3"); // Chill / Ambient
            radioMap.put("2️⃣", "http://64.71.79.181:5234/stream");             // Radio 35 Hip Hop CC
            radioMap.put("3️⃣", "http://ice.somafm.com/spacestation");          // Space Station SomaFM
            radioMap.put("4️⃣", "http://chill.friskyradio.com/friskychill_mp3_high"); // Frisky Chill
            radioMap.put("5️⃣", "http://ice1.somafm.com/secretagent-128-mp3"); // Secret Agent SomaFM
        }

        @Override
        public void onMessageReceived(MessageReceivedEvent event) {
            String msg = event.getMessage().getContentRaw();
            TextChannel channel = event.getTextChannel();

            // Comando /radio
            if (msg.equalsIgnoreCase("/radio" "#radio")) {
                StringBuilder sb = new StringBuilder("Radios para escuchar:\n");
                sb.append("1⃣: Groove Salad (Chill / Ambient)\n");
                sb.append("2⃣: Radio 35 Hip Hop (CC)\n");
                sb.append("3⃣: Space Station (SomaFM)\n");
                sb.append("4⃣: Frisky Chill (Electrónica)\n");
                sb.append("5⃣: Secret Agent (Lounge / Downtempo)\n");
                sb.append("「❖」𝖲𝖾𝗅𝖾𝖼𝖼𝗂𝗈𝗇𝖺 𝖾𝗅 𝖾𝗆𝗈𝗃𝗂 𝖼𝗈𝗋𝗋𝖾𝗌𝗉𝗈𝗇𝖽𝗂𝖾𝗇𝗍𝖾.")

                channel.sendMessage(sb.toString()).queue(message -> {
                    // Agregar reacciones para seleccionar
                    for (String emoji : radioMap.keySet()) {
                        message.addReaction(emoji).queue();
                    }
                });
            }
        }

        // Aquí manejarías las reacciones para reproducir la radio
        @Override
        public void onMessageReactionAdd(net.dv8tion.jda.api.events.message.react.MessageReactionAddEvent event) {
            User user = event.getUser();
            if (user.isBot()) return; // Ignorar bots

            String emoji = event.getReactionEmote().getName();

            if (radioMap.containsKey(emoji)) {
                String radioUrl = radioMap.get(emoji);
                event.getChannel().sendMessage("🎶【✦】Conectandome con la radio.." + radioUrl).queue();

                // Aquí iría tu código para reproducir el stream en el canal de voz
                // Ejemplo: playerManager.loadItem(radioUrl, new AudioLoadResultHandler() {...});
            }
        }
    }
    BufferedReader in = new BufferedReader(new InputStreamReader(con.getInputStream()));
            JsonObject json = JsonParser.parseReader(in).getAsJsonObject();
            in.close();

            String trackName = json.get("name").getAsString();
            String artistName = json.getAsJsonArray("artists").get(0).getAsJsonObject().get("name").getAsString();
            return trackName + " " + artistName;
        }

        private String getSpotifyPlaylistFirstTrack(String playlistId, String accessToken) throws IOException {
            URL url = new URL("https://api.spotify.com/v1/playlists/" + playlistId + "/tracks?limit=1");
            HttpURLConnection con = (HttpURLConnection) url.openConnection();
            con.setRequestProperty("Authorization", "Bearer " + accessToken);

            BufferedReader in = new BufferedReader(new InputStreamReader(con.getInputStream()));
            JsonObject json = JsonParser.parseReader(in).getAsJsonObject();
            in.close();

            JsonObject firstTrack = json.getAsJsonArray("items")
                    .get(0).getAsJsonObject()
                    .getAsJsonObject("track");

            String trackName = firstTrack.get("name").getAsString();
            String artistName = firstTrack.getAsJsonArray("artists").get(0).getAsJsonObject().get("name").getAsString();
            return trackName + " " + artistName;
        }
