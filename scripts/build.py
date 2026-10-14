"""Bundle content/*.md into a single self-contained course page.

Usage: uv run scripts/build.py
Writes site/index.html (artifact body) and site/standalone.html (full HTML doc for static hosting).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
TEMPLATE = ROOT / "scripts" / "template.html"
OUT = ROOT / "site"

FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER.match(text)
    if not match:
        raise SystemExit(f"{path.name}: missing front matter")
    # House style: "to" for ranges and hyphens for compounds, never en or em dashes.
    for n, line in enumerate(text.splitlines(), 1):
        if "\u2013" in line or "\u2014" in line:
            raise SystemExit(f"{path.name}:{n}: en or em dash found")
    meta = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    for required in ("id", "week", "title", "kind"):
        if required not in meta:
            raise SystemExit(f"{path.name}: front matter needs '{required}'")
    meta["week"] = int(meta["week"])
    meta["minutes"] = int(meta.get("minutes", 0))
    meta["body"] = text[match.end() :]
    return meta


def main() -> None:
    entries = [parse(p) for p in sorted(CONTENT.glob("*.md"))]
    ids = [e["id"] for e in entries]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise SystemExit(f"duplicate ids: {sorted(dupes)}")
    for e in entries:
        for quiz in re.findall(r"```quiz\n(.*?)```", e["body"], re.DOTALL):
            json.loads(quiz)  # fail the build on malformed quiz JSON

    data = json.dumps(entries, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8").replace("/*__COURSE_DATA__*/[]", data)

    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    standalone = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        "</head>\n<body>\n" + page + "\n</body>\n</html>\n"
    )
    (OUT / "standalone.html").write_text(standalone, encoding="utf-8")
    words = sum(len(e["body"].split()) for e in entries)
    print(f"built {len(entries)} pages, {words:,} words -> {OUT}")


if __name__ == "__main__":
    main()
