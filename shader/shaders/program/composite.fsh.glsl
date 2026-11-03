// composite: the end of the HDR chain (plans/m4.md D78): the scene exposed at its dimension's fixed
// exposure, graded and mapped by the display curve (lib/tonemap.glsl), encoded to sRGB into the
// RGB10_A2 display target that final dithers onto the screen.

#include "/lib/srgb.glsl"
#include "/lib/tonemap.glsl"

#if defined DIMENSION_NETHER
#define EXPOSURE 2.2
#elif defined DIMENSION_END
#define EXPOSURE 1.6
#else
#define EXPOSURE 1.0
#endif

uniform sampler2D colortex0;

/* RENDERTARGETS: 6 */
layout(location = 0) out vec4 displayOut;

void main() {
    vec3 scene = texelFetch(colortex0, ivec2(gl_FragCoord.xy), 0).rgb;
    displayOut = vec4(srgbFromLinear(tonemap(scene * EXPOSURE)), 1.0);
}
