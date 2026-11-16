"""Facts from the links the user pastes: website colours, fonts, logo, words; YouTube channel and recent videos.

This part only collects facts with their source. The Brand identity (an agent with the onboarding skill) decides what
goes into the style pack and says where each value came from. Nothing here guesses taste.
"""

from __future__ import annotations

import colorsys
import os
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

UA = "Mozilla/5.0 (compatible; Crewcut/0.1; +https://github.com/marcopatzelt/crewcut)"
TIMEOUT = 15.0
MAX_BYTES = 3_000_000
SOCIAL = ("x.com", "twitter.com", "instagram.com", "linkedin.com", "tiktok.com", "facebook.com", "threads.net",
          "bsky.app")
FREE_FONT_HOSTS = ("fonts.googleapis.com", "fonts.bunny.net", "fonts.gstatic.com")
HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
RGB = re.compile(r"rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})")
VAR = re.compile(r"--([\w-]*(?:primary|brand|accent|main|highlight|color|colour)[\w-]*)\s*:\s*([^;}{]+)", re.I)
FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
GENERIC_FONTS = {"sans-serif", "serif", "monospace", "system-ui", "-apple-system", "blinkmacsystemfont", "inherit",
                 "segoe ui", "roboto", "helvetica neue", "arial", "helvetica", "ui-sans-serif", "ui-serif",
                 "ui-monospace", "apple color emoji", "segoe ui emoji", "segoe ui symbol", "noto color emoji",
                 "initial", "var", "cursive", "fantasy", "emoji", "math", "fangsong", "unset", "revert"}


def kind_of(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")
    if host in ("youtube.com", "youtu.be") or host.endswith(".youtube.com"):
        return "youtube"
    if any(host == s or host.endswith("." + s) for s in SOCIAL):
        return "social"
    return "website"


# ---- HTML ------------------------------------------------------------------------------------------------------------
class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.links: list[dict] = []
        self.styles: list[str] = []
        self.inline_styles: list[str] = []
        self.imgs: list[dict] = []
        self.svgs: list[str] = []
        self.text: list[str] = []
        self._tag_stack: list[str] = []
        self._svg_depth = 0
        self._svg_buf: list[str] = []
        self._svg_logo = False
        self._in_style = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "link":
            self.links.append(a)
        elif tag == "style":
            self._in_style = True
        elif tag == "img":
            self.imgs.append(a)
        elif tag in ("script", "noscript", "template"):
            self._skip += 1
        if a.get("style"):
            self.inline_styles.append(a["style"])
        if tag == "svg":
            if self._svg_depth == 0:
                ident = " ".join([a.get("class", ""), a.get("id", ""), a.get("aria-label", "")]).lower()
                self._svg_logo = "logo" in ident or "brand" in ident
                self._svg_buf = []
            self._svg_depth += 1
        if self._svg_depth and self._svg_logo:
            attrs_s = "".join(f' {k}="{v}"' for k, v in attrs if v is not None)
            self._svg_buf.append(f"<{tag}{attrs_s}>")
        self._tag_stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False
        if tag in ("script", "noscript", "template") and self._skip:
            self._skip -= 1
        if self._svg_depth and self._svg_logo:
            self._svg_buf.append(f"</{tag}>")
        if tag == "svg" and self._svg_depth:
            self._svg_depth -= 1
            if self._svg_depth == 0 and self._svg_logo and len(self.svgs) < 3:
                self.svgs.append("".join(self._svg_buf))
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data):
        if self._in_style:
            self.styles.append(data)
            return
        if self._skip:
            return
        if self._tag_stack and self._tag_stack[-1] == "title" and not self.title:
            self.title = data.strip()
        t = " ".join(data.split())
        if t and self._tag_stack and self._tag_stack[-1] in ("h1", "h2", "h3", "p", "li", "a", "span", "button"):
            self.text.append(t)


def _norm_hex(h: str) -> str:
    h = h.lower()
    if len(h) == 4:
        h = "#" + "".join(c * 2 for c in h[1:])
    return h.upper()


def _hex_of_rgb(r, g, b) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(x))) for x in (r, g, b)))


def color_info(hex_: str) -> dict:
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, lum, s = colorsys.rgb_to_hls(r, g, b)
    return {"hex": hex_, "lightness": round(lum, 3), "saturation": round(s, 3)}


def colors_from_css(css: str) -> dict:
    counts: Counter[str] = Counter()
    for m in HEX.finditer(css):
        counts[_norm_hex(m.group(0))] += 1
    for m in RGB.finditer(css):
        counts[_hex_of_rgb(*m.groups())] += 1
    named = {}
    for m in VAR.finditer(css):
        val = m.group(2).strip()
        hx = HEX.search(val)
        rgb = RGB.search(val)
        if hx:
            named[m.group(1)] = _norm_hex(hx.group(0))
        elif rgb:
            named[m.group(1)] = _hex_of_rgb(*rgb.groups())
    infos = [{**color_info(h), "count": n} for h, n in counts.most_common(40)]
    saturated = [c for c in infos if c["saturation"] > 0.35 and 0.15 < c["lightness"] < 0.85]
    neutrals = [c for c in infos if c not in saturated]
    return {"accent_candidates": saturated[:8], "neutral_candidates": neutrals[:8], "named": named}


def fonts_from_css(css: str, font_links: list[str]) -> list[dict]:
    fams: Counter[str] = Counter()
    for m in FONT_FAMILY.finditer(css):
        for part in m.group(1).split(","):
            name = part.strip().strip("'\"").strip()
            if name and name.lower() not in GENERIC_FONTS and not name.startswith("var("):
                fams[name] += 1
    free = set()
    for link in font_links:
        for fam in re.findall(r"family=([^&:]+)", link):
            free.add(fam.replace("+", " ").strip())
    out = []
    for name, n in fams.most_common(6):
        out.append({"family": name, "uses": n,
                    "licence": "free (Google Fonts)" if name in free else "unknown: do not download; pick a similar "
                                                                            "free font and say so"})
    for fam in sorted(free - set(fams)):
        out.append({"family": fam, "uses": 0, "licence": "free (Google Fonts)"})
    return out


def parse_website(url: str, html: str, css_texts: list[str]) -> dict:
    p = _Page()
    p.feed(html)
    css = "\n".join(p.styles + p.inline_styles + css_texts)
    font_links = [urljoin(url, lk.get("href", "")) for lk in p.links
                  if any(h in (lk.get("href") or "") for h in FREE_FONT_HOSTS)]
    icons = [urljoin(url, lk["href"]) for lk in p.links
             if lk.get("href") and any(r in (lk.get("rel") or "").lower() for r in ("icon", "apple-touch-icon", "mask-icon"))]
    logo_imgs = [urljoin(url, i["src"]) for i in p.imgs
                 if i.get("src") and "logo" in " ".join([i.get("src", ""), i.get("alt", ""), i.get("class", ""),
                                                          i.get("id", "")]).lower()]
    text = " ".join(p.text)
    return {
        "url": url,
        "title": p.title or p.meta.get("og:title", ""),
        "site_name": p.meta.get("og:site_name", ""),
        "description": p.meta.get("description") or p.meta.get("og:description", ""),
        "language": (re.search(r"<html[^>]*\blang=[\"']?([\w-]+)", html, re.I) or [None, ""])[1],
        "theme_color": p.meta.get("theme-color", ""),
        "og_image": urljoin(url, p.meta["og:image"]) if p.meta.get("og:image") else "",
        "colors": colors_from_css(css + "\n" + p.meta.get("theme-color", "")),
        "fonts": fonts_from_css(css, font_links),
        "logo": {"inline_svg": p.svgs[:2], "images": logo_imgs[:4], "icons": icons[:4]},
        "text_sample": text[:2500],
        "source": url,
    }


# ---- network ---------------------------------------------------------------------------------------------------------
def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA, "Accept-Language": "en,*;q=0.5"}, timeout=TIMEOUT,
                        follow_redirects=True)


def _get(client: httpx.Client, url: str) -> str:
    r = client.get(url)
    r.raise_for_status()
    return r.content[:MAX_BYTES].decode(r.encoding or "utf-8", errors="replace")


def fetch_website(url: str, client: httpx.Client) -> dict:
    html = _get(client, url)
    page = _Page()
    page.feed(html)
    css_texts = []
    sheets = [urljoin(url, lk["href"]) for lk in page.links
              if lk.get("href") and "stylesheet" in (lk.get("rel") or "").lower()]
    for s in sheets[:6]:
        try:
            css_texts.append(_get(client, s))
        except httpx.HTTPError:
            continue
    return parse_website(url, html, css_texts)


def youtube_channel_id(html: str) -> str | None:
    for pat in (r'"externalId":"(UC[\w-]{22})"', r'itemprop="channelId" content="(UC[\w-]{22})"',
                r'"channelId":"(UC[\w-]{22})"', r"channel/(UC[\w-]{22})"):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def parse_feed(xml: str) -> list[dict]:
    out = []
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        def tag(name, e=entry):
            m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", e, re.S)
            return m.group(1).strip() if m else ""
        vid = tag("yt:videoId")
        views = re.search(r'<media:statistics views="(\d+)"', entry)
        out.append({"id": vid, "title": tag("title"), "published": tag("published"),
                    "views": int(views.group(1)) if views else None,
                    "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""})
    return out


def fetch_youtube(url: str, client: httpx.Client) -> dict:
    m = re.search(r"/channel/(UC[\w-]{22})", url)
    cid = m.group(1) if m else None
    html = ""
    if not cid:
        html = _get(client, url)
        cid = youtube_channel_id(html)
    info: dict = {"url": url, "channel_id": cid, "source": url}
    if html:
        p = _Page()
        p.feed(html)
        info["name"] = p.meta.get("og:title", "")
        info["description"] = p.meta.get("og:description") or p.meta.get("description", "")
    if cid:
        try:
            info["recent_videos"] = parse_feed(_get(client, f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"))
        except httpx.HTTPError as e:
            info["recent_videos"] = []
            info["note"] = f"feed not reachable: {e}"
        key = os.environ.get("YOUTUBE_API_KEY")
        if key:
            info.update(_youtube_api(cid, key, client))
    return info


def _youtube_api(cid: str, key: str, client: httpx.Client) -> dict:
    """Channel facts and the most viewed videos through the YouTube Data API (optional, needs a key)."""
    base = "https://www.googleapis.com/youtube/v3"
    out: dict = {}
    try:
        r = client.get(f"{base}/channels", params={"part": "snippet,statistics,brandingSettings", "id": cid, "key": key})
        items = r.json().get("items") or []
        if items:
            it = items[0]
            out["country"] = it["snippet"].get("country")
            out["default_language"] = it["snippet"].get("defaultLanguage")
            out["subscribers"] = it.get("statistics", {}).get("subscriberCount")
            out["keywords"] = it.get("brandingSettings", {}).get("channel", {}).get("keywords")
        r = client.get(f"{base}/search", params={"part": "snippet", "channelId": cid, "order": "viewCount",
                                                 "maxResults": 10, "type": "video", "key": key})
        out["top_videos"] = [{"id": i["id"]["videoId"], "title": i["snippet"]["title"]}
                             for i in r.json().get("items") or [] if i.get("id", {}).get("videoId")]
    except (httpx.HTTPError, KeyError, ValueError) as e:
        out["api_note"] = f"YouTube API not usable: {type(e).__name__}"
    return out


def download(url: str, dest_dir: Path, client: httpx.Client, name: str) -> str | None:
    """Download one asset (logo candidate) into the pack. Images and SVG only, small files only."""
    try:
        r = client.get(url)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    ctype = r.headers.get("content-type", "").split(";")[0]
    ext = {"image/svg+xml": ".svg", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
           "image/x-icon": ".ico", "image/vnd.microsoft.icon": ".ico"}.get(ctype)
    if not ext or len(r.content) > 2_000_000:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    p = dest_dir / f"{name}{ext}"
    p.write_bytes(r.content)
    return str(p)


def gather(links: list[str], client: httpx.Client | None = None, assets_dir: Path | None = None) -> dict:
    from .. import paths
    assets_dir = assets_dir or (paths.user_brand_dir() / "fetched")
    own = client is None
    client = client or _client()
    facts: dict = {"links": links, "websites": [], "youtube": [], "social": [], "notes": []}
    try:
        for url in links:
            k = kind_of(url)
            try:
                if k == "youtube":
                    facts["youtube"].append(fetch_youtube(url, client))
                elif k == "social":
                    facts["social"].append({"url": url, "note": "Social profiles are listed, not scraped."})
                else:
                    site = fetch_website(url, client)
                    saved = []
                    for i, cand in enumerate(site["logo"]["images"][:2] + site["logo"]["icons"][:2]):
                        p = download(cand, assets_dir, client, f"logo-candidate-{len(facts['websites'])}-{i}")
                        if p:
                            saved.append(p)
                    for i, svg in enumerate(site["logo"]["inline_svg"]):
                        assets_dir.mkdir(parents=True, exist_ok=True)
                        p = assets_dir / f"logo-inline-{len(facts['websites'])}-{i}.svg"
                        svg_doc = svg if 'xmlns="http://www.w3.org/2000/svg"' in svg else \
                            svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
                        p.write_text(svg_doc, encoding="utf-8")
                        saved.append(str(p))
                    site["logo"]["saved"] = saved
                    facts["websites"].append(site)
            except httpx.HTTPError as e:
                facts["notes"].append(f"{url}: not reachable ({type(e).__name__})")
    finally:
        if own:
            client.close()
    return facts


def summary(facts: dict) -> str:
    lines = []
    for w in facts.get("websites", []):
        acc = ", ".join(c["hex"] for c in w["colors"]["accent_candidates"][:4]) or "none"
        fonts = ", ".join(f"{f['family']} ({f['licence'].split(':')[0]})" for f in w["fonts"][:3]) or "none found"
        lines.append(f"Website {w['url']}: '{w['title']}', language {w['language'] or '?'}; accent candidates {acc}; "
                     f"fonts {fonts}; logo files {len(w['logo'].get('saved', []))}")
    for y in facts.get("youtube", []):
        lines.append(f"YouTube {y['url']}: channel {y.get('channel_id') or '?'}, {len(y.get('recent_videos', []))} "
                     "recent videos")
    for s in facts.get("social", []):
        lines.append(f"Social {s['url']}: listed only")
    lines += [f"Note: {n}" for n in facts.get("notes", [])]
    return "\n".join(lines) or "Nothing found."
