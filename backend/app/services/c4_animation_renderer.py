"""C4 Animation Package Renderer — deterministic, self-contained HTML packages.

Turns a validated AnimationSpecification into a single HTML string (stored in
``topic_animation_assets.package_content``) that the player embeds in a sandboxed
iframe. The package re-draws the animation scene graph as an inline SVG whose
nodes/edges are progressively revealed, highlighted, traversed or transformed by
a tiny deterministic controller script.

Design rules (enforced by construction):
* Purely deterministic — identical specifications render byte-identical packages.
* No external dependencies — the package is fully self-contained (SVG + CSS + JS).
* No randomness — positions and all timing come from the specification.
* HTML-escaped user content — node/edge labels never break out of markup or JS.
"""

from __future__ import annotations

import html as html_lib
import json
from typing import Any

from app.core.logging import get_logger
from app.schemas.c4_animation_intelligence import (
    AnimationScene,
    AnimationSpecification,
    AnimationStep,
)
from app.services.c4_animation_spec_generator import build_animation_explanation

logger = get_logger(__name__)

_COLS = 6
_CELL_W = 170
_CELL_H = 150
_MARGIN = 30
_TEXT_LINE_LIMIT = 42

# Palette borrowed from the C3 renderer so packages feel native to the player.
_BG = "#0B1626"
_SURFACE = "#0E1A2B"
_PRIMARY = "#F2A623"
_SECONDARY = "#1D9E75"
_TEXT = "#F4EFE4"
_MUTED = "rgba(244,239,228,0.55)"
_BORDER = "rgba(244,239,228,0.14)"


def _esc(text: Any) -> str:
    return html_lib.escape(str(text))


def _wrap(text: str, limit: int = _TEXT_LINE_LIMIT) -> str:
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= limit:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "&#10;".join(lines[:5])


def _step_payload(step: AnimationStep) -> dict[str, Any]:
    return {
        "kind": step.kind.value,
        "nodeIds": step.node_ids,
        "edgeIds": step.edge_ids,
        "caption": step.caption,
        "role": step.educational_role,
        "durationMs": step.duration_ms,
    }


def _scene_payload(scene: AnimationScene) -> dict[str, Any]:
    return {
        "title": scene.title,
        "purpose": scene.purpose,
        "caption": scene.caption,
        "steps": [_step_payload(s) for s in scene.steps],
    }


def _layout(spec: AnimationSpecification) -> tuple[dict[str, tuple[float, float]], int, int]:
    """Deterministic grid layout for the animation scene graph."""
    layout: dict[str, tuple[float, float]] = {}
    if spec.animation_type.value == "comparison_reveal":
        for node in spec.nodes:
            if node.id == "col_b":
                layout[node.id] = (_MARGIN + _COLS * _CELL_W - 200, _MARGIN + 120)
            else:
                layout[node.id] = (_MARGIN + 40, _MARGIN + 120)
        return layout, _MARGIN + _COLS * _CELL_W, _MARGIN + 310
    for i, node in enumerate(spec.nodes):
        col = i % _COLS
        row = i // _COLS
        layout[node.id] = (_MARGIN + col * _CELL_W, _MARGIN + row * _CELL_H)
    rows = (len(spec.nodes) - 1) // _COLS + 1 if spec.nodes else 1
    return layout, _MARGIN + _COLS * _CELL_W, _MARGIN + rows * _CELL_H


def _render_edges(spec: AnimationSpecification, layout: dict[str, tuple[float, float]]) -> str:
    parts: list[str] = ['<g id="c4-edges">']
    for edge in spec.edges:
        src = layout.get(edge.source_id)
        dst = layout.get(edge.target_id)
        if not src or not dst:
            continue
        x1, y1 = src[0] + _CELL_W / 2, src[1] + 58
        x2, y2 = dst[0] + _CELL_W / 2, dst[1] + 58
        parts.append(
            f'<line class="c4-edge" data-id="{_esc(edge.id)}" '
            f'x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}"/>'
        )
        parts.append(
            f'<line class="c4-edge-arrow" data-id="arr-{_esc(edge.id)}" '
            f'x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}"/>'
        )
    parts.append("</g>")
    return "".join(parts)


def _render_nodes(spec: AnimationSpecification, layout: dict[str, tuple[float, float]]) -> str:
    parts: list[str] = ['<g id="c4-nodes">']
    for node in spec.nodes:
        x, y = layout[node.id]
        label = _esc(_wrap(node.label, 14)).replace("&amp;#10;", "&#10;")
        desc = (
            _esc(_wrap(node.description, 20)).replace("&amp;#10;", "&#10;")
            if node.description
            else ""
        )
        parts.append(
            f'<g class="c4-node" data-id="{_esc(node.id)}" opacity="0">'
            f'<rect x="{x:.0f}" y="{y:.0f}" rx="12" ry="12" width="{_CELL_W - 8}" '
            f'height="{_CELL_H - 20}"/>'
            f'<text x="{x + (_CELL_W - 8) / 2:.0f}" y="{y + 34:.0f}" '
            f'class="c4-node-label">{label}</text>'
        )
        if desc:
            parts.append(
                f'<text x="{x + (_CELL_W - 8) / 2:.0f}" y="{y + 96:.0f}" '
                f'class="c4-node-desc">{desc}</text>'
            )
        parts.append("</g>")
    parts.append("</g>")
    return "".join(parts)


def _render_comparison_boxes(spec: AnimationSpecification) -> str:
    parts: list[str] = ['<g id="c4-compare">']
    for node in spec.nodes:
        if node.id not in ("col_a", "col_b"):
            continue
        x = _MARGIN + 30 if node.id == "col_a" else _MARGIN + _COLS * _CELL_W - 230
        y = _MARGIN + 90
        items = [line for line in (node.description or "").split(" | ") if line]
        box_h = 58 + len(items) * 22 + 20
        parts.append(
            f'<g class="c4-compare-col" data-id="{_esc(node.id)}" opacity="0">'
            f'<rect x="{x:.0f}" y="{y:.0f}" rx="14" width="200" height="{box_h:.0f}"/>'
            f'<text x="{x + 100:.0f}" y="{y + 30:.0f}" class="c4-compare-head">'
            f"{_esc(node.label)}</text>"
        )
        for i, item in enumerate(items[:5]):
            parts.append(
                f'<text x="{x + 16:.0f}" y="{y + 58 + i * 22:.0f}" '
                f'class="c4-compare-item">&#8226; {_esc(item)}</text>'
            )
        parts.append("</g>")
    parts.append("</g>")
    return "".join(parts)


def _explanation_html(explanation: dict[str, str]) -> str:
    if not explanation:
        return ""
    blocks = [
        ("what_you_see", "What you see"),
        ("how_to_read", "How to read it"),
        ("key_takeaway", "Key takeaway"),
        ("motion_justification", "Why motion helps"),
    ]
    inner = "".join(
        f'<div class="c4-ex-block"><span class="c4-ex-k">{_esc(label)}</span>'
        f"<p>{_esc(explanation.get(key, ''))}</p></div>"
        for key, label in blocks
        if explanation.get(key)
    )
    if not inner:
        return ""
    return (
        '<section id="c4-explanation" class="c4-panel">'
        "<h4>Learning guide</h4>" + inner + "</section>"
    )


def _interaction_payload(spec: AnimationSpecification) -> list[dict[str, Any]]:
    """Serialise guided interactions.

    ``anchor_step_index`` on the schema is the 1-based position of the step
    within its scene. The generator always anchors at the final visible step of
    the last scene, so we resolve it to a global 1-based index for the player.
    """
    payload: list[dict[str, Any]] = []
    for interaction in spec.interactions:
        scene_index = interaction.anchor_scene_index or len(spec.scenes)
        prior_steps = sum(len(s.steps) for s in spec.scenes[: scene_index - 1])
        payload.append(
            {
                "kind": interaction.kind.value,
                "sceneIndex": scene_index,
                "stepIndex": interaction.anchor_step_index,
                "globalStepIndex": prior_steps + interaction.anchor_step_index,
                "prompt": interaction.prompt,
                "answer": interaction.answer,
                "guide_hint": interaction.guide_hint,
            }
        )
        if len(payload) >= 4:
            break
    return payload


_CSS = """
  :root {
    --bg: #0B1626; --surface: #0E1A2B; --primary: #F2A623;
    --secondary: #1D9E75; --accent: #D85A30; --text: #F4EFE4;
    --muted: rgba(244,239,228,0.55); --border: rgba(244,239,228,0.14);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Space Grotesk', system-ui, sans-serif; }
  #c4-stage { position: relative; padding: 12px; }
  svg { display: block; width: 100%; height: auto; background: var(--bg); }
  .c4-node rect { fill: var(--surface); stroke: var(--border); stroke-width: 1.4; transition: opacity .25s ease; }
  .c4-node text { fill: var(--text); font-size: 13px; text-anchor: middle; }
  .c4-node .c4-node-desc { fill: var(--muted); font-size: 11px; }
  .c4-node.c4-active rect { stroke: var(--primary); stroke-width: 2.4; filter: drop-shadow(0 0 6px rgba(242,166,35,.35)); }
  .c4-compare-col rect { fill: var(--surface); stroke: var(--border); stroke-width: 1.4; }
  .c4-compare-col.c4-active rect { stroke: var(--secondary); stroke-width: 2.4; }
  .c4-compare-head { fill: var(--primary); font-size: 15px; font-weight: 700; text-anchor: middle; }
  .c4-compare-item { fill: var(--text); font-size: 12px; }
  .c4-edge { stroke: var(--border); stroke-width: 1.6; opacity: .5; transition: opacity .2s ease; }
  .c4-edge-arrow { stroke: var(--border); stroke-width: 4; stroke-dasharray: 0, 10; marker-end: url(#arrowhead); opacity: 0; }
  .c4-edge.c4-flowed { stroke: var(--secondary); opacity: .85; }
  .c4-edge-arrow.c4-flowed { stroke: var(--secondary); opacity: .9; }
  .c4-edge.c4-active, .c4-edge-arrow.c4-active { stroke: var(--primary); opacity: 1; }
  #c4-message { padding: 6px 16px 0; min-height: 78px; }
  #c4-caption-title { color: var(--primary); font-size: 15px; margin-bottom: 4px; }
  #c4-caption-text { color: var(--text); font-size: 14px; }
  #c4-scene-progress, .c4-step-count { color: var(--muted); font-size: 12px; }
  .c4-hud { display: flex; gap: 8px; align-items: center; padding: 10px 16px 14px; flex-wrap: wrap; }
  .c4-btn { background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; font-size: 14px; cursor: pointer; }
  .c4-btn:hover { border-color: var(--primary); }
  .c4-btn.c4-play { background: var(--secondary); border-color: var(--secondary); color: #04231c; font-weight: 700; min-width: 40px; }
  .c4-panel { margin: 4px 16px 20px; padding: 14px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; }
  .c4-panel h4 { color: var(--primary); margin-bottom: 8px; font-size: 14px; }
  .c4-ex-block { margin-bottom: 8px; }
  .c4-ex-k { color: var(--secondary); font-weight: 700; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
  .c4-ex-block p { font-size: 13px; margin-top: 2px; color: var(--text); }
  .c4-overlay { position: fixed; inset: 0; background: rgba(4,10,18,.78); display: flex; align-items: center; justify-content: center; z-index: 50; }
  .c4-overlay-card { background: var(--surface); border: 1px solid var(--primary); border-radius: 14px; padding: 22px 26px; max-width: 420px; }
  .c4-overlay-card h4 { color: var(--primary); margin-bottom: 8px; }
  #c4-annotate { display: none; margin: 0 16px; padding: 10px 14px; background: rgba(242,166,35,.1); border-left: 3px solid var(--primary); color: var(--text); font-size: 14px; }
  [hidden] { display: none !important; }
"""

_SCRIPT = r"""
<script>
(function () {
  var RAW = __C4_PAYLOAD__;
  var scenes = RAW.scenes;
  var starts = [];
  var total = 0;
  scenes.forEach(function (s) { starts.push(total); total += s.steps.length; });
  var state = { scene: 0, step: 0, playing: false, speed: 1, timer: null };
  var curScene = function () { return scenes[state.scene]; };
  var curStep = function () { return scenes[state.scene].steps[state.step]; };
  var globalStep = function () { return starts[state.scene] + state.step; };
  function apply(reveal, active, flowed) {
    var s = scenes[state.scene];
    for (var i = 0; i < state.step; i++) {
      var st = s.steps[i];
      if (st.kind === 'reveal') st.nodeIds.forEach(function (id) { reveal[id] = true; });
      else if (st.kind === 'traverse') st.edgeIds.forEach(function (id) { flowed[id] = true; });
    }
  }
  function render() {
    var s = scenes[state.scene];
    var reveal = {}, active = {}, flowed = {};
    apply(reveal, active, flowed);
    var last = s.steps[state.step];
    if (last.kind === 'traverse') {
      last.edgeIds.forEach(function (id) { flowed[id] = false; active[id] = true; });
    } else if (last.kind !== 'reveal' && last.kind !== 'pause') {
      last.nodeIds.forEach(function (id) { reveal[id] = true; active[id] = true; });
    }
    document.querySelectorAll('#c4-nodes .c4-node').forEach(function (g) {
      var id = g.getAttribute('data-id');
      g.setAttribute('opacity', (reveal[id] || active[id]) ? '1' : '0');
      g.classList.toggle('c4-active', !!active[id]);
    });
    document.querySelectorAll('#c4-compare .c4-compare-col').forEach(function (g) {
      var id = g.getAttribute('data-id');
      g.setAttribute('opacity', (reveal[id] || active[id]) ? '1' : '0');
      g.classList.toggle('c4-active', !!active[id]);
    });
    document.querySelectorAll('#c4-edges .c4-edge').forEach(function (l) {
      var id = l.getAttribute('data-id');
      l.classList.toggle('c4-flowed', !!flowed[id]);
      l.classList.toggle('c4-active', !!active[id]);
    });
    document.querySelectorAll('#c4-edges .c4-edge-arrow').forEach(function (l) {
      var id = l.getAttribute('data-id');
      l.classList.toggle('c4-flowed', !!flowed[id]);
      l.classList.toggle('c4-active', !!active[id]);
    });
    var annotate = document.getElementById('c4-annotate');
    if (last.kind === 'annotate' && last.caption) {
      annotate.textContent = last.caption;
      annotate.style.display = 'block';
    } else if (annotate) {
      annotate.style.display = 'none';
    }
    document.getElementById('c4-caption-title').textContent = s.title;
    document.getElementById('c4-caption-text').textContent = last.caption;
    document.getElementById('c4-scene-progress').textContent =
      'Scene ' + (state.scene + 1) + '/' + scenes.length +
      ' - Step ' + (state.step + 1) + '/' + s.steps.length;
    document.getElementById('c4-step-count').textContent = globalStep() + 1 + ' / ' + total;
    checkInteraction();
  }
  function seek(scene, step) { state.scene = scene; state.step = step; }
  function advance() {
    if (!state.playing) return;
    var s = scenes[state.scene];
    if (state.step + 1 < s.steps.length) {
      state.step++;
    } else if (state.scene + 1 < scenes.length) {
      seek(state.scene + 1, 0);
    } else {
      stop(); return;
    }
    render();
  }
  function play() {
    if (state.playing) return;
    state.playing = true;
    document.getElementById('c4-play').innerHTML = '&#10074;&#10074;';
    tick();
  }
  function tick() {
    if (!state.playing) return;
    var st = curStep();
    render();
    state.timer = setTimeout(function () { advance(); tick(); }, (st ? st.durationMs : 1000) / state.speed);
  }
  function stop() {
    state.playing = false;
    document.getElementById('c4-play').innerHTML = '&#9654;';
    clearTimeout(state.timer);
  }
  function checkInteraction() {
    var overlay = document.getElementById('c4-interaction');
    var shown = false;
    RAW.interactions.forEach(function (it) {
      if (it.globalStepIndex - 1 === globalStep()) {
        document.getElementById('c4-interaction-prompt').textContent = it.prompt;
        overlay.hidden = false;
        shown = true;
        stop();
      }
    });
    if (!shown) overlay.hidden = true;
  }
  document.getElementById('c4-play').addEventListener('click', function () { state.playing ? stop() : play(); });
  document.getElementById('c4-next').addEventListener('click', function () { advance(); stop(); });
  document.getElementById('c4-prev').addEventListener('click', function () {
    if (state.step > 0) { state.step--; }
    else if (state.scene > 0) { seek(state.scene - 1, scenes[state.scene - 1].steps.length - 1); }
    stop(); render();
  });
  document.getElementById('c4-restart').addEventListener('click', function () { seek(0, 0); stop(); render(); });
  document.getElementById('c4-step').addEventListener('click', function () {
    var s = scenes[state.scene];
    if (state.step + 1 < s.steps.length) state.step++;
    stop(); render();
  });
  document.getElementById('c4-speed').addEventListener('click', function () {
    state.speed = state.speed === 0.5 ? 1 : state.speed === 1 ? 1.5 : state.speed === 1.5 ? 2 : 0.5;
    document.getElementById('c4-speed').textContent = state.speed + 'x';
    if (state.playing) { clearTimeout(state.timer); tick(); }
  });
  document.getElementById('c4-interaction-next').addEventListener('click', function () {
    document.getElementById('c4-interaction').hidden = true;
    play();
  });
  function refreshGlobal() {
    var last = curScene().steps[state.step];
    window.__c4state = {
      step: globalStep() + 1,
      totalSteps: total,
      caption: last ? last.caption : '',
      playing: state.playing,
      speed: state.speed
    };
  }
  window.__c4control = function (action) {
    if (action === 'restart') { seek(0, 0); stop(); render(); }
    else if (action === 'prev') {
      if (state.step > 0) { state.step--; }
      else if (state.scene > 0) { seek(state.scene - 1, scenes[state.scene - 1].steps.length - 1); }
      else { stop(); state.step = 0; }
      stop(); render();
    }
    else if (action === 'next') {
      var s = scenes[state.scene];
      if (state.step + 1 < s.steps.length) { state.step++; }
      else if (state.scene + 1 < scenes.length) { seek(state.scene + 1, 0); }
      else { seek(0, 0); }
      stop(); render();
    }
    else if (action === 'play') { state.playing ? stop() : play(); }
    else if (action === 'slow') { state.speed = 0.5; if (state.playing) { clearTimeout(state.timer); tick(); } }
    else if (action === 'fast') { state.speed = 2; if (state.playing) { clearTimeout(state.timer); tick(); } }
    refreshGlobal();
  };
  setInterval(function () { refreshGlobal(); }, 250);
  refreshGlobal();
  render();
})();
</script>
"""


def render_animation_package(
    spec: AnimationSpecification,
    *,
    title: str = "",
    topic_title: str = "",
    explanation: dict[str, str] | None = None,
) -> str:
    """Render a deterministic, self-contained animation package as HTML."""
    payload_spec = {
        "animationType": spec.animation_type.value,
        "title": title or spec.title,
        "topic": topic_title,
        "scenes": [_scene_payload(s) for s in spec.scenes],
        "interactions": _interaction_payload(spec),
    }
    payload_json = json.dumps(payload_spec, ensure_ascii=False, separators=(",", ":"))
    # Escape "<" as the valid JSON escape \\u003c so no user text can ever form
    # "</script", "<script", or "<!--" inside the script block: the HTML tokenizer
    # in script-data state is keyed on the literal "<" character.
    payload_json = payload_json.replace("<", "\\u003c")

    layout, width, height = _layout(spec)
    edge_svg = _render_edges(spec, layout)
    node_svg = _render_nodes(spec, layout)
    compare_svg = _render_comparison_boxes(spec)
    exp = (
        explanation
        if explanation is not None
        else build_animation_explanation(spec.animation_type, spec, topic_title or spec.title)
    )

    message = (
        '<h4 id="c4-caption-title"></h4>'
        '<p id="c4-caption-text"></p>'
        '<p id="c4-scene-progress" class="c4-progress"></p>'
    )
    overlay = (
        '<div id="c4-interaction" class="c4-overlay" hidden>'
        '<div class="c4-overlay-card">'
        "<h4>Check understanding</h4>"
        '<p id="c4-interaction-prompt"></p>'
        '<button id="c4-interaction-next" class="c4-btn">Continue</button>'
        "</div>"
        "</div>"
    )
    hud = (
        '<div id="c4-hud" class="c4-hud">'
        '<button id="c4-restart" class="c4-btn" aria-label="Restart">&#8634;</button>'
        '<button id="c4-prev" class="c4-btn" aria-label="Previous step">&#9664;</button>'
        '<button id="c4-play" class="c4-btn c4-play" aria-label="Play / Pause">&#9654;</button>'
        '<button id="c4-next" class="c4-btn" aria-label="Next step">&#9654;</button>'
        '<button id="c4-step" class="c4-btn" aria-label="Step reveal">+</button>'
        '<button id="c4-speed" class="c4-btn" aria-label="Playback speed">1x</button>'
        '<span id="c4-step-count" class="c4-step-count"></span>'
        "</div>"
    )

    document = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8"/>'
        f"<title>{_esc(payload_spec['title'])}</title>\n"
        "<style>" + _CSS + "</style>\n</head>\n<body>\n"
        '<div id="c4-stage">'
        f'<svg id="c4-svg" viewBox="0 0 {width:.0f} {height:.0f}" role="img" '
        f'aria-label="{_esc(payload_spec["title"])}">\n'
        "<defs>"
        '<marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">'
        f'<polygon points="0 0, 8 3, 0 6" fill="{_SECONDARY}"/></marker>'
        "</defs>\n" + edge_svg + node_svg + compare_svg + "\n</svg>\n</div>\n"
        f'<div id="c4-message">{message}</div>\n'
        '<div id="c4-annotate"></div>\n'
        + hud
        + overlay
        + _explanation_html(exp)
        + "\n"
        + _SCRIPT.replace("__C4_PAYLOAD__", payload_json)
        + "</body>\n</html>"
    )
    return document


render_animation_package_public = render_animation_package
