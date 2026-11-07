# Eye Within Words

Python + pygame generative piece: scrolling text rows form an eye; iris is concentric rings of rotating text; lids close in a blink. Runs natively and in the browser (pygbag/WebAssembly).

## Stack
- Python 3.10+, pygame 2.6
- pygbag (pygame -> WASM static build)
- Hosting: Vercel (static)

## Files
- `main.py` — entire app (`EyeWithinWordsApp`, `BlinkController`, `Camera`)
- `requirements.txt` — local deps
- `vercel.json` — Vercel Git deploy: installs pygbag 0.9.3, builds, serves `build/web`
- `deploy.sh` — manual build + CLI deploy (alternative to Git deploy)
- `README.md`, `LICENSE` (MIT), `docs/preview.jpg`
- `CHANGELOG.md`

## Architecture
- Fixed 1280x720 canvas (`pygame.SCALED`), async main loop (`await asyncio.sleep(0)` is required by pygbag).
- Background: pre-rendered gradient + 49 text rows. Each row has a dim and a bright pre-rendered strip, scrolled by offset.
- Eye interior = bright strips blitted through a per-row clip rect. The x-range comes from the inverse of the lid curve, so no per-pixel masking for text.
- Iris: dark disc + ~8 pre-rendered text rings, rotated per frame with `rotozoom`. Clipped to the eye polygon using `BLEND_RGBA_MULT`.
- Lids: polyline + rotated words placed along both curves.
- `BlinkController`: close (0.085s) -> hold -> open (0.18s); auto-blink every 2.6-6.2s, optional double blink.

## Controls
SPACE / click / tap = blink, B auto-blink, Z auto-zoom, C palette, R reseed, H help, ESC quit.

## Headless test
```
SDL_VIDEODRIVER=dummy python main.py --test-frames 62 --screenshot-dir shots
```
Writes frames 20 (open), 41-43 (closing/closed), 60 (reopened).

## Deploy (Vercel)
- Primary: public GitHub repo imported into Vercel. `vercel.json` sets framework to none, install `pip install pygbag==0.9.3`, build `pygbag --build .`, output `build/web`. Every push redeploys.
- Fallback: `./deploy.sh` (local pygbag build -> `vercel deploy build/web --prod`).
- pygbag packs every file in the folder into the web bundle, so keep large assets (screenshots etc.) small.

## Known constraints
- Uses pygame's default font (no TTF bundled) so web builds need no asset loading. Bundle a serif `.ttf` in the project folder for a more editorial look.
- pygbag loads its WASM runtime from a CDN at page load; first load is several MB.
- Canvas is landscape; on phones it letterboxes. Change `WIDTH, HEIGHT` for portrait (eye geometry is centered on `CX, CY`).
- Performance: per-frame `rotozoom` on ~8 ring surfaces. If the web build stutters on low-end phones, lower ring count (`range(..., 11)` step) or rotate every 2nd frame.

## Security
No network calls, no user data, no storage, no secrets. Static assets only.
