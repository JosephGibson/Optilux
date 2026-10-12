package optilux.helper;

import optilux.helper.core.Timers;
import org.lwjgl.opengl.GL15C;
import org.lwjgl.opengl.GL33C;

/**
 * The timers' GL queries through the LWJGL the game ships, on the render thread, where the game's
 * context is current. GL_TIMESTAMP queries need GL 3.3, the game's 3.3 core context
 * (docs/platform.md#mc-263); none touches state GlStateManager caches.
 */
final class GlQueries implements Timers.Gl {
    @Override
    public void generate(int[] names) {
        GL15C.glGenQueries(names);
    }

    @Override
    public void timestamp(int name) {
        GL33C.glQueryCounter(name, GL33C.GL_TIMESTAMP);
    }

    @Override
    public boolean available(int name) {
        return GL15C.glGetQueryObjecti(name, GL15C.GL_QUERY_RESULT_AVAILABLE) != 0;
    }

    @Override
    public long result(int name) {
        return GL33C.glGetQueryObjecti64(name, GL15C.GL_QUERY_RESULT);
    }

    @Override
    public void delete(int[] names) {
        GL15C.glDeleteQueries(names);
    }
}
