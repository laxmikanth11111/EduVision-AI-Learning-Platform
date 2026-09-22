"""C4.12 contract tests — deterministic renderer exposes an interactive bridge.

The self-contained package must expose ``window.__c4control`` (play/pause/next/
prev/restart/slow/fast) and ``window.__c4state`` (step/totalSteps/caption) so the
player's Animation Mode HUD can drive and read a sandboxed iframe deterministically.
Also verifies the front-end player wires the Animation Mode tab, fetch, render,
and HUD control functions.
"""

from __future__ import annotations

from pathlib import Path

from app.schemas.c3_visual_intelligence import VisualNode
from app.schemas.c4_animation_intelligence import (
    AnimationScene,
    AnimationSpecification,
    AnimationStep,
    AnimationStepKind,
    C4AnimationType,
)
from app.services.c4_animation_renderer import render_animation_package

PLAYER_HTML = Path(__file__).resolve().parents[2] / "frontend" / "player.html"


def _make_spec() -> AnimationSpecification:
    nodes = [
        VisualNode(id="n1", label="A"),
        VisualNode(id="n2", label="B"),
        VisualNode(id="n3", label="C"),
    ]
    scenes = [
        AnimationScene(
            scene_index=1,
            steps=[
                AnimationStep(
                    step_index=1, kind=AnimationStepKind.REVEAL, node_ids=["n1"], caption="one"
                ),
                AnimationStep(
                    step_index=2, kind=AnimationStepKind.REVEAL, node_ids=["n2"], caption="two"
                ),
                AnimationStep(
                    step_index=3, kind=AnimationStepKind.REVEAL, node_ids=["n3"], caption="three"
                ),
            ],
        )
    ]
    return AnimationSpecification(
        animation_type=C4AnimationType.PROCESS_SEQUENCE,
        title="T",
        nodes=nodes,
        scenes=scenes,
    )


def _render() -> str:
    return render_animation_package(
        _make_spec(),
        title="T",
        topic_title="Topic",
        explanation={"what_you_see": "x", "why_it_matters": "y"},
    )


def test_c4_12_renderer_exposes_control_bridge():
    pkg = _render()
    assert "window.__c4control" in pkg
    assert "window.__c4state" in pkg
    assert "restart" in pkg
    assert "advance" in pkg
    assert pkg.count("</script>") == 1


def test_c4_12_package_outlines_full_hud():
    pkg = _render()
    for element_id in (
        "c4-play",
        "c4-next",
        "c4-prev",
        "c4-restart",
        "c4-speed",
        "c4-interaction",
        "c4-caption-text",
    ):
        assert f'id="{element_id}"' in pkg, f"missing {element_id}"


def test_c4_12_player_wires_animation_mode():
    html = PLAYER_HTML.read_text(encoding="utf-8")
    assert "btnModeAnimation" in html
    assert "setPlayerMode('animation')" in html
    assert "fetchC4Animations" in html
    assert "renderAnimationSlide" in html
    assert "c4HudControl" in html
    assert "/c4/animations/presentation/" in html
    assert 'sandbox="allow-scripts allow-same-origin"' in html
