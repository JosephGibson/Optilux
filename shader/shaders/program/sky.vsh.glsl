// The vertex stage of the sky's two programs. skybasic (SKY_NONE) draws nothing: vanilla's sky
// dome, stars and sunrise fan give way to deferred's gradient (plans/m4.md D78; sky= and stars=
// cannot remove them, P12), so every vertex lands outside the clip volume and no fragment runs.
// skytextured keeps vanilla's sun and moon (and the End's sky box and flash): its sprites go into
// the early target, which deferred adds at the sky's pixels.

in vec3 vaPosition;

#ifndef SKY_NONE
in vec4 vaColor;
in vec2 vaUV0;
uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
out vec4 vertexColor;
out vec2 albedoCoord;
#endif

void main() {
#ifdef SKY_NONE
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
#else
    gl_Position = projectionMatrix * (modelViewMatrix * vec4(vaPosition, 1.0));
    vertexColor = vaColor;
    albedoCoord = vaUV0;
#endif
}
