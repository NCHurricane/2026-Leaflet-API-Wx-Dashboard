from __future__ import annotations

import os

import numpy as np
from PIL import Image

from video_utils import save_animation
from weather import weather_utils


def export_frame_png(session_path: str, frame_index: int):
    """Compose a single frame from layered artifacts into a flat PNG."""
    weather_utils.touch_session(os.path.basename(session_path))

    basemap_path = os.path.join(session_path, "basemap", "basemap.png")
    product_path = os.path.join(
        session_path, "product", f"frame_{frame_index:04d}.png")
    static_overlay_path = os.path.join(
        session_path, "static_overlay", f"frame_{frame_index:04d}.png"
    )
    hud_right_path = os.path.join(
        session_path, "hud_right", f"frame_{frame_index:04d}.png")
    legend_path = os.path.join(
        session_path, "legend", f"frame_{frame_index:04d}.png")

    if not os.path.exists(basemap_path) or not os.path.exists(product_path):
        return None

    export_dir = os.path.join(session_path, "exports")
    os.makedirs(export_dir, exist_ok=True)
    export_path = os.path.join(
        export_dir, f"export_frame_{frame_index:04d}.png")

    basemap = Image.open(basemap_path).convert("RGBA")
    product = Image.open(product_path).convert("RGBA")

    if product.size != basemap.size:
        product = product.resize(basemap.size, Image.LANCZOS)

    composite = Image.alpha_composite(basemap, product)

    if os.path.exists(static_overlay_path):
        static_overlay = Image.open(static_overlay_path).convert("RGBA")
        if static_overlay.size != basemap.size:
            static_overlay = static_overlay.resize(basemap.size, Image.LANCZOS)
        composite = Image.alpha_composite(composite, static_overlay)

    if os.path.exists(legend_path):
        legend = Image.open(legend_path).convert("RGBA")
        if legend.size != basemap.size:
            legend = legend.resize(basemap.size, Image.LANCZOS)
        composite = Image.alpha_composite(composite, legend)

    if os.path.exists(hud_right_path):
        hud = Image.open(hud_right_path).convert("RGBA")
        if hud.size != basemap.size:
            hud = hud.resize(basemap.size, Image.LANCZOS)
        composite = Image.alpha_composite(composite, hud)

    composite.save(export_path, "PNG")
    return export_path


def export_animation_mp4(session_path: str, fps: int = 4):
    """Compose all frames from layered artifacts into an MP4."""
    weather_utils.touch_session(os.path.basename(session_path))

    basemap_path = os.path.join(session_path, "basemap", "basemap.png")
    if not os.path.exists(basemap_path):
        return None

    product_dir = os.path.join(session_path, "product")
    static_overlay_dir = os.path.join(session_path, "static_overlay")
    hud_dir = os.path.join(session_path, "hud_right")
    legend_dir = os.path.join(session_path, "legend")

    frame_files = sorted(
        [f for f in os.listdir(product_dir) if f.startswith(
            "frame_") and f.endswith(".png")]
    )
    if not frame_files:
        return None

    export_dir = os.path.join(session_path, "exports")
    os.makedirs(export_dir, exist_ok=True)
    export_path = os.path.join(export_dir, "export_animation.mp4")

    basemap = Image.open(basemap_path).convert("RGBA")
    rgb_frames = []

    for frame_file in frame_files:
        product = Image.open(os.path.join(
            product_dir, frame_file)).convert("RGBA")
        if product.size != basemap.size:
            product = product.resize(basemap.size, Image.LANCZOS)

        composite = Image.alpha_composite(basemap, product)

        static_overlay_path = os.path.join(static_overlay_dir, frame_file)
        if os.path.exists(static_overlay_path):
            static_overlay = Image.open(static_overlay_path).convert("RGBA")
            if static_overlay.size != basemap.size:
                static_overlay = static_overlay.resize(
                    basemap.size, Image.LANCZOS)
            composite = Image.alpha_composite(composite, static_overlay)

        legend_path = os.path.join(legend_dir, frame_file)
        if os.path.exists(legend_path):
            legend = Image.open(legend_path).convert("RGBA")
            if legend.size != basemap.size:
                legend = legend.resize(basemap.size, Image.LANCZOS)
            composite = Image.alpha_composite(composite, legend)

        hud_path = os.path.join(hud_dir, frame_file)
        if os.path.exists(hud_path):
            hud = Image.open(hud_path).convert("RGBA")
            if hud.size != basemap.size:
                hud = hud.resize(basemap.size, Image.LANCZOS)
            composite = Image.alpha_composite(composite, hud)

        rgb_frames.append(np.array(composite.convert("RGB")))

    save_animation(export_path, rgb_frames, fps=fps)
    return export_path
