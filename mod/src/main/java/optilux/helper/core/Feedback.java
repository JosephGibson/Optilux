package optilux.helper.core;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * One `command`'s feedback (docs/mod-protocol.md#commands): the game layer hands it every message
 * the command's source received, each marked success or failure, and every result the source's
 * callback got (26.3: brigadier's result consumer reports each executed context, false for a
 * CommandSyntaxException). A command succeeded when no failure was sent, at least one context
 * reported a result and every result was a success: a parse error or an internal exception sends a
 * failure and reports no result, and a fork over no target reports none either.
 */
public final class Feedback {
    private final List<String> messages = new ArrayList<>();
    private final List<String> failures = new ArrayList<>();
    private int successes;
    private int failed;

    public synchronized void message(String text) {
        messages.add(text);
    }

    public synchronized void failure(String text) {
        failures.add(text);
    }

    public synchronized void result(boolean success, int value) {
        if (success) {
            successes++;
        } else {
            failed++;
        }
    }

    public synchronized boolean succeeded() {
        return failures.isEmpty() && failed == 0 && successes > 0;
    }

    /** The answer's fields: succeeded, messages, failures. */
    public synchronized Map<String, Object> outcome() {
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("succeeded", succeeded());
        found.put("messages", List.copyOf(messages));
        found.put("failures", List.copyOf(failures));
        return found;
    }
}
