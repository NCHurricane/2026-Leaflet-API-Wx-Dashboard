# Dashboard Version 2 Roadmap

**Status:** Planning

---

## Purpose

This roadmap captures long-term enhancements that extend beyond the current
optimization work. It intentionally excludes items already covered by the
Satellite Render Pipeline, Radar Render Pipeline, and active Super Plan.

The goal is to maintain a single location for future initiatives without
allowing them to distract from current development.

---

# Guiding Principles

1. Finish the current optimization plans first.
2. Measure before optimizing.
3. Prioritize maintainability over complexity.
4. Build features that benefit all hardware classes.
5. Keep the dashboard approachable while providing advanced capabilities for power users.

---

# Version 2 Categories

---

## 1. Performance

**Status:** Planned

### Goals

- Adaptive worker allocation
- Hardware-aware defaults
- Performance profiles
- Intelligent cache management
- Low-end hardware optimization
- Continuous performance regression testing

Possible features:

- Automatic CPU detection
- Recommended worker count
- Performance presets
    - Power Saver
    - Balanced
    - Maximum Performance
    - Custom

---

## 2. Settings & Control Center

**Status:** Planned

Replace the existing scattered settings approach with a centralized Settings Drawer.

Sections may include:

- Global
- Display
- Performance
- Diagnostics
- Accessibility
- Current Page Settings

Features:

- Hardware information
- Worker controls
- Global map preferences
- Theme management
- Advanced configuration

---

## 3. UI Branding & Design System

**Status:** Planned

Establish a unified visual language across the entire application.

Goals:

- Design tokens
- Standard components
- Consistent spacing
- Typography rules
- Color system
- Iconography
- Component showcase page
- Visual regression checklist

---

## 4. Developer Diagnostics

**Status:** Planned

Create an internal diagnostics dashboard for development and troubleshooting.

Potential metrics:

- Tile render latency
- Queue depth
- Worker utilization
- Memory usage
- Cache hit rates
- Active render jobs
- Network timing
- Python process health
- Browser performance

---

## 5. User Experience

**Status:** Future

Ideas:

- First-run setup wizard
- Hardware auto-detection
- Workspace presets
- Keyboard command palette
- Improved onboarding
- Better accessibility
- Better mobile/tablet support

---

## 6. Broadcasting

**Status:** Future

Improve usability for live streaming.

Potential features:

- Broadcast Mode
- Simplified UI
- Larger labels
- Auto-hide editing controls
- OBS-friendly layouts
- Scene presets

---

## 7. Advanced User Configuration

**Status:** Planned

Separate supported user customization from internal application configuration.

Possible structure:

Default Configuration

↓

User Overrides

↓

Page Overrides

Goals:

- Easier upgrades
- Cleaner documentation
- Safer customization
- Stable supported settings

---

## 8. Future Research

**Status:** Research

Topics to investigate after Version 2:

- GPU-accelerated map rendering
- WebGPU
- Browser-side rendering
- Multi-machine rendering
- Remote worker nodes
- Plugin architecture
- Theme marketplace
- Optional cloud synchronization

---

# Document Organization

Detailed implementation documents should live separately and be referenced from this roadmap.

Example:

Version 2 Roadmap
│
├── UI Branding Plan
├── Diagnostics Dashboard
├── Settings System
├── Broadcast Features
├── Adaptive Performance
└── User Configuration

---

# Notes

This roadmap is intentionally high-level.

Detailed implementation plans should only be created when work is scheduled.

The roadmap should evolve as the project matures while remaining focused on long-term vision rather than active implementation.