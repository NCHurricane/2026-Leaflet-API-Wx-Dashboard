from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SURFACE_PAGE = ROOT / "frontend" / "pages" / "surface"


def test_surface_warming_does_not_show_unmasked_client_gradient():
    engine = (SURFACE_PAGE / "surface-engine.js").read_text(encoding="utf-8")
    renderer = (SURFACE_PAGE / "surface-render.js").read_text(encoding="utf-8")

    assert "const gradientPendingKeys = new Set();" in engine
    assert "gradientPendingKeys.add(gradientKey);" in engine
    assert "onMeta?.(meta);" in engine
    assert "else if (!view.gradientPending) {" in renderer
