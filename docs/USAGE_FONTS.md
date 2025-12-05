# Custom Fonts

Place your font files (`.ttf`, `.otf`, `.ttc`) into `assets/fonts/`.

Examples:
- Copy `edo.ttf` to `assets/fonts/edo.ttf`
- Copy any `.ttf/.otf` and reference by name or path

How to select a font:
- API: include `"font": "edo"` or a full file path and optional `"fontsize"`
- CLI: add `--font edo --fontsize 72`

Resolution rules:
- Looks first in `assets/fonts` for matching `name.ttf/otf/ttc`
- On Windows, also searches `C:\\Windows\\Fonts`
- If not found, falls back to PIL default