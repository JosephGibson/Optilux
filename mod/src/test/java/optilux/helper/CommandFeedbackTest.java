package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import org.junit.jupiter.api.Test;

/**
 * A command's failure told from its success lines on 26.3's own components: sendFailure's wrapper,
 * Component.empty().append(message).withStyle(RED), against what sendSuccess sends.
 */
class CommandFeedbackTest {
    @Test
    void sendFailuresWrapperIsAFailure() {
        Component wrapped = Component.empty().append(Component.literal("Unknown or incomplete command"))
            .withStyle(ChatFormatting.RED);
        assertEquals("Unknown or incomplete command", CommandFeedback.failureText(wrapped));
    }

    @Test
    void successLinesAreNoFailures() {
        assertNull(CommandFeedback.failureText(Component.literal("The game has been frozen")));
        // Red text that is not the wrapper: a command's own coloured success line.
        assertNull(CommandFeedback.failureText(Component.literal("red").withStyle(ChatFormatting.RED)));
        // The wrapper's shape in another colour, and an empty red line with two parts.
        assertNull(CommandFeedback.failureText(Component.empty().append(Component.literal("x"))
            .withStyle(ChatFormatting.YELLOW)));
        assertNull(CommandFeedback.failureText(Component.empty().append(Component.literal("a"))
            .append(Component.literal("b")).withStyle(ChatFormatting.RED)));
    }
}
