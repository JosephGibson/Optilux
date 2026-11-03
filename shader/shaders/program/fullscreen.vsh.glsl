// The vertex stage of the full-screen passes (deferred, composite, final): Iris draws a quad from
// (0, 0) to (1, 1); for these programs it maps modelViewMatrix to the identity and
// projectionMatrix to clip space.

in vec3 vaPosition;

uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;

void main() {
    gl_Position = projectionMatrix * (modelViewMatrix * vec4(vaPosition, 1.0));
}
