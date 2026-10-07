package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import optilux.helper.core.FrameClock;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

/** The frame hook's polls (docs/mod.md#4-architecture): a failing adapter never stops another. */
class HooksTest {
    @AfterEach
    void detach() {
        Hooks.attach(List.of(), () -> { }, error -> { }, () -> false, message -> { });
        Hooks.open(null);
    }

    @Test
    void oneFailingPollNeitherStopsTheOthersNorReportsTwice() {
        AtomicLong counter = new AtomicLong(10_000_000L);
        Hooks.open(new FrameClock(counter::incrementAndGet, 10_000_000L));
        List<String> errors = new ArrayList<>();
        AtomicInteger iris = new AtomicInteger();
        AtomicInteger broken = new AtomicInteger();
        Hooks.attach(List.of(
            new Hooks.Poll("renderer", () -> {
                if (broken.incrementAndGet() != 3) {
                    throw new IllegalStateException("no renderer");
                }
            }),
            new Hooks.Poll("iris", iris::incrementAndGet)), () -> { }, error -> { }, () -> false,
            errors::add);
        for (int frame = 0; frame < 4; frame++) {
            Hooks.frameHead();
        }
        assertEquals(4, iris.get(), "the later poll ran every frame");
        // Frames 1-2 are one run of failures, frame 3 passed, frame 4 starts a new run.
        assertEquals(List.of(
            "frame poll renderer at frame 1: java.lang.IllegalStateException: no renderer",
            "frame poll renderer at frame 4: java.lang.IllegalStateException: no renderer"), errors);
    }
}
