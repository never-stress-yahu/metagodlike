"""Cache the demo's Valve hero images so the hosted replay does not depend on the CDN."""
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[2]


def image_urls(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("icon_url", "image_url") and isinstance(child, str) and child.startswith("https://"):
                yield child
            else:
                yield from image_urls(child)
    elif isinstance(value, list):
        for child in value:
            yield from image_urls(child)


async def run():
    demo = json.loads((ROOT / "frontend/src/data/draft-demo.json").read_text(encoding="utf8"))
    directory = ROOT / "frontend/public/demo/heroes"
    directory.mkdir(parents=True, exist_ok=True)
    urls = sorted(set(image_urls(demo)))
    manifest = {}
    semaphore = asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        async def download(url):
            async with semaphore:
                response = await client.get(url)
                response.raise_for_status()
                if not response.headers.get("content-type", "").startswith("image/"):
                    raise ValueError("Unexpected asset content")
                name = ("icon-" if "/icons/" in url else "") + Path(urlsplit(url).path).name
                path = directory / name
                path.write_bytes(response.content)
                manifest[url] = {"path": "demo/heroes/" + name,
                                 "sha256": hashlib.sha256(response.content).hexdigest()}
        await asyncio.gather(*(download(url) for url in urls))
    (ROOT / "data/research/assets.json").write_text(json.dumps(dict(sorted(manifest.items())), indent=2) + "\n",
                                                  encoding="utf8", newline="\n")
    print("Cached", len(manifest), "hero images")


if __name__ == "__main__":
    asyncio.run(run())
