package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;

import optilux.helper.core.TpSemantics;
import org.junit.jupiter.api.Test;

/**
 * `/tp` semantics on fixtures (docs/lessons.md#game-control; plans/m1.md 0.01.06): yaw 180 -> -180,
 * the +0.5 centre on integer x and z only, the pitch clamp, each as read in the 26.3 jar.
 */
class TpSemanticsTest {
    @Test
    void yawWrapsToMinus180To180() {
        assertEquals(-180.0f, TpSemantics.wrapDegrees(180.0f));
        assertEquals(-180.0f, TpSemantics.wrapDegrees(-180.0f));
        assertEquals(-180.0f, TpSemantics.wrapDegrees(540.0f));
        assertEquals(-170.0f, TpSemantics.wrapDegrees(190.0f));
        assertEquals(170.0f, TpSemantics.wrapDegrees(-190.0f));
        assertEquals(-0.5f, TpSemantics.wrapDegrees(359.5f));
        assertEquals(179.5f, TpSemantics.wrapDegrees(179.5f));
        assertEquals(0.0f, TpSemantics.wrapDegrees(720.0f));
    }

    @Test
    void integerXAndZAreCentredAndYNever() {
        TpSemantics.Pose integers = TpSemantics.apply(10, true, 64, -3, true, 0, 0);
        assertEquals(new TpSemantics.Pose(10.5, 64, -2.5, 0.0f, 0.0f), integers);
        TpSemantics.Pose decimals = TpSemantics.apply(10, false, 64, -3, false, 0, 0);
        assertEquals(new TpSemantics.Pose(10, 64, -3, 0.0f, 0.0f), decimals);
        TpSemantics.Pose mixed = TpSemantics.apply(0.25, false, 70.5, 7, true, 0, 0);
        assertEquals(new TpSemantics.Pose(0.25, 70.5, 7.5, 0.0f, 0.0f), mixed);
    }

    @Test
    void pitchIsWrappedThenClamped() {
        assertEquals(90.0f, TpSemantics.apply(0, false, 0, 0, false, 0, 100).pitch());
        assertEquals(-90.0f, TpSemantics.apply(0, false, 0, 0, false, 0, -95).pitch());
        // 270 wraps to -90 first, so it looks straight up, not down.
        assertEquals(-90.0f, TpSemantics.apply(0, false, 0, 0, false, 0, 270).pitch());
        assertEquals(45.5f, TpSemantics.apply(0, false, 0, 0, false, 0, 45.5).pitch());
        assertEquals(90.0f, TpSemantics.clampPitch(90.0f));
        assertEquals(-90.0f, TpSemantics.clampPitch(-450.0f));
    }

    @Test
    void anglesAreCastToFloatBeforeTheWrap() {
        TpSemantics.Pose pose = TpSemantics.apply(0, false, 0, 0, false, 180.0000001, 0.1);
        assertEquals(-180.0f, pose.yaw());
        assertEquals((float) 0.1, pose.pitch());
    }

    @Test
    void commandLiteralsCarryADecimalPoint() {
        assertEquals("10.0", TpSemantics.literal(10.0));
        assertEquals("-0.5", TpSemantics.literal(-0.5));
        assertEquals("10000000.0", TpSemantics.literal(1e7));
        assertEquals("0.000010", TpSemantics.literal(1e-5));
        assertEquals("-533.3000000000001", TpSemantics.literal(-533.3000000000001));
    }
}
