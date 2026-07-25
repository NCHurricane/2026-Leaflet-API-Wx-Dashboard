# Possible Enhancements for Version 2

These ideas were collected during architectural planning discussions while the
current optimization work is still underway.

Most of these items are intentionally deferred until after the Super Plan has
been completed.

---

# Adaptive Performance

## Automatic Worker Detection

Detect available CPU cores during startup.

Automatically recommend an optimal worker count while allowing manual overrides.

Benefits:

- Better experience on lower-end CPUs
- Prevents oversubscription
- Easier configuration

---

## Performance Profiles

Possible presets:

- Power Saver
- Balanced
- Maximum Performance
- Custom

Each profile could adjust:

- Worker count
- Cache sizes
- Update intervals
- Background tasks

---

# Memory Management

Investigate long-running browser memory usage.

Determine whether growth is caused by:

- Legitimate caching
- Browser image cache
- Tile accumulation
- JavaScript memory leaks

Potential improvements:

- Cache limits
- Automatic eviction
- Periodic cleanup
- Diagnostics

---

# Developer Diagnostics Dashboard

Create an internal developer-only dashboard showing live application metrics.

Possible metrics:

- Render latency
- Queue depth
- Worker utilization
- Cache statistics
- Memory usage
- Browser FPS
- Network timing
- HDF5 handle count
- Active tiles
- Tile generation rate

Goal:

Transform performance tuning from guesswork into measurable engineering.

---

# Settings Drawer

Replace scattered settings with a centralized drawer.

Structure:

Global

↓

Display

↓

Performance

↓

Diagnostics

↓

Current Page Settings

Advantages:

- Cleaner navigation
- Easier discovery
- Better organization
- More scalable

---

# Advanced Configuration

Instead of editing source code:

Provide a supported user configuration file.

Example hierarchy:

Default Settings

↓

User Settings

↓

Page Overrides

This allows advanced customization without modifying application code.

---

# UI Branding System

Create a consistent visual language.

Possible work:

- Design tokens
- Shared components
- Typography system
- Color palette
- Standard spacing
- Icon system

---

## Component Showcase

Create a hidden development page displaying every UI component.

Examples:

- Buttons
- Toggles
- Sliders
- Dropdowns
- Checkboxes
- Cards
- Titles
- Tables

Purpose:

Quickly verify styling consistency after UI changes.

---

# Broadcasting Improvements

Continue using OBS Studio as the primary broadcasting solution.

Potential dashboard improvements:

- Broadcast Mode
- Simplified UI
- Larger text
- Hide editing controls
- Presenter-friendly layouts

OBS remains responsible for:

- Encoding
- Scene switching
- Audio
- Camera
- Streaming

---

# GPU Map Rendering

MapLibre GL JS and similar technologies remain a future research item.

Current conclusion:

Backend rendering remains the performance bottleneck.

Migrating the frontend map renderer would require significant architectural changes while providing relatively little benefit at the current stage.

Recommendation:

Revisit only after backend optimization work has been completed.

---

# Licensing

Before public release:

Determine the project's licensing goals.

Questions to answer:

- Should commercial use be allowed?
- Should forks remain open source?
- Should attribution be required?
- Should modified versions be redistributed under the same license?

Potential licenses to evaluate:

- MIT
- Apache 2.0
- GPLv3
- AGPLv3
- Non-commercial licenses (not OSI Open Source)

---

# Long-Term Vision

The dashboard should evolve into a polished, highly configurable platform while remaining approachable for new users.

Version 2 should emphasize:

- Polish
- Consistency
- Observability
- Maintainability
- Scalability

Performance improvements should continue to be driven by real measurements rather than assumptions.