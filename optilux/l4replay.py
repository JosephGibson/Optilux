"""L4's replay script (docs/offline.md#levels, plans/m4.md M4.P05), run by `qrenderdoc.exe --python`
in RenderDoc 1.46's bundled Python 3.8, the one Python its renderdoc module loads in (plans/m4.md
P7): one capture per start, the job a JSON file named by OPTILUX_L4_JOB (optilux/l4.py writes it).
It never imports optilux; its syntax and library calls are Python 3.8's.

It opens the capture and writes <out>/replay.json:
- `events`: each action FetchCounters gives an EventGPUDuration (ms): its event id, name, kind, the
  debug groups around it, outermost first (every PushMarker: in Iris's captures its GLDebug groups,
  setPhase's and its passes'), and for a draw the program the last glUseProgram before it bound,
  by its label (Iris labels its programs; RenderDoc names an unlabelled one "Program <id>"). The
  walk reads the program and the draw framebuffer from the capture's chunks, both seeded from the
  first draw's pipeline state; at each draw after either changes, RenderDoc's state must agree;
- with `outputs`, per pass (a program's draws into one framebuffer, named by its label, then
  "<label> #2" and on in the order of their first draws) its last draw's colour targets (the draw
  buffers) and depth target read back after it into <out>/targets/<n>.bin, with their facts;
- with `ab`, per replacement (a program's stage and a candidate source file) the frame fetched
  `fetches` times each with the original, a no-op replacement (the capture's own source rebuilt),
  a control (a second no-op build) and the candidate in place: per fetch the frame's and the
  program's draws' summed durations; replacements are always removed; a replacement that does not
  build, or a label naming several programs, is an error of its entry alone.
Progress goes to <out>/stage.json. The process ends itself once replay.json is written, whatever
happened: qrenderdoc's window would otherwise stay open.
"""

import hashlib
import json
import os
import re
import time
import traceback

JOB_ENV = "OPTILUX_L4_JOB"
REPLAY = "replay.json"
STAGE = "stage.json"
TARGETS = "targets"
# RenderDoc's name for a program no glObjectLabel named.
UNLABELLED = re.compile(r"^Program \d+$")
# ActionFlags, in this order, give an action its kind; a draw's program is the bound one.
KINDS = (
    ("Drawcall", "draw"),
    ("Dispatch", "dispatch"),
    ("Clear", "clear"),
    ("Copy", "copy"),
    ("Resolve", "resolve"),
    ("GenMips", "mips"),
    ("Present", "present"),
)
PROGRAMMED = ("draw", "dispatch")
STAGES = {"vert": "Vertex", "frag": "Fragment"}
USE_PROGRAM = "glUseProgram"
BIND_FRAMEBUFFER = "glBindFramebuffer"
# glBindFramebuffer's targets that set the draw framebuffer (its target serializes as an enum).
DRAW_TARGETS = ("GL_FRAMEBUFFER", "GL_DRAW_FRAMEBUFFER")


def stage(out, name):
    with open(os.path.join(out, STAGE), "w", encoding="utf-8") as handle:
        json.dump({"stage": name, "time": time.time()}, handle)


def kind_of(rd, flags):
    for flag, kind in KINDS:
        if flags & getattr(rd.ActionFlags, flag):
            return kind
    return "other"


def succeeded(rd, status):
    return getattr(status, "code", status) == rd.ResultCode.Succeeded


def bound_at(controller, event):
    """RenderDoc's own program and draw framebuffer at an event, as resource ids' text."""
    controller.SetFrameEvent(event, False)
    state = controller.GetGLPipelineState()
    return str(state.vertexShader.programResourceId), str(state.framebuffer.drawFBO.resourceId)


def first_draw(rd, actions):
    for action in actions:
        if action.flags & rd.ActionFlags.Drawcall:
            return action.eventId
        found = first_draw(rd, action.children)
        if found is not None:
            return found
    return None


def walk(rd, controller):
    """Every action in event order: its event id, name, kind, the groups around it (a PushMarker
    action's name, outermost first), and the program and draw framebuffer bound at it (resource
    ids' text, None for no program), read from the glUseProgram and glBindFramebuffer chunks."""
    structured = controller.GetStructuredFile()
    null = str(rd.ResourceId.Null())
    roots = controller.GetRootActions()
    first = first_draw(rd, roots)
    # What the frame inherits from before its first chunk; a local's annotation is never
    # evaluated, so Python 3.8 runs it.
    bound: list = list(bound_at(controller, first)) if first is not None else [None, None]
    found = []

    def visit(actions, groups):
        for action in actions:
            for event in action.events:
                chunk = structured.chunks[event.chunkIndex]
                if chunk.name == USE_PROGRAM:
                    program = str(chunk.GetChild(0).AsResourceId())
                    bound[0] = None if program == null else program
                elif chunk.name == BIND_FRAMEBUFFER:
                    if chunk.GetChild(0).AsString() in DRAW_TARGETS:
                        bound[1] = str(chunk.GetChild(1).AsResourceId())
            name = action.GetName(structured)
            found.append(
                {
                    "event": action.eventId,
                    "name": name,
                    "kind": kind_of(rd, action.flags),
                    "groups": list(groups),
                    "programId": bound[0],
                    "fbo": bound[1],
                }
            )
            if action.children:
                marker = action.flags & rd.ActionFlags.PushMarker
                visit(action.children, [*groups, name] if marker else groups)

    visit(roots, [])
    return found


def spot_check(rd, controller, actions):
    """RenderDoc's pipeline state at each draw after the walk's program or draw framebuffer
    changed, against the walk's; the count checked. RuntimeError at the first disagreement."""
    checked = 0
    last = ("none", "none")
    for action in actions:
        here = (action["programId"], action["fbo"])
        if action["kind"] != "draw" or here == last:
            continue
        last = here
        state = bound_at(controller, action["event"])
        if state != (str(here[0]), str(here[1])):
            raise RuntimeError(
                f"event {action['event']}: the walk read program {here[0]} into framebuffer "
                f"{here[1]}, RenderDoc's state binds {state[0]} into {state[1]}"
            )
        checked += 1
    return checked


def durations(rd, controller):
    """Each event's EventGPUDuration in ms."""
    counter = rd.GPUCounter.EventGPUDuration
    if counter not in controller.EnumerateCounters():
        raise RuntimeError("this replay offers no EventGPUDuration counter")
    return {r.eventId: r.value.d * 1000.0 for r in controller.FetchCounters([counter])}


def fmt(texture):
    form = texture.format
    return {
        "name": form.Name(),
        "type": str(form.type).rsplit(".", 1)[-1],
        "compType": str(form.compType).rsplit(".", 1)[-1],
        "compCount": form.compCount,
        "compByteWidth": form.compByteWidth,
    }


def outputs(rd, controller, actions, names, out):
    """Per program, its last draw's draw-buffer colour targets and depth target read back after it
    into out/targets/; the passes in the order of their last draws with each target's facts."""
    first, last = {}, {}
    for action in actions:
        if action["kind"] == "draw" and action["programId"] is not None:
            key = (action["programId"], action["fbo"])
            first.setdefault(key, action["event"])
            last[key] = action
    # A program drawing into several framebuffers, or two programs of one label, give one pass
    # each: the label, then "<label> #2" and on, by first draw.
    titles, seen = {}, {}
    for key in sorted(first, key=lambda k: first[k]):
        label = names.get(key[0], key[0])
        seen[label] = seen.get(label, 0) + 1
        titles[key] = label if seen[label] == 1 else f"{label} #{seen[label]}"
    textures = {str(t.resourceId): t for t in controller.GetTextures()}
    folder = os.path.join(out, TARGETS)
    os.makedirs(folder, exist_ok=True)
    null = rd.ResourceId.Null()
    passes = []
    written = 0
    for key, action in sorted(last.items(), key=lambda item: item[1]["event"]):
        controller.SetFrameEvent(action["event"], True)
        fbo = controller.GetGLPipelineState().framebuffer.drawFBO
        colours = list(fbo.colorAttachments)
        attached = [
            (f"color{index}", colours[index])
            for index in fbo.drawBuffers
            if 0 <= index < len(colours) and colours[index].resource != null
        ]
        if fbo.depthAttachment.resource != null:
            attached.append(("depth", fbo.depthAttachment))
        targets = []
        for slot, attachment in attached:
            texture = textures[str(attachment.resource)]
            mip = attachment.firstMip  # RenderDoc 1.46's Descriptor
            data = controller.GetTextureData(
                attachment.resource, rd.Subresource(mip, attachment.firstSlice, 0)
            )
            written += 1
            file = f"{written}.bin"
            with open(os.path.join(folder, file), "wb") as handle:
                handle.write(bytes(data))
            targets.append(
                {
                    "slot": slot,
                    "resource": str(attachment.resource),
                    "texture": names.get(str(attachment.resource), ""),
                    "width": max(1, texture.width >> mip),
                    "height": max(1, texture.height >> mip),
                    "mip": mip,
                    "slice": attachment.firstSlice,
                    "format": fmt(texture),
                    "bytes": len(data),
                    "file": TARGETS + "/" + file,
                }
            )
        passes.append(
            {
                "program": titles[key],
                "fbo": key[1],
                "event": action["event"],
                "groups": action["groups"],
                "targets": targets,
            }
        )
    return passes


def ab(rd, controller, actions, names, job, out):
    """Replay A/B: per replacement, the frame fetched with the original, the no-op, the control
    and the candidate in place, `fetches` rounds; per fetch the frame's and the program's summed
    durations (ms). A replacement whose program is not drawn is listed, not replayed; one whose
    label names several programs, or that does not build, carries its error."""
    fetches = int(job["fetches"])
    by_label = {}
    for action in actions:
        if action["kind"] == "draw" and action["programId"] is not None:
            label = names.get(action["programId"], "")
            by_label.setdefault(label, {}).setdefault(action["programId"], []).append(
                action["event"]
            )
    null = rd.ResourceId.Null()
    found = []
    for item in job["replace"]:
        entry = {"program": item["program"], "stage": item["stage"], "candidate": item["file"]}
        found.append(entry)
        programs = by_label.get(item["program"])
        if not programs:
            entry["notDrawn"] = True
            continue
        if len(programs) > 1:
            entry["error"] = f"the label names {len(programs)} programs, so none is replaced"
            continue
        (events,) = programs.values()
        controller.SetFrameEvent(events[0], True)
        state = controller.GetGLPipelineState()
        shader = state.fragmentShader if item["stage"] == "frag" else state.vertexShader
        reflection = shader.reflection
        kind = getattr(rd.ShaderStage, STAGES[item["stage"]])
        with open(item["file"], "rb") as handle:
            candidate = handle.read()
        own = bytes(reflection.rawBytes)
        # The capture's own source beside the replay: a candidate is written from it.
        entry["own"] = f"ab-{item['program']}.{item['stage']}"
        entry["ownSha256"] = hashlib.sha256(own).hexdigest()
        with open(os.path.join(out, entry["own"]), "wb") as handle:
            handle.write(own)
        built = []
        try:
            for role, text in (("noop", own), ("control", own), ("candidate", candidate)):
                replacement, errors = controller.BuildTargetShader(
                    reflection.entryPoint,
                    reflection.encoding,
                    text,
                    rd.ShaderCompileFlags(),
                    kind,
                )
                if replacement == null:
                    entry["error"] = f"the {role} replacement did not build: {str(errors)[:600]}"
                    break
                built.append((role, replacement))
            if "error" in entry:
                continue
            rounds = {"original": [], "noop": [], "control": [], "candidate": []}
            for _ in range(fetches):
                for role in ("original", "noop", "control", "candidate"):
                    replacement = dict(built).get(role)
                    if replacement is not None:
                        controller.ReplaceResource(shader.shaderResourceId, replacement)
                    try:
                        times = durations(rd, controller)
                    finally:
                        if replacement is not None:
                            controller.RemoveReplacement(shader.shaderResourceId)
                    rounds[role].append(
                        {
                            "frameMs": sum(times.values()),
                            "programMs": sum(times.get(e, 0.0) for e in events),
                        }
                    )
            entry["draws"] = len(events)
            entry["rounds"] = rounds
        finally:
            controller.RemoveReplacement(shader.shaderResourceId)
            for _, replacement in built:
                controller.FreeTargetResource(replacement)
    return found


def replay(rd, job, out):
    capture = rd.OpenCaptureFile()
    status = capture.OpenFile(job["capture"], "", None)
    if not succeeded(rd, status):
        capture.Shutdown()
        raise RuntimeError(f"OpenFile: {status}")
    status, controller = capture.OpenCapture(rd.ReplayOptions(), None)
    if not succeeded(rd, status):
        capture.Shutdown()
        raise RuntimeError(f"OpenCapture: {status}")
    try:
        stage(out, "opened")
        names = {str(r.resourceId): r.name for r in controller.GetResources()}
        actions = walk(rd, controller)
        checked = spot_check(rd, controller, actions)
        stage(out, "walked")
        times = durations(rd, controller)
        events = []
        for action in actions:
            if action["event"] in times:
                # A clear, copy or blit runs no program, whichever one is bound.
                program = action["programId"] if action["kind"] in PROGRAMMED else None
                events.append(
                    {
                        "event": action["event"],
                        "name": action["name"],
                        "kind": action["kind"],
                        "groups": action["groups"],
                        "program": names.get(program, program) if program else None,
                        "ms": times[action["event"]],
                    }
                )
        found = {
            "api": str(controller.GetAPIProperties().pipelineType).rsplit(".", 1)[-1],
            "actions": len(actions),
            "spotChecked": checked,
            "events": events,
        }
        if job.get("outputs"):
            stage(out, "outputs")
            found["outputs"] = outputs(rd, controller, actions, names, out)
        if job.get("ab"):
            stage(out, "ab")
            found["ab"] = ab(rd, controller, actions, names, job["ab"], out)
        return found
    finally:
        controller.Shutdown()
        capture.Shutdown()


def main():
    out = None
    result: dict = {"ok": False}
    try:
        with open(os.environ[JOB_ENV], encoding="utf-8") as handle:
            job = json.load(handle)
        out = job["out"]
        stage(out, "started")
        import renderdoc as rd  # type: ignore[import-not-found] # qrenderdoc's own module

        result["renderdoc"] = rd.GetVersionString()
        result.update(replay(rd, job, out))
        result["ok"] = True
    except BaseException:  # noqa: BLE001 every failure goes into replay.json for l4.py
        result["error"] = traceback.format_exc()
    finally:
        if out is not None:
            # Whole or absent: l4.py reads it once it exists.
            partial = os.path.join(out, REPLAY + ".part")
            with open(partial, "w", encoding="utf-8") as handle:
                json.dump(result, handle)
            os.replace(partial, os.path.join(out, REPLAY))
            stage(out, "finished")
    os._exit(0)


if __name__ == "__main__":
    main()
