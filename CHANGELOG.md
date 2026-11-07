# Changelog

## 2026-11-07
- Fixed: `H` could not re-show help after the first 6s (auto-hide ran every frame). Auto-hide now fires once, by wall time.
- Fixed: ESC in the browser build ended the loop and froze the canvas. ESC now quits on desktop only (`IS_WEB`).
- Verified: native headless test + pygbag 0.9.3 web build boot and render in Chromium.
- Added `vercel.json` (Git-based Vercel deploy), `README.md`, MIT `LICENSE`, `docs/preview.jpg`.
- Pinned pygbag to 0.9.3 in `deploy.sh` for reproducible builds.
- Fixed Vercel build: system Python is uv-managed (PEP 668 blocks pip). pygbag now installs into a venv at
  `/tmp/pygbag-venv`, outside the project so pygbag doesn't bundle it into the web build.

## 2026-10-24
- Initial build: text-row background, almond eye with bright interior, rotating text-ring iris, pupil, glint.
- Blink controller (auto, manual, optional double blink), breathing zoom, gaze wander / mouse follow.
- 4 palettes, reseed, help overlay.
- pygbag-ready async loop; headless screenshot test mode.
- Tuned: dimmer background rows, smaller iris so the eye shape reads clearly.
