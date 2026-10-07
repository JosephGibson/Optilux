package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import java.util.zip.ZipFile;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.AnnotationNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.FieldNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

/**
 * Every target of every mixin the config lists, read with ASM from the pinned jars' bytecode, the
 * authority (roadmap.md F9): the target class, the injected method by name and descriptor, each
 * INVOKE inside it, and each accessor's field by name and type. A mixin annotation, or an @Inject,
 * @At or @Accessor value, that this test does not read fails it, so a new kind of target cannot
 * pass unread. The adapters' direct calls and field reads into Sodium and Iris are read too: each
 * resolves in the pinned jars, and together they are the list below.
 */
class MixinTargetTest {
    private static final String MIXIN = "Lorg/spongepowered/asm/mixin/Mixin;";
    private static final String INJECT = "Lorg/spongepowered/asm/mixin/injection/Inject;";
    private static final String ACCESSOR = "Lorg/spongepowered/asm/mixin/gen/Accessor;";
    private static final List<String> MIXIN_PACKAGES =
        List.of("Lorg/spongepowered/asm/mixin/", "Lcom/llamalad7/mixinextras/");
    private static final List<String> PLAIN_POINTS = List.of("HEAD", "RETURN", "TAIL");
    // The @Inject and @At values this test reads or that name no target; any other (slice,
    // ordinal, locals, shift, ...) fails it until the test reads it.
    private static final List<String> INJECT_KEYS = List.of("method", "at", "cancellable");
    private static final List<String> AT_KEYS = List.of("value", "target", "shift");
    private static final List<String> ACCESSOR_KEYS = List.of("value");
    // The adapters whose calls into the renderer and the shader loader are read, and those owners.
    private static final List<Class<?>> ADAPTERS = List.of(RendererAdapter.class, IrisAdapter.class,
        CaptureAdapter.class, Selftest.class);
    private static final List<String> FRAGILE = List.of("net/caffeinemc/", "net/irisshaders/");
    private static final List<ZipFile> JARS = new ArrayList<>();

    @BeforeAll
    static void openPinnedJars() {
        for (JsonElement element : Pinned.inputs().getAsJsonArray("targetJars")) {
            JsonObject jar = element.getAsJsonObject();
            JARS.add(Pinned.open(Path.of(jar.get("path").getAsString()),
                jar.get("algorithm").getAsString(), jar.get("digest").getAsString()));
        }
    }

    @AfterAll
    static void closePinnedJars() throws IOException {
        for (ZipFile jar : JARS) {
            jar.close();
        }
    }

    @Test
    void everyTargetIsInThePinnedJars() {
        JsonObject config = resourceJson("optilux-helper.mixins.json");
        String pkg = config.get("package").getAsString();
        List<String> mixins = new ArrayList<>();
        for (String side : List.of("mixins", "client", "server")) {
            if (config.has(side)) {
                config.getAsJsonArray(side).forEach(name -> mixins.add(name.getAsString()));
            }
        }
        assertTrue(!mixins.isEmpty(), "the config lists no mixin");
        List<String> problems = new ArrayList<>();
        List<String> checked = new ArrayList<>();
        for (String name : mixins) {
            ClassNode mixin = read(ownClass(pkg + "." + name));
            List<ClassNode> targets = new ArrayList<>();
            for (String targetName : targets(mixin, problems)) {
                ClassNode target = pinnedClass(targetName);
                if (target == null) {
                    problems.add(name + ": target class " + targetName + " is in no pinned jar");
                } else {
                    targets.add(target);
                }
            }
            for (var field : mixin.fields) {
                unread(name + "." + field.name, all(field.visibleAnnotations,
                    field.invisibleAnnotations), problems);
            }
            for (MethodNode method : mixin.methods) {
                String where = name + "." + method.name;
                List<AnnotationNode> others = new ArrayList<>();
                for (AnnotationNode annotation : all(method)) {
                    if (annotation.desc.equals(INJECT)) {
                        for (ClassNode target : targets) {
                            checkInject(where, annotation, target, problems, checked);
                        }
                    } else if (annotation.desc.equals(ACCESSOR)) {
                        for (ClassNode target : targets) {
                            checkAccessor(where, annotation, method, target, problems, checked);
                        }
                    } else {
                        others.add(annotation);
                    }
                }
                unread(where, others, problems);
            }
        }
        assertEquals(List.of(), problems);
        String rsm = "net/caffeinemc/mods/sodium/client/render/chunk/RenderSectionManager.";
        assertEquals(List.of(
            "GameRendererMixin.optilux$frameHead: "
                + "net/minecraft/client/renderer/GameRenderer.render()V HEAD",
            "GameRendererMixin.optilux$capturePoint: net/minecraft/client/renderer/GameRenderer."
                + "render()V INVOKE Lnet/minecraft/client/renderer/GameRenderer;applyPostEffects()V"
                + " shift AFTER",
            "IrisMixin.optilux$loadFailed: net/irisshaders/iris/Iris."
                + "handleException(Ljava/lang/Exception;)V HEAD",
            "KeyboardHandlerMixin.optilux$blockKey: net/minecraft/client/KeyboardHandler."
                + "keyPress(JILnet/minecraft/client/input/KeyEvent;)V HEAD",
            "KeyboardHandlerMixin.optilux$blockText: net/minecraft/client/KeyboardHandler."
                + "textInput(JLjava/lang/String;)V HEAD",
            "KeyboardHandlerMixin.optilux$blockEditing: net/minecraft/client/KeyboardHandler."
                + "textEditing(JLnet/minecraft/client/input/PreeditEvent;)V HEAD",
            "MinecraftMixin.optilux$refusePause: net/minecraft/client/Minecraft.pauseGame(Z)V HEAD",
            "MinecraftMixin.optilux$swapped: net/minecraft/client/Minecraft.renderFrame(Z)V INVOKE"
                + " Lcom/mojang/renderpearl/api/device/GpuSurface;present()V shift AFTER",
            "MouseHandlerMixin.optilux$blockMove: net/minecraft/client/MouseHandler.onMove(JDDDD)V HEAD",
            "MouseHandlerMixin.optilux$blockButton: net/minecraft/client/MouseHandler."
                + "onButton(JLnet/minecraft/client/input/MouseButtonInfo;I)V HEAD",
            "MouseHandlerMixin.optilux$blockScroll: net/minecraft/client/MouseHandler.onScroll(JDD)V HEAD",
            "RenderRegionAccessor.optilux$sections: net/caffeinemc/mods/sodium/client/render/chunk/"
                + "region/RenderRegion.sections [Lnet/caffeinemc/mods/sodium/client/render/chunk/"
                + "RenderSection;",
            "RenderSectionAccessor.optilux$runningJobs: net/caffeinemc/mods/sodium/client/render/"
                + "chunk/RenderSection.runningJobs Ljava/util/List;",
            "RenderSectionManagerAccessor.optilux$buildResults: " + rsm
                + "buildResults Ljava/util/concurrent/ConcurrentLinkedDeque;",
            "RenderSectionManagerAccessor.optilux$taskLists: " + rsm
                + "taskLists Lnet/caffeinemc/mods/sodium/client/render/chunk/lists/DeferredTaskList;",
            "RenderSectionManagerAccessor.optilux$pendingTask: " + rsm
                + "pendingTask Lnet/caffeinemc/mods/sodium/client/render/chunk/async/CullTask;",
            "RenderSectionManagerAccessor.optilux$needsGraphUpdate: " + rsm + "needsGraphUpdate Z",
            "RenderSectionManagerAccessor.optilux$thisFrameBlockingTasks: " + rsm
                + "thisFrameBlockingTasks I",
            "RenderSectionManagerAccessor.optilux$nextFrameBlockingTasks: " + rsm
                + "nextFrameBlockingTasks I",
            "RenderSectionManagerAccessor.optilux$deferredTasks: " + rsm + "deferredTasks I",
            "SodiumWorldRendererAccessor.optilux$renderSectionManager: net/caffeinemc/mods/sodium/"
                + "client/render/SodiumWorldRenderer.renderSectionManager Lnet/caffeinemc/mods/"
                + "sodium/client/render/chunk/RenderSectionManager;"),
            checked);
    }

    private static void checkInject(String where, AnnotationNode inject, ClassNode target,
        List<String> problems, List<String> checked) {
        @SuppressWarnings("unchecked")
        List<String> selectors = (List<String>) value(inject, "method");
        @SuppressWarnings("unchecked")
        List<AnnotationNode> points = (List<AnnotationNode>) value(inject, "at");
        unreadKeys(where + " @Inject", inject, INJECT_KEYS, problems);
        for (AnnotationNode at : points) {
            unreadKeys(where + " @At", at, AT_KEYS, problems);
        }
        for (String selector : selectors) {
            int paren = selector.indexOf('(');
            if (paren < 0) {
                problems.add(where + ": selector " + selector + " has no descriptor");
                continue;
            }
            MethodNode method = method(target, selector.substring(0, paren),
                selector.substring(paren));
            if (method == null) {
                problems.add(where + ": " + target.name + "." + selector + " is not in the jar");
                continue;
            }
            for (AnnotationNode at : points) {
                String point = (String) value(at, "value");
                String seen = target.name + "." + selector + " " + point;
                String shifted = value(at, "shift") instanceof String[] shift ? " shift " + shift[1] : "";
                if (PLAIN_POINTS.contains(point)) {
                    checked.add(where + ": " + seen + shifted);
                } else if (point.equals("INVOKE")) {
                    String call = (String) value(at, "target");
                    if (invokes(method, call)) {
                        checked.add(where + ": " + seen + " " + call + shifted);
                    } else {
                        problems.add(where + ": " + seen + ": no call to " + call);
                    }
                } else {
                    problems.add(where + ": injection point " + point + " is not read by this test");
                }
            }
        }
    }

    /** An accessor's field: in the target by the annotation's name, of the method's return type. */
    private static void checkAccessor(String where, AnnotationNode accessor, MethodNode method,
        ClassNode target, List<String> problems, List<String> checked) {
        unreadKeys(where + " @Accessor", accessor, ACCESSOR_KEYS, problems);
        String name = (String) value(accessor, "value");
        if (name == null) {
            problems.add(where + ": @Accessor names no field");
            return;
        }
        String desc = Type.getReturnType(method.desc).getDescriptor();
        for (FieldNode field : target.fields) {
            if (field.name.equals(name) && field.desc.equals(desc)) {
                checked.add(where + ": " + target.name + "." + name + " " + desc);
                return;
            }
        }
        problems.add(where + ": " + target.name + " has no field " + name + " " + desc);
    }

    @Test
    void everyAdapterReferenceIntoSodiumAndIrisIsInThePinnedJars() {
        TreeSet<String> found = new TreeSet<>();
        List<String> problems = new ArrayList<>();
        for (Class<?> adapter : ADAPTERS) {
            ClassNode node = read(ownClass(adapter.getName()));
            for (MethodNode method : node.methods) {
                for (AbstractInsnNode insn : method.instructions) {
                    String owner;
                    String member;
                    boolean isField;
                    if (insn instanceof MethodInsnNode call) {
                        owner = call.owner;
                        member = call.name + call.desc;
                        isField = false;
                    } else if (insn instanceof FieldInsnNode field) {
                        owner = field.owner;
                        member = field.name + " " + field.desc;
                        isField = true;
                    } else {
                        continue;
                    }
                    if (FRAGILE.stream().noneMatch(owner::startsWith)) {
                        continue;
                    }
                    if (found.add(owner + "." + member) && !resolves(owner, member, isField)) {
                        problems.add(adapter.getSimpleName() + ": " + owner + "." + member
                            + " is not in the pinned jars");
                    }
                }
            }
        }
        assertEquals(List.of(), problems);
        assertEquals(EXPECTED_REFERENCES, List.copyOf(found));
    }

    /** Sodium's and Iris's surface the adapters use (docs/platform.md#mod-adapter-surface). */
    private static final List<String> EXPECTED_REFERENCES = List.of(
        "net/caffeinemc/mods/sodium/client/render/SodiumWorldRenderer.instanceNullable()"
            + "Lnet/caffeinemc/mods/sodium/client/render/SodiumWorldRenderer;",
        "net/caffeinemc/mods/sodium/client/render/SodiumWorldRenderer.isTerrainRenderComplete()Z",
        "net/caffeinemc/mods/sodium/client/render/chunk/RenderSectionManager.getBuilder()"
            + "Lnet/caffeinemc/mods/sodium/client/render/chunk/compile/executor/ChunkBuilder;",
        "net/caffeinemc/mods/sodium/client/render/chunk/RenderSectionManager.getTotalSections()I",
        "net/caffeinemc/mods/sodium/client/render/chunk/RenderSectionManager.regions "
            + "Lnet/caffeinemc/mods/sodium/client/render/chunk/region/RenderRegionManager;",
        "net/caffeinemc/mods/sodium/client/render/chunk/compile/executor/ChunkBuilder."
            + "getBusyThreadCount()I",
        "net/caffeinemc/mods/sodium/client/render/chunk/compile/executor/ChunkBuilder."
            + "getScheduledJobCount()I",
        "net/caffeinemc/mods/sodium/client/render/chunk/compile/executor/ChunkBuilder."
            + "isBuildQueueEmpty()Z",
        "net/caffeinemc/mods/sodium/client/render/chunk/lists/DeferredTaskList.size()I",
        "net/caffeinemc/mods/sodium/client/render/chunk/region/RenderRegionManager."
            + "getLoadedRegions()Ljava/util/Collection;",
        "net/irisshaders/iris/Iris.getCurrentPack()Ljava/util/Optional;",
        "net/irisshaders/iris/Iris.getCurrentPackName()Ljava/lang/String;",
        "net/irisshaders/iris/Iris.getIrisConfig()Lnet/irisshaders/iris/config/IrisConfig;",
        "net/irisshaders/iris/Iris.getPipelineManager()"
            + "Lnet/irisshaders/iris/pipeline/PipelineManager;",
        "net/irisshaders/iris/Iris.isFallback()Z",
        "net/irisshaders/iris/Iris.reload()V",
        "net/irisshaders/iris/config/IrisConfig.getShaderPackName()Ljava/util/Optional;",
        "net/irisshaders/iris/pipeline/PipelineManager.getPipelineNullable()"
            + "Lnet/irisshaders/iris/pipeline/WorldRenderingPipeline;",
        "net/irisshaders/iris/pipeline/WorldRenderingPipeline.getClass()Ljava/lang/Class;",
        "net/irisshaders/iris/shaderpack/ShaderPack.getShaderPackOptions()"
            + "Lnet/irisshaders/iris/shaderpack/option/ShaderPackOptions;",
        "net/irisshaders/iris/shaderpack/option/OptionSet.getBooleanOptions()"
            + "Lcom/google/common/collect/ImmutableMap;",
        "net/irisshaders/iris/shaderpack/option/OptionSet.getStringOptions()"
            + "Lcom/google/common/collect/ImmutableMap;",
        "net/irisshaders/iris/shaderpack/option/ShaderPackOptions.getOptionValues()"
            + "Lnet/irisshaders/iris/shaderpack/option/values/OptionValues;",
        "net/irisshaders/iris/shaderpack/option/values/OptionValues.getBooleanValueOrDefault"
            + "(Ljava/lang/String;)Z",
        "net/irisshaders/iris/shaderpack/option/values/OptionValues.getOptionSet()"
            + "Lnet/irisshaders/iris/shaderpack/option/OptionSet;",
        "net/irisshaders/iris/shaderpack/option/values/OptionValues.getStringValueOrDefault"
            + "(Ljava/lang/String;)Ljava/lang/String;",
        "net/irisshaders/iris/uniforms/SystemTimeUniforms$FrameCounter.getAsInt()I",
        "net/irisshaders/iris/uniforms/SystemTimeUniforms.COUNTER "
            + "Lnet/irisshaders/iris/uniforms/SystemTimeUniforms$FrameCounter;");

    /** Whether the member is declared by the owner or by a class or interface above it. */
    private static boolean resolves(String owner, String member, boolean isField) {
        ClassNode node = anyClass(owner);
        if (node == null) {
            return false;
        }
        if (isField) {
            for (FieldNode field : node.fields) {
                if (member.equals(field.name + " " + field.desc)) {
                    return true;
                }
            }
        } else {
            for (MethodNode method : node.methods) {
                if (member.equals(method.name + method.desc)) {
                    return true;
                }
            }
        }
        List<String> above = new ArrayList<>(node.interfaces);
        if (node.superName != null) {
            above.add(node.superName);
        }
        for (String parent : above) {
            if (resolves(parent, member, isField)) {
                return true;
            }
        }
        return false;
    }

    /** A class from the pinned jars, else from the test classpath (a library parent, the JDK). */
    private static ClassNode anyClass(String internalName) {
        ClassNode pinned = pinnedClass(internalName);
        if (pinned != null) {
            return pinned;
        }
        try (InputStream stream = ClassLoader.getSystemResourceAsStream(internalName + ".class")) {
            return stream == null ? null : read(stream.readAllBytes());
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    /** Whether a method calls {@code Lowner;name(desc)}. */
    private static boolean invokes(MethodNode method, String call) {
        int semicolon = call.indexOf(';');
        int paren = call.indexOf('(');
        if (!call.startsWith("L") || semicolon < 0 || paren < semicolon) {
            return false;
        }
        String owner = call.substring(1, semicolon);
        String name = call.substring(semicolon + 1, paren);
        String desc = call.substring(paren);
        for (AbstractInsnNode insn : method.instructions) {
            if (insn instanceof MethodInsnNode invoke && invoke.owner.equals(owner)
                && invoke.name.equals(name) && invoke.desc.equals(desc)) {
                return true;
            }
        }
        return false;
    }

    private static List<String> targets(ClassNode mixin, List<String> problems) {
        List<String> found = new ArrayList<>();
        for (AnnotationNode annotation : all(mixin.visibleAnnotations, mixin.invisibleAnnotations)) {
            if (!annotation.desc.equals(MIXIN)) {
                continue;
            }
            Object types = value(annotation, "value");
            if (types instanceof List<?> list) {
                list.forEach(type -> found.add(((Type) type).getInternalName()));
            }
            Object names = value(annotation, "targets");
            if (names instanceof List<?> list) {
                list.forEach(target -> found.add(((String) target).replace('.', '/')));
            }
        }
        if (found.isEmpty()) {
            problems.add(mixin.name + ": no @Mixin target");
        }
        return found;
    }

    /** A mixin annotation this test does not read is a problem: extend the test first. */
    private static void unread(String where, List<AnnotationNode> annotations,
        List<String> problems) {
        for (AnnotationNode annotation : annotations) {
            if (MIXIN_PACKAGES.stream().anyMatch(annotation.desc::startsWith)) {
                problems.add(where + ": " + annotation.desc + " is not read by this test");
            }
        }
    }

    private static void unreadKeys(String where, AnnotationNode annotation, List<String> read,
        List<String> problems) {
        if (annotation.values == null) {
            return;
        }
        for (int i = 0; i < annotation.values.size(); i += 2) {
            String key = (String) annotation.values.get(i);
            if (!read.contains(key)) {
                problems.add(where + ": " + key + " is not read by this test");
            }
        }
    }

    private static MethodNode method(ClassNode target, String name, String desc) {
        for (MethodNode method : target.methods) {
            if (method.name.equals(name) && method.desc.equals(desc)) {
                return method;
            }
        }
        return null;
    }

    private static ClassNode pinnedClass(String internalName) {
        for (ZipFile jar : JARS) {
            byte[] bytes = Pinned.bytes(jar, internalName + ".class");
            if (bytes != null) {
                return read(bytes);
            }
        }
        return null;
    }

    private static List<AnnotationNode> all(MethodNode method) {
        return all(method.visibleAnnotations, method.invisibleAnnotations);
    }

    @SafeVarargs
    private static List<AnnotationNode> all(List<AnnotationNode>... lists) {
        List<AnnotationNode> found = new ArrayList<>();
        for (List<AnnotationNode> list : lists) {
            if (list != null) {
                found.addAll(list);
            }
        }
        return found;
    }

    private static Object value(AnnotationNode annotation, String key) {
        Map<String, Object> values = new HashMap<>();
        if (annotation.values != null) {
            for (int i = 0; i + 1 < annotation.values.size(); i += 2) {
                values.put((String) annotation.values.get(i), annotation.values.get(i + 1));
            }
        }
        return values.get(key);
    }

    private static byte[] ownClass(String className) {
        return resource(className.replace('.', '/') + ".class");
    }

    private static JsonObject resourceJson(String name) {
        return com.google.gson.JsonParser.parseString(new String(resource(name),
            java.nio.charset.StandardCharsets.UTF_8)).getAsJsonObject();
    }

    private static byte[] resource(String name) {
        try (InputStream stream = MixinTargetTest.class.getClassLoader().getResourceAsStream(name)) {
            if (stream == null) {
                throw new IllegalStateException(name + " is not on the test classpath");
            }
            return stream.readAllBytes();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    private static ClassNode read(byte[] bytes) {
        ClassNode node = new ClassNode();
        new ClassReader(bytes).accept(node, 0);
        return node;
    }
}
