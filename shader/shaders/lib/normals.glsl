// Unit normals as two signed 7-bit codes, -63 to 63, on the octahedral map (Cigolle et al. 2014,
// "A Survey of Efficient Representations for Independent Unit Vectors"): the normal is divided by
// its L1 norm, which puts it on the octahedron |x| + |y| + |z| = 1; the upper half keeps x and y,
// the lower half is folded out over the square's corners. 63 steps a side with an exact 0 code keep
// the six axis normals, all of terrain's, exact.

#ifndef OPTILUX_NORMALS
#define OPTILUX_NORMALS 1

#define NORMAL_STEPS 63.0

// Each component's sign, 1 for 0, so the fold sends (0, 0, -1) to a corner.
vec2 signOrOne(vec2 v) {
    return vec2(v.x >= 0.0 ? 1.0 : -1.0, v.y >= 0.0 ? 1.0 : -1.0);
}

// The two codes (whole numbers in [-63, 63], as floats) of a unit normal.
vec2 normalCodes(vec3 normal) {
    vec2 square = normal.xy / (abs(normal.x) + abs(normal.y) + abs(normal.z));
    if (normal.z < 0.0) square = (1.0 - abs(square.yx)) * signOrOne(square);
    return floor(clamp(square, -1.0, 1.0) * NORMAL_STEPS + 0.5);
}

// The unit normal two codes stand for.
vec3 normalFromCodes(vec2 codes) {
    vec2 square = codes / NORMAL_STEPS;
    vec3 normal = vec3(square, 1.0 - abs(square.x) - abs(square.y));
    if (normal.z < 0.0) normal.xy = (1.0 - abs(normal.yx)) * signOrOne(normal.xy);
    return normalize(normal);
}

#endif
