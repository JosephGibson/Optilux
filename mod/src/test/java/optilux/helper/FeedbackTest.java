package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Map;
import optilux.helper.core.Feedback;
import org.junit.jupiter.api.Test;

/** The feedback collector behind `command` (docs/mod-protocol.md#commands). */
class FeedbackTest {
    @Test
    void aCommandThatReportedSuccessAndNoFailureSucceeded() {
        Feedback feedback = new Feedback();
        feedback.message("The game is frozen");
        feedback.result(true, 1);
        assertEquals(Map.of("succeeded", true, "messages", List.of("The game is frozen"),
            "failures", List.of()), feedback.outcome());
    }

    @Test
    void aFailureMessageFailsIt() {
        // A parse error: performCommand sends a failure and no context reports a result.
        Feedback feedback = new Feedback();
        feedback.failure("Unknown or incomplete command");
        assertEquals(Map.of("succeeded", false, "messages", List.of(),
            "failures", List.of("Unknown or incomplete command")), feedback.outcome());
    }

    @Test
    void aFailedResultFailsItEvenAfterASuccess() {
        Feedback feedback = new Feedback();
        feedback.result(true, 1);
        feedback.result(false, 0);
        assertEquals(false, feedback.succeeded());
    }

    @Test
    void noResultAtAllIsNoSuccess() {
        // A fork over no target runs nothing and reports nothing.
        assertEquals(false, new Feedback().succeeded());
    }

    @Test
    void messagesKeepTheirOrder() {
        Feedback feedback = new Feedback();
        feedback.message("a");
        feedback.message("b");
        feedback.result(true, 2);
        assertEquals(List.of("a", "b"), feedback.outcome().get("messages"));
    }
}
