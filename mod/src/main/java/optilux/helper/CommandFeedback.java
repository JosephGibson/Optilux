package optilux.helper;

import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.TextColor;
import net.minecraft.network.chat.contents.PlainTextContents;

/**
 * How a command's failure reaches its source on 26.3: CommandSourceStack.sendFailure sends
 * Component.empty().append(message).withStyle(ChatFormatting.RED) (read in the pinned jar), while
 * sendSuccess sends the message itself.
 */
final class CommandFeedback {
    private static final TextColor FAILURE_COLOR = TextColor.fromLegacyFormat(ChatFormatting.RED);

    private CommandFeedback() {
    }

    /** The failure's text when `message` is sendFailure's wrapper, else null (a success line). */
    static String failureText(Component message) {
        if (message.getContents() == PlainTextContents.EMPTY && message.getSiblings().size() == 1
            && FAILURE_COLOR.equals(message.getStyle().getColor())) {
            return message.getSiblings().get(0).getString();
        }
        return null;
    }
}
