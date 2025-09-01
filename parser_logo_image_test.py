import os
import re
import json
import requests
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Dict, List, Tuple

# =========================
# Réglages
# =========================
_TIMEOUT = 7
_HEADERS = {"User-Agent": "AgregateurDeContenu/1.0 (+contact: dev@example.com)"}
_GOOGLE_API = "https://www.googleapis.com/customsearch/v1"
_DEFAULT_CACHE_PATH = Path(os.getenv("LOGO_CACHE_PATH", str(Path.home() / ".cache" / "agregateur_logo_cache.json")))

_MEMO: Dict[str, str] = {}

# Domaines hors-sujet
_BLACKLIST_HOST_PARTS = [
    "pinterest.", "pinimg.com", "reddit.", "facebook.", "instagram.", "x.com", "twitter.",
    "shutterstock.", "istockphoto.", "gettyimages.", "dreamstime.", "depositphotos.",
    "vectorstock.", "freepik.", "fineartamerica.", "123rf.", "alamy.",
    "wallpaper", "fond-ecran", "background", "template"
]

# Mots-clés
_POSITIVE_URL_TOKENS = ["logo", "brand", "branding", "identity", "charte", "charte-graphique",
                        "press", "media", "kit", "assets", "marque", "guidelines", "styleguide",
                        "mark", "logotype", "favicon"]
_NEGATIVE_URL_TOKENS = ["wallpaper", "background", "mockup", "template"]

# =========================
# Cache persistant
# =========================
def _load_disk_cache(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_disk_cache(path: Path, data: Dict[str, str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def _get_cached(prefix: str, cache_path: Path) -> Optional[str]:
    if prefix in _MEMO:
        return _MEMO[prefix]
    disk = _load_disk_cache(cache_path)
    if prefix in disk:
        _MEMO[prefix] = disk[prefix]
        return disk[prefix]
    return None

def _set_cached(prefix: str, url: str, cache_path: Path):
    _MEMO[prefix] = url
    disk = _load_disk_cache(cache_path)
    disk[prefix] = url
    _save_disk_cache(cache_path, disk)

# =========================
# Utils domaine / URL
# =========================
def _norm_host(host: str) -> str:
    host = (host or "").lower().strip()
    host = re.sub(r"^(www|m)\.", "", host)
    return host

def _host_of(url: str) -> str:
    try:
        return _norm_host(urlparse(url).netloc or "")
    except Exception:
        return ""

def _same_site(target_host: str, candidate_url: str) -> bool:
    h = _host_of(candidate_url)
    t = _norm_host(target_host)
    return (h == t) or h.endswith("." + t) or t.endswith("." + h)

def _ext_of(url: str) -> str:
    path = urlparse(url).path.lower()
    m = re.search(r"\.([a-z0-9]{2,5})(?:$|\?)", path)
    return m.group(1) if m else ""

def _contains_any(s: str, tokens: List[str]) -> bool:
    s = (s or "").lower()
    return any(tok in s for tok in tokens)

# =========================
# Google CSE
# =========================
def _prefix_from_url(url: str) -> Optional[str]:
    try:
        p = urlparse(url)
        if not p.scheme or not p.netloc:
            return None
        return f"{p.scheme}://{_norm_host(p.netloc)}/"
    except Exception:
        return None

def _pick_reference_url(entry: Optional[dict], base_link: Optional[str]) -> Optional[str]:
    if entry:
        for k in ("site","homepage","source_url","origin_link","url","link"):
            v = entry.get(k)
            if isinstance(v,str) and v.startswith(("http://","https://")):
                return v
    if isinstance(base_link,str) and base_link.startswith(("http://","https://")):
        return base_link
    return None

def _build_queries(prefix_url: str, entry: Optional[dict]) -> List[Tuple[str,str]]:
    p = urlparse(prefix_url)
    host = _norm_host(p.netloc or "")
    label = host.split(".")[0] if host else ""

    queries: List[Tuple[str,str]] = []

    queries.append(("domaine", f"site:{host} logo"))
    queries.append(("domaine", f"{host} logo"))

    if len(label) >= 3:
        queries.append(("label", f"{label} logo"))

    if entry:
        for k in ("organization", "publisher", "source", "site_name", "name", "title"):
            v = entry.get(k)
            if isinstance(v, str) and len(v.strip()) >= 3:
                queries.append(("meta", f"{v.strip()} logo"))

    queries.append(("svg", f"site:{host} filetype:svg logo"))
    queries.append(("svg", f"{host} filetype:svg logo"))

    queries.append(("brand-assets",
                   f"site:{host} (brand assets OR charte graphique OR identité visuelle OR press kit OR media kit) logo"))
    queries.append(("brand-assets", f"{host} brand assets logo"))

    # déduplication
    seen = set()
    deduped = []
    for cat, q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append((cat, q))
    return deduped

def _google_image_search(query: str, api_key: str, cx: str,
                         filetype: Optional[str]=None, num: int=10) -> List[dict]:
    params = {
        "key": api_key, "cx": cx, "q": query,
        "searchType": "image", "num": str(num), "safe": "off", "hl": "fr", "gl": "fr"
    }
    if filetype:
        params["fileType"] = filetype
        params["hq"] = f"filetype:{filetype}"
    try:
        r = requests.get(_GOOGLE_API, headers=_HEADERS, params=params, timeout=_TIMEOUT)
        if not r.ok:
            return []
        return r.json().get("items", []) or []
    except Exception:
        return []

# =========================
# Filtrage et scoring
# =========================
def _is_blacklisted_host(url: str) -> bool:
    h = _host_of(url)
    s = (h + " " + url).lower()
    return any(tok in s for tok in _BLACKLIST_HOST_PARTS)

def _valid_image(it: dict, min_side: int=64) -> Tuple[bool,int,int]:
    img = it.get("image", {}) or {}
    w = int(img.get("width") or 0)
    h = int(img.get("height") or 0)
    return (w >= min_side and h >= min_side, w, h)

def _score_candidate(it: dict, target_host: str) -> float:
    title = (it.get("title") or "").lower()
    link = it.get("link") or ""
    ctx  = (it.get("image", {}) or {}).get("contextLink") or ""
    snippet = (it.get("snippet") or "").lower()

    same_ctx = _same_site(target_host, ctx)
    same_link = _same_site(target_host, link)

    score = 0.0
    if same_ctx: score += 50
    elif same_link: score += 20

    url_all = " ".join([title, link.lower(), snippet, ctx.lower()])

    if _contains_any(url_all, _POSITIVE_URL_TOKENS):
        score += 18
    if _contains_any(url_all, ["brand", "assets", "charte", "identity", "press", "media", "guidelines", "styleguide"]):
        score += 10
    if _contains_any(url_all, _NEGATIVE_URL_TOKENS):
        score -= 10
    if _is_blacklisted_host(link) or _is_blacklisted_host(ctx):
        score -= 60

    ext = _ext_of(link)
    if ext == "svg":
        score += 16
    elif ext == "png":
        score += 12
    elif ext == "webp":
        score += 8
    else:
        score += 2

    ok, w, h = _valid_image(it, 64)
    if ok:
        score += min(min(w, h) / 64.0, 20.0)
        ratio = (w / h) if h else 1.0
        if ratio > 4 or ratio < 0.25:
            score -= 25

    return score

# =========================
# Fonction principale
# =========================
def extract_logo_institution(
    entry: dict | None,
    base_link: str | None,
    fallback_url: str = "https://upload.wikimedia.org/wikipedia/commons/6/65/No-Image-Placeholder.svg",
    *,
    google_api_key: Optional[str] = None,
    google_cx: Optional[str] = None,
    cache_path: Path = _DEFAULT_CACHE_PATH,
    force_refresh: bool = True,
    max_queries: int = 6,
    per_query: int = 10
) -> str:
    api_key = google_api_key or os.getenv("GOOGLE_API_KEY")
    cx = google_cx or os.getenv("GOOGLE_CX")
    if not api_key or not cx:
        return fallback_url

    ref = _pick_reference_url(entry, base_link)
    if not ref:
        return fallback_url

    prefix = _prefix_from_url(ref)
    if not prefix:
        return fallback_url

    if not force_refresh:
        cached = _get_cached(prefix, cache_path)
        if cached:
            return cached

    queries = _build_queries(prefix, entry)
    if max_queries > 0:
        queries = queries[:max_queries]

    target_host = _host_of(prefix)
    best: Tuple[float, Optional[str]] = (-1e9, None)
    seen_links = set()

    for cat, q in queries:
        results = _google_image_search(q, api_key, cx, filetype=None, num=per_query)
        for it in results:
            link = it.get("link")
            if not link or link in seen_links:
                continue
            seen_links.add(link)

            ok, w, h = _valid_image(it, 16)
            if not ok:
                continue

            s = _score_candidate(it, target_host)
            if s > best[0]:
                best = (s, link)

        if best[0] >= 95:
            break

    chosen = best[1] or fallback_url
    _set_cached(prefix, chosen, cache_path)
    return chosen
