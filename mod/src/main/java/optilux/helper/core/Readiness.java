package optilux.helper.core;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * The readiness predicate and one `ready` wait (docs/mod.md#7-readiness). A {@link Reading} is one
 * frame's look at the renderer, taken on the render thread by the renderer adapter; the predicate
 * holds when every term does, judged in the order of {@link #TERMS}. A wait answers at the first
 * frame where the predicate has held for stableFrames consecutive frames and minSeconds have
 * passed. The renderer's own check (Sodium's isTerrainRenderComplete, which reads only the build
 * queue) is tracked beside it with the same run rule, and every frame where it held while the
 * predicate did not is counted: the gap ALC found.
 */
public final class Readiness {
    /** The predicate's terms in the order they are judged; a reading names the first failing. */
    public static final String[] TERMS = {"inWorld", "noScreen", "sections", "buildQueue",
        "busyThreads", "buildResults", "runningJobs", "taskLists", "submittedTasks", "graph"};

    /**
     * One frame's renderer state. sections: the renderer's section count; queuedJobs: jobs in the
     * build queue; busyThreads: builder threads inside a job; buildResults: finished jobs not yet
     * uploaded; runningJobs: sections holding a job not yet collected (a worker holds a dequeued
     * job before it counts as busy); taskLists: sections the last cull left to submit, -1 before
     * the first cull; submittedTasks: tasks the last update submitted (this frame's, next frame's
     * and deferred); graphClean: no graph update pending and no cull task running;
     * rendererCheck: the renderer's own check.
     */
    public record Reading(boolean inWorld, boolean noScreen, int sections, int queuedJobs,
        int busyThreads, int buildResults, int runningJobs, int taskLists, int submittedTasks,
        boolean graphClean, boolean rendererCheck) {

        /** The first failing term, or null when the predicate holds. */
        public String failing() {
            boolean[] holds = {inWorld, noScreen, sections > 0, queuedJobs == 0, busyThreads == 0,
                buildResults == 0, runningJobs == 0, taskLists == 0, submittedTasks == 0,
                graphClean};
            for (int i = 0; i < holds.length; i++) {
                if (!holds[i]) {
                    return TERMS[i];
                }
            }
            return null;
        }

        public Map<String, Object> fields() {
            Map<String, Object> found = new LinkedHashMap<>();
            found.put("inWorld", inWorld);
            found.put("noScreen", noScreen);
            found.put("sections", sections);
            found.put("queuedJobs", queuedJobs);
            found.put("busyThreads", busyThreads);
            found.put("buildResults", buildResults);
            found.put("runningJobs", runningJobs);
            found.put("taskLists", taskLists);
            found.put("submittedTasks", submittedTasks);
            found.put("graphClean", graphClean);
            found.put("rendererCheck", rendererCheck);
            return found;
        }
    }

    /** The renderer's own check, named in the answer. */
    public static final String RENDERER_CHECK = "SodiumWorldRenderer.isTerrainRenderComplete";

    private final int stableFrames;
    private final long minNanos;
    private final long startNanos;
    private int run;
    private long runDoneNanos = -1;
    private String lastFailing;
    private int rendererRun;
    private long rendererNanos = -1;
    private int gapFrames;
    private int frames;
    private Reading last;

    public Readiness(int stableFrames, double minSeconds, long startNanos) {
        if (stableFrames < 1) {
            throw new IllegalArgumentException("stableFrames " + stableFrames + " is below 1");
        }
        this.stableFrames = stableFrames;
        this.minNanos = (long) (minSeconds * 1e9);
        this.startNanos = startNanos;
    }

    /** Judge one frame; the answer's fields once the wait is over, else null. */
    public Map<String, Object> frame(Reading reading, long nowNanos) {
        frames++;
        last = reading;
        String failing = reading.failing();
        if (failing == null) {
            run++;
            if (run == stableFrames) {
                runDoneNanos = nowNanos;
            }
        } else {
            run = 0;
            runDoneNanos = -1;
            lastFailing = failing;
        }
        if (reading.rendererCheck()) {
            rendererRun++;
            if (rendererRun == stableFrames && rendererNanos < 0) {
                rendererNanos = nowNanos;
            }
            if (failing != null) {
                gapFrames++;
            }
        } else {
            rendererRun = 0;
        }
        if (run < stableFrames || nowNanos - startNanos < minNanos) {
            return null;
        }
        Map<String, Object> rendererCheck = new LinkedHashMap<>();
        rendererCheck.put("name", RENDERER_CHECK);
        rendererCheck.put("holds", reading.rendererCheck());
        rendererCheck.put("seconds", rendererNanos < 0 ? null : seconds(rendererNanos));
        rendererCheck.put("gapFrames", gapFrames);
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("seconds", seconds(nowNanos));
        found.put("predicateSeconds", seconds(runDoneNanos));
        found.put("limitedBy", runDoneNanos < nowNanos ? "minSeconds"
            : lastFailing == null ? "stableFrames" : lastFailing);
        found.put("rendererCheck", rendererCheck);
        found.put("frames", frames);
        return found;
    }

    /** The newest reading and its first failing term, for a wait that ends unanswered. */
    public String describe() {
        if (last == null) {
            return "no frame judged";
        }
        String failing = last.failing();
        return frames + " frames judged; last " + (failing == null ? "held (run " + run + " of "
            + stableFrames + ")" : "failed on " + failing) + ": " + last.fields();
    }

    private double seconds(long nanos) {
        return (nanos - startNanos) / 1e9;
    }
}
