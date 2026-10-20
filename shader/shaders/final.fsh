#version 330 core
// final: colortex0 onto the screen, texel for texel, opaque.

uniform sampler2D colortex0;

layout(location = 0) out vec4 screenColor;

void main() {
    screenColor = vec4(texelFetch(colortex0, ivec2(gl_FragCoord.xy), 0).rgb, 1.0);
}
