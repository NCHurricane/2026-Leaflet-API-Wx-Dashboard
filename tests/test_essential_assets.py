from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from matplotlib.ft2font import FT2Font
import shapefile

from config.radar_colortable_utils import (
    _COLORTABLE_DIR,
    _PAL_FILENAMES,
    _parse_pal,
)


ROOT = Path(__file__).resolve().parents[1]

FONT_FILES = {
    "Montserrat-Black.ttf",
    "Montserrat-BlackItalic.ttf",
    "Montserrat-Bold.ttf",
    "Montserrat-BoldItalic.ttf",
    "Montserrat-Italic-VariableFont_wght.ttf",
    "Montserrat-Regular.ttf",
    "Montserrat-VariableFont_wght.ttf",
}

SATELLITE_CMAP_COUNTS = {
    "IR_Color_Clouds_Summer.cmap": 2048,
    "IR_Color_Clouds_Winter.cmap": 2048,
    "fire_detection_3.9.cmap": 2048,
    "fogdiff_blue.cmap": 2048,
    "ramsdis_WV_12bit.cmap": 4096,
}

BOUNDARY_BUNDLES = {
    "cb_2025_us_state_500k": {"STUSPS", "GEOID"},
    "cb_2025_us_county_500k": {"STATEFP", "COUNTYFP", "GEOID"},
    "tl_2025_us_state": {"STUSPS", "GEOID"},
}
BOUNDARY_EXTENSIONS = {".shp", ".shx", ".dbf", ".prj", ".cpg"}

CANONICAL_PAGES = (
    ROOT / "index.html",
    ROOT / "frontend/pages/alerts/alerts.html",
    ROOT / "frontend/pages/drought/drought.html",
    ROOT / "frontend/pages/mrms/mrms.html",
    ROOT / "frontend/pages/radar/radar.html",
    ROOT / "frontend/pages/rtma/rtma.html",
    ROOT / "frontend/pages/satellite/satellite.html",
    ROOT / "frontend/pages/spc/spc.html",
    ROOT / "frontend/pages/surface/surface.html",
    ROOT / "frontend/pages/tropical/tropical.html",
    ROOT / "frontend/pages/water/water.html",
    ROOT / "frontend/pages/workspace/workspace.html",
    ROOT / "frontend/pages/wpc/wpc.html",
)

JS_IMPORT_RE = re.compile(
    r"^\s*(?:import|export)\s+(?:[^;]*?\s+from\s+)?[\"']([^\"']+)[\"']",
    re.MULTILINE,
)


class _PageAssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.references.append(values["src"])
        elif tag == "link" and values.get("href"):
            self.references.append(values["href"])
        elif tag == "img" and values.get("src"):
            self.references.append(values["src"])


def _local_asset_path(reference: str, source: Path) -> Path | None:
    parsed = urlsplit(str(reference or "").strip())
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    if parsed.path.startswith("data:") or parsed.path.startswith("#"):
        return None
    if parsed.path.startswith("/"):
        return ROOT / parsed.path.lstrip("/")
    return source.parent / parsed.path


def test_retained_montserrat_fonts_are_complete_and_readable():
    fonts_dir = ROOT / "fonts"

    assert {path.name for path in fonts_dir.glob("*.ttf")} == FONT_FILES
    for filename in sorted(FONT_FILES):
        font = FT2Font(str(fonts_dir / filename))
        assert font.family_name.startswith("Montserrat")

    core_css = (ROOT / "frontend/core/core.css").read_text(encoding="utf-8")
    landing_css = (ROOT / "css/shared.css").read_text(encoding="utf-8")
    assert "Montserrat-VariableFont_wght.ttf" in core_css
    assert "Montserrat-Italic-VariableFont_wght.ttf" in core_css
    assert "Montserrat-VariableFont_wght.ttf" in landing_css
    assert "Montserrat-Italic-VariableFont_wght.ttf" not in landing_css


def test_landing_and_leaflet_css_have_no_disconnected_legacy_assets():
    landing_css = (ROOT / "css/shared.css").read_text(encoding="utf-8")
    leaflet_css = (ROOT / "frontend/lib/leaflet/leaflet.css").read_text(
        encoding="utf-8"
    )

    assert ".banner-logo" not in landing_css
    assert "images/layers.png" not in leaflet_css
    assert "images/layers-2x.png" not in leaflet_css
    assert "images/marker-icon.png" not in leaflet_css


def test_canonical_pages_use_shared_chuck_copeland_branding():
    logo_path = ROOT / "img/chuck-copeland-weather-logo.svg"
    logo_source = logo_path.read_text(encoding="utf-8")
    logo_root = ET.fromstring(logo_source)
    bolt = next(
        (
            element
            for element in logo_root.iter()
            if element.attrib.get("id") == "lightning-bolt"
        ),
        None,
    )

    assert logo_root.attrib["viewBox"] == "0 0 1377.81 115.73"
    assert bolt is not None
    assert "#lightning-bolt" in logo_source
    assert (
        "animation: lightning-bolt-flash 4.5s ease-in-out infinite" in logo_source
    )
    assert "@media (prefers-reduced-motion: reduce)" in logo_source
    assert "animation: none" in logo_source
    assert "opacity: 1" in logo_source

    branding = (ROOT / "frontend/core/branding.js").read_text(encoding="utf-8")
    nav = (ROOT / "frontend/core/nav.js").read_text(encoding="utf-8")
    map_core = (ROOT / "frontend/core/map-core.js").read_text(encoding="utf-8")
    core_css = (ROOT / "frontend/core/core.css").read_text(encoding="utf-8")
    landing = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "/img/chuck-copeland-weather-logo.svg?v=20260826a" in branding
    assert "BRAND_NAME = 'Chuck Copeland Weather'" in branding
    assert "`${BRAND_NAME} home`" in branding
    assert "renderHeaderBrand(root)" in nav
    assert "BRAND_ASSET_URL" in map_core
    assert "image.alt = ''" in map_core
    assert "aria-hidden" in map_core
    assert "pointer-events: none" in core_css
    assert "background: transparent" in core_css
    assert "box-shadow: none" in core_css
    assert "/img/chuck-copeland-weather-logo.svg?v=20260826a" in landing
    assert 'aria-label="Chuck Copeland Weather home"' in landing

    for page_path in CANONICAL_PAGES[1:]:
        page = page_path.read_text(encoding="utf-8")
        assert '<div class="core-brand"></div>' in page
        assert ">NCHURRICANE<" not in page
        assert "/frontend/core/core.css?v=20260826e" in page

    for script_path in (ROOT / "frontend/pages").glob("*/*.js"):
        script = script_path.read_text(encoding="utf-8")
        if "../../core/map-core.js" in script:
            assert "../../core/map-core.js?v=20260826g" in script
        if "../../core/nav.js" in script:
            assert "../../core/nav.js?v=20260826a" in script


def test_canonical_map_pages_use_approved_esri_basemaps():
    map_core = (ROOT / "frontend/core/map-core.js").read_text(encoding="utf-8")
    approved_services = (
        "Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        "USA_Topo_Maps/MapServer/tile/{z}/{y}/{x}",
        "World_Imagery/MapServer/tile/{z}/{y}/{x}",
    )
    for service in approved_services:
        assert service in map_core
    assert "basemaps.cartocdn.com" not in map_core
    assert "basemap.nationalmap.gov" not in map_core
    assert "className: 'core-basemap-dark-tiles'" in map_core
    assert "const boundaryRenderer = leaflet.canvas" in map_core
    assert "renderer: boundaryRenderer" in map_core

    core_css = (ROOT / "frontend/core/core.css").read_text(encoding="utf-8")
    assert ".leaflet-layer.core-basemap-dark-tiles img.leaflet-tile" in core_css
    assert "brightness(0.6) contrast(1.08)" in core_css
    assert "drop-shadow(0 0 0.6px rgba(2, 6, 23, 0.72))" in core_css

    conus_scripts = (
        "alerts/alerts-page.js",
        "drought/drought-page.js",
        "mrms/mrms-page.js",
        "radar/radar-page.js",
        "rtma/rtma-page.js",
        "spc/spc-page.js",
        "surface/surface-page.js",
        "water/water-app.js",
        "workspace/workspace-app.js",
        "wpc/wpc-page.js",
    )
    for relative_path in conus_scripts:
        script = (ROOT / "frontend/pages" / relative_path).read_text(encoding="utf-8")
        assert "boundaryMode: 'conus'" in script

    for relative_path in ("satellite/satellite-page.js", "tropical/tropical-app.js"):
        script = (ROOT / "frontend/pages" / relative_path).read_text(encoding="utf-8")
        assert "boundaryMode: 'world'" in script

    for page_path in CANONICAL_PAGES[1:]:
        page = page_path.read_text(encoding="utf-8")
        select = re.search(
            r'<select id="[^"]+-basemap">(.*?)</select>', page, re.DOTALL
        )
        assert select, page_path.relative_to(ROOT)
        assert re.findall(r"<option>([^<]+)</option>", select.group(1)) == [
            "Dark",
            "Light",
            "USA Topo",
            "Satellite",
        ]


def test_split_page_css_excludes_unreachable_monolith_blocks():
    tropical_css = (ROOT / "frontend/pages/tropical/tropical.css").read_text(
        encoding="utf-8"
    )
    water_css = (ROOT / "frontend/pages/water/water.css").read_text(
        encoding="utf-8"
    )
    workspace_css = (ROOT / "frontend/pages/workspace/workspace.css").read_text(
        encoding="utf-8"
    )

    for css in (tropical_css, water_css, workspace_css):
        assert ".weather-header" not in css
        assert ".weather-shell" not in css

    assert "#wx-section-water" not in tropical_css
    assert ".workspace-shell" not in tropical_css
    assert "#weather-tropical-hub" not in water_css
    assert ".workspace-shell" not in water_css
    assert "#weather-tropical-hub" not in workspace_css


def test_surface_frontend_uses_server_palette_without_fallback_isotherm():
    renderer = (
        ROOT / "frontend/pages/surface/surface-render.js"
    ).read_text(encoding="utf-8")
    engine = (
        ROOT / "frontend/pages/surface/surface-engine.js"
    ).read_text(encoding="utf-8")

    assert "SURFACE_COLORMAPS" not in renderer
    assert "drawIsothermFromGrid" not in renderer
    assert "FREEZING_ISOTHERM" not in renderer
    assert "colorAtValue(val, view.colorAnchors)" in renderer
    assert "normalizeColorAnchors(data?.color_anchors" in engine


def test_all_mapped_radar_palettes_parse_with_valid_colors():
    assert set(_PAL_FILENAMES.values()) == {
        path.name for path in _COLORTABLE_DIR.glob("*.pal")
    }

    for palette_key, filename in sorted(_PAL_FILENAMES.items()):
        parsed = _parse_pal(_COLORTABLE_DIR / filename)
        assert parsed["color_entries"], palette_key
        for entry in parsed["color_entries"]:
            assert all(0 <= component <= 255 for component in entry["c1"])
            assert all(0 <= component <= 255 for component in entry["c2"])


def test_satellite_awips_colormaps_have_complete_numeric_color_tables():
    cmap_dir = ROOT / "config/sat_cmaps"

    assert {path.name for path in cmap_dir.glob("*.cmap")} == set(
        SATELLITE_CMAP_COUNTS
    )
    for filename, expected_count in SATELLITE_CMAP_COUNTS.items():
        colors = ET.parse(cmap_dir / filename).getroot().findall("color")
        assert len(colors) == expected_count
        for color in colors:
            components = [float(color.attrib[channel]) for channel in "rgba"]
            assert all(0.0 <= component <= 1.0 for component in components)


def test_retained_boundary_bundles_are_complete_and_readable():
    boundary_dir = ROOT / "shapefiles"

    for stem, required_fields in BOUNDARY_BUNDLES.items():
        for extension in BOUNDARY_EXTENSIONS:
            component = boundary_dir / f"{stem}{extension}"
            assert component.is_file() and component.stat().st_size > 0

        with shapefile.Reader(str(boundary_dir / f"{stem}.shp")) as reader:
            fields = {field[0] for field in reader.fields[1:]}
            assert required_fields <= fields
            assert len(reader) > 0
            assert reader.shape(0).points


def test_canonical_pages_and_reachable_javascript_imports_exist():
    script_queue: list[Path] = []

    for page in CANONICAL_PAGES:
        assert page.is_file()
        parser = _PageAssetParser()
        parser.feed(page.read_text(encoding="utf-8"))
        assert parser.references, page
        for reference in parser.references:
            asset = _local_asset_path(reference, page)
            if asset is None:
                continue
            assert asset.is_file(), f"{page.relative_to(ROOT)} -> {reference}"
            if asset.suffix.lower() == ".js":
                script_queue.append(asset.resolve())

    visited: set[Path] = set()
    while script_queue:
        script = script_queue.pop()
        if script in visited:
            continue
        visited.add(script)
        source = script.read_text(encoding="utf-8")
        for reference in JS_IMPORT_RE.findall(source):
            imported = _local_asset_path(reference, script)
            if imported is None:
                continue
            imported = imported.resolve()
            assert imported.is_file(), (
                f"{script.relative_to(ROOT)} -> {reference}"
            )
            script_queue.append(imported)
