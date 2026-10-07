package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;
import optilux.helper.core.Readiness;
import org.junit.jupiter.api.Test;

/** The readiness predicate and one wait on fake renderer states (docs/mod.md#7-readiness). */
class ReadinessTest {
    private static final long MS = 1_000_000L;
    /** A renderer with nothing left to do. */
    private static final Readiness.Reading SETTLED =
        new Readiness.Reading(true, true, 900, 0, 0, 0, 0, 0, 0, true, true);

    private static Readiness.Reading with(String term) {
        Readiness.Reading s = SETTLED;
        return switch (term) {
            case "inWorld" -> new Readiness.Reading(false, true, 900, 0, 0, 0, 0, 0, 0, true, true);
            case "noScreen" -> new Readiness.Reading(true, false, 900, 0, 0, 0, 0, 0, 0, true, true);
            case "sections" -> new Readiness.Reading(true, true, 0, 0, 0, 0, 0, 0, 0, true, true);
            case "buildQueue" -> new Readiness.Reading(true, true, 900, 4, 0, 0, 0, 0, 0, true, false);
            case "busyThreads" -> new Readiness.Reading(true, true, 900, 0, 2, 0, 0, 0, 0, true, true);
            case "buildResults" -> new Readiness.Reading(true, true, 900, 0, 0, 3, 0, 0, 0, true, true);
            // A worker holds a dequeued job before it counts as busy: the queue is empty, so
            // Sodium's own check holds, and only the section's running job shows it.
            case "runningJobs" -> new Readiness.Reading(true, true, 900, 0, 0, 0, 1, 0, 0, true, true);
            case "taskLists" -> new Readiness.Reading(true, true, 900, 0, 0, 0, 0, 5, 0, true, true);
            case "submittedTasks" -> new Readiness.Reading(true, true, 900, 0, 0, 0, 0, 0, 2, true, true);
            case "graph" -> new Readiness.Reading(true, true, 900, 0, 0, 0, 0, 0, 0, false, true);
            default -> s;
        };
    }

    @Test
    void eachTermFailsThePredicateByName() {
        assertNull(SETTLED.failing());
        for (String term : Readiness.TERMS) {
            assertEquals(term, with(term).failing());
        }
        // Before the first cull the task lists are absent (-1), which is not empty.
        assertEquals("taskLists",
            new Readiness.Reading(true, true, 900, 0, 0, 0, 0, -1, 0, true, true).failing());
    }

    @Test
    void theWaitAnswersAfterStableFramesAndNamesTheLastTermThatFailed() {
        Readiness wait = new Readiness(3, 0, 0);
        assertNull(wait.frame(with("buildQueue"), 10 * MS));
        assertNull(wait.frame(with("runningJobs"), 20 * MS));
        assertNull(wait.frame(SETTLED, 30 * MS));
        assertNull(wait.frame(SETTLED, 40 * MS));
        Map<String, Object> answer = wait.frame(SETTLED, 50 * MS);
        assertEquals(0.05, answer.get("seconds"));
        assertEquals(0.05, answer.get("predicateSeconds"));
        assertEquals("runningJobs", answer.get("limitedBy"));
        assertEquals(5, answer.get("frames"));
        // Sodium's own check held from frame 2 on (its run of 3 ended at frame 4) and held once
        // while the predicate did not: the gap the predicate closes.
        assertEquals(Map.of("name", Readiness.RENDERER_CHECK, "holds", true, "seconds", 0.04,
            "gapFrames", 1), answer.get("rendererCheck"));
    }

    @Test
    void aBrokenRunStartsOver() {
        Readiness wait = new Readiness(2, 0, 0);
        assertNull(wait.frame(SETTLED, 10 * MS));
        assertNull(wait.frame(with("graph"), 20 * MS));
        assertNull(wait.frame(SETTLED, 30 * MS));
        Map<String, Object> answer = wait.frame(SETTLED, 40 * MS);
        assertEquals("graph", answer.get("limitedBy"));
        assertEquals(0.04, answer.get("predicateSeconds"));
    }

    @Test
    void minSecondsHoldsTheAnswerBackAndSaysSo() {
        Readiness wait = new Readiness(2, 0.1, 0);
        assertNull(wait.frame(SETTLED, 10 * MS));
        assertNull(wait.frame(SETTLED, 20 * MS));
        assertNull(wait.frame(SETTLED, 60 * MS));
        Map<String, Object> answer = wait.frame(SETTLED, 110 * MS);
        assertEquals(0.11, answer.get("seconds"));
        assertEquals(0.02, answer.get("predicateSeconds"));
        assertEquals("minSeconds", answer.get("limitedBy"));
    }

    @Test
    void aPredicateThatHeldFromTheFirstFrameIsLimitedByStableFrames() {
        Readiness wait = new Readiness(1, 0, 0);
        Map<String, Object> answer = wait.frame(SETTLED, 5 * MS);
        assertEquals("stableFrames", answer.get("limitedBy"));
    }

    @Test
    void theRenderersCheckIsReportedEvenWhenItNeverHeld() {
        Readiness wait = new Readiness(1, 0, 0);
        Readiness.Reading noOwnCheck =
            new Readiness.Reading(true, true, 900, 0, 0, 0, 0, 0, 0, true, false);
        Map<?, ?> check = (Map<?, ?>) wait.frame(noOwnCheck, 5 * MS).get("rendererCheck");
        assertEquals(false, check.get("holds"));
        assertNull(check.get("seconds"));
        assertEquals(0, check.get("gapFrames"));
    }

    @Test
    void anUnansweredWaitDescribesItsLastReading() {
        Readiness wait = new Readiness(5, 0, 0);
        assertEquals("no frame judged", wait.describe());
        wait.frame(with("busyThreads"), MS);
        assertEquals(true, wait.describe().startsWith("1 frames judged; last failed on busyThreads"));
        assertThrows(IllegalArgumentException.class, () -> new Readiness(0, 0, 0));
    }
}
