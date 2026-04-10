import net.dv8tion.jda.api.JDABuilder;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.events.message.MessageReceivedEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.requests.GatewayIntent;

import javax.annotation.Nonnull;

public class ArcLivingSong extends ListenerAdapter {
    public static void main(String[] args) {
        String token = System.getenv("DISCORD_BOT_TOKEN");
        if (token == null) {
            System.out.println("Error: DISCORD_BOT_TOKEN no encontrado.");
            return;
        }

        JDABuilder.createDefault(token)
                .enableIntents(GatewayIntent.GUILD_MESSAGES, GatewayIntent.MESSAGE_CONTENT, GatewayIntent.GUILD_VOICE_STATES)
                .addEventListeners(new ArcLivingSong())
                .build();
    }

    @Override
    public void onMessageReceived(@Nonnull MessageReceivedEvent event) {
        if (event.getAuthor().isBot()) return;

        String msg = event.getMessage().getContentRaw();
        if (msg.startsWith("/") || msg.startsWith("#")) {
            String command = msg.substring(1).split(" ")[0].toLowerCase();
            
            if (command.equals("create")) {
                event.getGuild().createTextChannel("ticket-" + event.getAuthor().getName())
                        .queue(channel -> event.getChannel().sendMessage("Ticket creado: " + channel.getAsMention()).queue());
            }
        }
    }
}
