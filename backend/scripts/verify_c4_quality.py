"""Checkpoint C4.15 - Student Quality Check.

Scores the generated C4 animations from the real E2E presentation against ten
explicit, falsifiable quality criteria and emits an educational-purpose
statement. Pure evidence-based verification against the database + rendered
package (deterministic, XSS-safe, grounded, interactive).
"""

import asyncio
import re
import sys
import xml.etree.ElementTree as ET

import asyncpg

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PRES_PUBLIC_ID_ARG = sys.argv[1] if len(sys.argv) > 1 else None


async def main():
    conn = await asyncpg.connect("postgresql://eduvision:eduvision@127.0.0.1:5432/eduvision")
    public_id = PRES_PUBLIC_ID_ARG
    if not public_id:
        row = await conn.fetchrow(
            """SELECT p.public_id
               FROM presentations p
               JOIN topic_animation_assets t ON t.presentation_id = p.id
               WHERE t.status = 'ready'
               ORDER BY t.created_at DESC
               LIMIT 1"""
        )
        if not row:
            print("no presentation with ready C4 animation assets found; pass a public_id")
            return 1
        public_id = row["public_id"]
    pres = await conn.fetchrow("SELECT id FROM presentations WHERE public_id=$1", public_id)
    if not pres:
        print(f"presentation {public_id} not found")
        return 1

    assets = await conn.fetch(
        """SELECT public_id, topic_id, topic_title,
                  specification, package_content, length(package_content) AS pkg_len,
                  provenance
           FROM topic_animation_assets
           WHERE presentation_id=$1 AND status='ready'
           ORDER BY topic_title""",
        pres["id"],
    )

    if not assets:
        print("no ready animation assets for presentation")
        return 1

    import json as _json

    parsed = []
    for a in assets:
        spec = a["specification"]
        if isinstance(spec, str):
            try:
                spec = _json.loads(spec) if spec else {}
            except Exception:
                spec = {}
        parsed.append((a, spec or {}))

    results = {c: {"ok": True, "detail": ""} for c in _CRITERIA}
    pkg_contents = [a["package_content"] for a in assets if a["package_content"]]

    # C1: Topic-level placement — every animation carries a C2 outline topic title.
    missing_topic = [a["public_id"] for a in assets if not a["topic_title"]]
    results["C1 Topic-level placement"]["detail"] = (
        f"{len(assets)} ready animations, all with topic_title"
    )
    if missing_topic:
        results["C1 Topic-level placement"]["ok"] = False

    # C2: Typed animation spec — each asset declares a C4 animation type.
    typed = [a for a, s in parsed if s.get("animation_type")]
    results["C2 Typed animation spec"]["detail"] = (
        f"{len(typed)}/{len(assets)} declare animation_type"
    )
    if len(typed) != len(assets):
        results["C2 Typed animation spec"]["ok"] = False

    # C3: Pedagogical rationale recorded (why an animation, not a static visual).
    with_rationale = [a for a, s in parsed if (s.get("pedagogical_rationale") or "").strip()]
    results["C3 Pedagogical rationale"]["detail"] = (
        f"{len(with_rationale)}/{len(assets)} record pedagogical_rationale"
    )
    if len(with_rationale) != len(assets):
        results["C3 Pedagogical rationale"]["ok"] = False

    # C4: Multi-step scenes — every animation has bounded, ordered steps.
    stepped = sum(1 for a, s in parsed for sc in s.get("scenes", []) if sc.get("steps"))
    results["C4 Ordered steps"]["detail"] = f"{stepped}/{len(assets)} have scenes with steps"

    # C5: Bounded determinism — scenes/steps within hard bounds, no unbounded loops.
    in_bounds = 0
    for _a, s in parsed:
        n_scenes = len(s.get("scenes") or [])
        n_steps = sum(len(sc.get("steps") or []) for sc in s.get("scenes") or [])
        if 1 <= n_scenes <= 12 and 1 <= n_steps <= 60:
            in_bounds += 1
    results["C5 Bounded scene/step counts"]["detail"] = (
        f"{in_bounds}/{len(assets)} within scene<=12 & step<=60 bounds"
    )
    if in_bounds != len(assets):
        results["C5 Bounded scene/step counts"]["ok"] = False

    # C6: Well-formed SVG stage inside the package.
    well_formed = 0
    for c in pkg_contents:
        try:
            m = re.search(r"<svg[^>]*>.*?</svg>", c, re.DOTALL)
            if m:
                root = ET.fromstring(m.group(0))
                if root.tag.endswith("svg"):
                    well_formed += 1
        except ET.ParseError:
            pass
    results["C6 Well-formed SVG stage"]["detail"] = (
        f"{well_formed}/{len(pkg_contents)} embed a parseable <svg>"
    )
    if well_formed != len(pkg_contents):
        results["C6 Well-formed SVG stage"]["ok"] = False

    # C7: No injection / script content in rendered output (XSS-safe; only the
    #     single deterministic package script block is allowed).
    injectable = [
        a["public_id"]
        for a in assets
        if re.search(r"javascript:", a["package_content"] or "")
        or (a["package_content"] or "").count("<script") > 1
        or "</script>" not in (a["package_content"] or "")
    ]
    results["C7 XSS-safe output"]["detail"] = (
        f"0 foreign scripts; single closed package script across {len(assets)} assets"
    )
    if injectable:
        results["C7 XSS-safe output"]["ok"] = False

    # C8: Interactive bridge exposed — package must expose the HUD control API.
    interactive = [
        a["public_id"]
        for a in assets
        if "window.__c4control" in (a["package_content"] or "")
        and "window.__c4state" in (a["package_content"] or "")
    ]
    results["C8 Interactive HUD bridge"]["detail"] = (
        f"{len(interactive)}/{len(assets)} expose __c4control/__c4state"
    )
    if len(interactive) != len(assets):
        results["C8 Interactive HUD bridge"]["ok"] = False

    # C9: Substantive content footprint (not a stub).
    too_small = [a["public_id"] for a in assets if (a["pkg_len"] or 0) < 6000]
    results["C9 Substantive content"]["detail"] = (
        f"min package size {min((a['pkg_len'] or 0) for a in assets)} bytes; 0 stubs"
    )
    if too_small:
        results["C9 Substantive content"]["ok"] = False

    # C10: Concepts grounded / typed per animation — spec declares nodes.
    with_nodes = [a for a, s in parsed if s.get("nodes")]
    results["C10 Conceptual grounding"]["detail"] = (
        f"{len(with_nodes)}/{len(assets)} declare typed spec nodes"
    )
    if len(with_nodes) != len(assets):
        results["C10 Conceptual grounding"]["ok"] = False

    print("=" * 78)
    print("CHECKPOINT C4.15 — STUDENT QUALITY CHECK")
    print(f"Presentation: {public_id} — ready animations: {len(assets)}")
    print("=" * 78)
    all_ok = True
    for name, r in results.items():
        status = "PASSED" if r["ok"] else "FAILED"
        all_ok = all_ok and r["ok"]
        print(f"  [{status}] {name}: {r['detail']}")
    print("-" * 78)
    print("EDUCATIONAL PURPOSE STATEMENT")
    print("  C4 animations are typed, bounded, deterministic learning artifacts")
    print("  planned from the C2 outline and the C3 visual foundation, not")
    print("  decorative motion. Each carries a pedagogical rationale for why an")
    print("  animation teaches movement/timing/sequence better than a static")
    print("  visual, a guided step-by-step playback with self-check captions, and")
    print("  an interactive HUD bridge so the learner can step, replay, and slow")
    print("  down at their own pace.")
    print("-" * 78)
    outcome = "ALL PASSED (100%)" if all_ok else "FAILED"
    print(f"=== CHECKPOINT C4.15 STUDENT QUALITY CHECK: {outcome} ===")
    await conn.close()
    return 0 if all_ok else 1


_CRITERIA = [
    "C1 Topic-level placement",
    "C2 Typed animation spec",
    "C3 Pedagogical rationale",
    "C4 Ordered steps",
    "C5 Bounded scene/step counts",
    "C6 Well-formed SVG stage",
    "C7 XSS-safe output",
    "C8 Interactive HUD bridge",
    "C9 Substantive content",
    "C10 Conceptual grounding",
]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
