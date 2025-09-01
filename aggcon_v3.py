# -*- coding: utf-8 -*-
"""
Agrégateur de contenu – prêt à l'emploi
- Catégories FR: Article, Vidéo, Podcast, Post, Livre, Revue
- Presse: Libération + Le Monde (À la Une)
- YouTube: flux RSS channel_id/user
- Bluesky: rendu style tweet + avatar/handle via API publique
- Images: RSS -> YouTube thumbnail -> OG/Twitter -> <img> plausible -> favicon
- Cache: ETag / Last-Modified (sources_state.json) pour éviter le rescrape
- DB: SQLite (mydb.db) avec migrations légères
- UI: Streamlit (Feed + Admin pour éditer sources.yaml)
"""

# =========================
# 0) Dépendances auto
# =========================
def _ensure_deps():
    import importlib, subprocess, sys
    pkgs = ["feedparser", "requests", "beautifulsoup4", "SQLAlchemy", "PyYAML", "streamlit"]
    for p in pkgs:
        mod = "bs4" if p == "beautifulsoup4" else p
        try:
            importlib.import_module(mod)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", p])
_ensure_deps()

# =========================
# 1) Imports
# =========================
import os, json, re, html
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

# =========================
# 2) Config & Constantes
# =========================
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}

CATEGORIES = {"Article", "Vidéo", "Podcast", "Post", "Livre", "Revue"}

SOURCES_YAML = "sources.yaml"
STATE_JSON = "sources_state.json"
DB_URL = "sqlite:///mydb.db"

DEFAULT_SOURCES = {
    "sources": [
        # --- Presse ---
        {"type": "rss", "platform": "Libération", "name": "Libération (Tout)", "url": "https://www.liberation.fr/arc/outboundfeeds/rss-all/?outputType=xml", "category": "Article"},
        {"type": "rss", "platform": "Le Monde", "name": "Le Monde - À la Une", "url": "https://www.lemonde.fr/rss/une.xml", "category": "Article"},

        # --- YouTube (RSS) ---
        {"type": "rss", "platform": "YouTube", "name": "Le Monde (YouTube)", "url": "https://www.youtube.com/feeds/videos.xml?user=LeMonde", "category": "Vidéo"},
        {"type": "rss", "platform": "YouTube", "name": "franceinfo", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCO6K_kkdP-lnSCiO3tPx7WA", "category": "Vidéo"},
        {"type": "rss", "platform": "YouTube", "name": "France Culture", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCd5DKToXYTKAQ6khzewww2g", "category": "Vidéo"},

        # --- Bluesky (microblog) ---
        {"type": "rss", "platform": "Bluesky", "name": "Thomas Piketty", "url": "https://bsky.app/profile/thomaspiketty.bsky.social/rss", "category": "Post"},
        {"type": "rss", "platform": "Bluesky", "name": "Gabriel Zucman", "url": "https://bsky.app/profile/gabrielzucman.bsky.social/rss", "category": "Post"},

        # --- Revues académiques (exemples) ---
        {"type": "rss", "platform": "Cairn", "name": "Revue Française de Sociologie", "url": "https://shs.cairn.info/rss/revue/RFS?lang=fr", "category": "Revue"},
    ]
}

# =========================
# 3) DB & Modèle
# =========================
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Content(Base):
    __tablename__ = "contents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, unique=True, nullable=False)
    title = Column(String)
    type = Column(String, nullable=False)  # Article, Vidéo, Podcast, Post, Livre, Revue
    description = Column(Text)
    published_at = Column(DateTime)
    source = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    image_url = Column(String)
    # Post (Bluesky/Twitter-like)
    author_name = Column(String)
    author_handle = Column(String)
    author_avatar_url = Column(String)
    # Podcast
    audio_url = Column(String)

Base.metadata.create_all(bind=engine)

def ensure_schema():
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("contents")}
    need = [c for c in ["image_url","author_name","author_handle","author_avatar_url","audio_url"] if c not in cols]
    if need:
        with engine.begin() as conn:
            for c in need:
                conn.execute(text(f"ALTER TABLE contents ADD COLUMN {c} VARCHAR"))
        print("✅ Schéma mis à jour (", ", ".join(need), ")")

# =========================
# 4) Utils nettoyage & extraction
# =========================
WHITESPACE_RE = re.compile(r"\s+")

def strip_html(text_: str) -> str:
    if not text_:
        return ""
    soup = BeautifulSoup(text_, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    cleaned = soup.get_text(separator=" ", strip=True)
    cleaned = html.unescape(cleaned)
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned

def looks_like_code_garbage(s: str) -> bool:
    if not s: return False
    lt_ratio = s.count("<") + s.count(">")
    ent_ratio = s.count("&")
    return lt_ratio > 10 or ent_ratio > 30

def pick_first_nonempty(*xs):
    for x in xs:
        if x and str(x).strip():
            return str(x).strip()
    return ""

def extract_entry_published(entry):
    if "published_parsed" in entry and entry.published_parsed:
        return datetime(*entry.published_parsed[:6])
    if "updated_parsed" in entry and entry.updated_parsed:
        return datetime(*entry.updated_parsed[:6])
    return None

# ---- Images
BAD_IMG_HINTS = ("sprite","logo","icon","avatar","placeholder","blank","transparent")

def youtube_id_from_url(link: str | None) -> str | None:
    if not link: return None
    try:
        u = urlparse(link)
        if "youtube.com" in u.netloc:
            if u.path == "/watch":
                return parse_qs(u.query).get("v", [None])[0]
            if u.path.startswith("/shorts/"):
                parts = u.path.strip("/").split("/")
                if len(parts) >= 2: return parts[1]
        if "youtu.be" in u.netloc and len(u.path) > 1:
            return u.path.strip("/")
    except Exception:
        pass
    return None

def first_plausible_img_from_html(html_text: str, base_link: str):
    soup = BeautifulSoup(html_text, "html.parser")
    # og/twitter variants
    metas = [
        ("property","og:image"),("name","og:image"),
        ("property","og:image:url"),("property","og:image:secure_url"),
        ("property","twitter:image"),("name","twitter:image"),("name","twitter:image:src")
    ]
    for (attr,val) in metas:
        m = soup.find("meta", attrs={attr: val})
        if m and m.get("content"):
            return urljoin(base_link, m["content"])
    ln = soup.find("link", rel="image_src")
    if ln and ln.get("href"):
        return urljoin(base_link, ln["href"])
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
        if not src:
            srcset = img.get("srcset") or img.get("data-srcset") or ""
            if srcset:
                src = srcset.split(",")[0].strip().split(" ")[0]
        if not src: 
            continue
        src = urljoin(base_link, src)
        low = src.lower()
        if any(b in low for b in BAD_IMG_HINTS):
            continue
        if low.endswith((".jpg",".jpeg",".png",".webp",".gif")):
            return src
    icon = soup.find("link", rel=lambda v: v and "icon" in v.lower())
    if icon and icon.get("href"):
        return urljoin(base_link, icon["href"])
    return None

def extract_image(entry, base_link: str | None):
    # 1) RSS media
    try:
        if getattr(entry, "media_thumbnail", None):
            url = entry.media_thumbnail[0].get("url")
            if url: return url
    except Exception: pass
    try:
        if getattr(entry, "media_content", None):
            for mc in entry.media_content:
                url = mc.get("url")
                if url: return url
    except Exception: pass
    try:
        for enc in getattr(entry, "enclosures", []) or []:
            url = getattr(enc, "href", None)
            typ = (getattr(enc, "type", "") or "").lower()
            if url and ("image" in typ or url.lower().endswith((".jpg",".jpeg",".png",".webp",".gif"))):
                return url
    except Exception: pass

    # 2) YouTube fallback
    vid = youtube_id_from_url(base_link or "")
    if vid:
        return f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"

    # 3) Scrape
    if base_link:
        try:
            resp = requests.get(base_link, timeout=10, headers=HTTP_HEADERS)
            if resp.ok and resp.text:
                return first_plausible_img_from_html(resp.text, base_link)
        except Exception:
            pass
    return None

def best_description_for_entry(entry, page_url: str | None):
    rss_html = pick_first_nonempty(
        getattr(entry, "summary", None),
        getattr(entry, "description", None),
        (entry.content[0].value if getattr(entry, "content", None) else None),
    )
    if rss_html and not looks_like_code_garbage(rss_html):
        return strip_html(rss_html)[:2000]
    if page_url:
        try:
            resp = requests.get(page_url, timeout=10, headers=HTTP_HEADERS)
            if resp.ok and resp.text:
                soup = BeautifulSoup(resp.text, "html.parser")
                og = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name":"description"})
                if og and og.get("content"):
                    return strip_html(og["content"])[:2000]
                for p in soup.find_all("p"):
                    txt = strip_html(p.get_text(" ", strip=True))
                    if len(txt) > 80:
                        return txt[:2000]
        except Exception:
            pass
    return strip_html(rss_html)[:2000]

# ---- Types
def normalize_type(t: str | None) -> str:
    t = (t or "").strip().lower()
    mapping = {
        "article":"Article","post":"Post","tweet":"Post","video":"Vidéo","vidéo":"Vidéo",
        "podcast":"Podcast","revue":"Revue","livre":"Livre"
    }
    return mapping.get(t, "Article")

def infer_type(title: str | None, platform: str | None, url: str | None, source_name: str | None) -> str:
    p = (platform or "").lower()
    u = (url or "").lower()
    s = (source_name or "").lower()
    if "youtube" in p or "youtube.com" in u or "youtu.be" in u:
        return "Vidéo"
    if "podcast" in p:
        return "Podcast"
    if "bsky.app" in u or "bluesky" in p or "x.com" in u or "twitter.com" in u:
        return "Post"
    if "cairn" in p or "revue" in p or any(k in s for k in ["revue","cairn"]):
        return "Revue"
    return "Article"

# ---- Bluesky
def bsky_handle_from_url(url: str) -> str | None:
    try:
        parts = urlparse(url).path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "profile":
            return parts[1]
    except Exception:
        pass
    return None

def fetch_bluesky_profile(handle: str) -> dict | None:
    api = f"https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor={handle}"
    try:
        r = requests.get(api, timeout=8)
        if r.ok:
            j = r.json()
            return {
                "author_name": j.get("displayName") or j.get("handle"),
                "author_handle": j.get("handle"),
                "author_avatar_url": j.get("avatar")
            }
    except Exception:
        pass
    return None

# =========================
# 5) Config & État (ETag)
# =========================
def ensure_sources_file():
    if not os.path.exists(SOURCES_YAML):
        with open(SOURCES_YAML, "w", encoding="utf-8") as f:
            yaml.safe_dump(DEFAULT_SOURCES, f, allow_unicode=True, sort_keys=False)
        print(f"📝 Fichier {SOURCES_YAML} créé avec des sources par défaut.")

def load_sources():
    ensure_sources_file()
    with open(SOURCES_YAML, "r", encoding="utf-8") as f:
        y = yaml.safe_load(f) or {}
    return y.get("sources", [])

def load_state():
    if os.path.exists(STATE_JSON):
        return json.load(open(STATE_JSON, "r", encoding="utf-8"))
    return {}

def save_state(state: dict):
    with open(STATE_JSON, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def parse_with_cache(url: str, state: dict):
    etag = state.get(url, {}).get("etag")
    modified = state.get(url, {}).get("modified")
    parsed = feedparser.parse(url, etag=etag, modified=modified)
    # MàJ état si présent
    et = parsed.get("etag")
    mod = parsed.get("modified")
    if et or mod:
        state[url] = {"etag": et, "modified": mod}
    return parsed

# =========================
# 6) Adapters & persistence
# =========================
def scan_pertinence(item: dict) -> bool:
    if not item.get("url"): return False
    desc = item.get("description", "")
    return bool(desc and len(desc.strip()) >= 10)

def save_to_db(session, item: dict):
    exists = session.query(Content).filter_by(url=item["url"]).first()
    if exists:
        updated = False
        for k in ["image_url","author_name","author_handle","author_avatar_url","audio_url","description","title","type"]:
            v = item.get(k)
            if v and (getattr(exists, k) in (None, "",) or (k=="description" and len(getattr(exists,k) or "")<50)):
                setattr(exists, k, v); updated = True
        if updated: session.commit()
        return
    session.add(Content(**item))
    session.commit()

def adapter_rss(src: dict, state: dict):
    parsed = parse_with_cache(src["url"], state)
    out = []
    for entry in parsed.entries:
        link = entry.get("link")
        pub = extract_entry_published(entry)
        desc = best_description_for_entry(entry, link)
        typ = infer_type(entry.get("title"), src.get("platform"), link, src.get("name"))
        if src.get("category"):  # override manuel
            typ = normalize_type(src["category"])
        img = extract_image(entry, link)

        # enrich Bluesky
        author_name = author_handle = author_avatar_url = None
        if typ == "Post" and link:
            handle = bsky_handle_from_url(link)
            if handle:
                prof = fetch_bluesky_profile(handle)
                if prof:
                    author_name = prof["author_name"]
                    author_handle = prof["author_handle"]
                    author_avatar_url = prof["author_avatar_url"]

        # audio (si podcast mal tagué)
        audio_url = None
        try:
            if getattr(entry, "enclosures", None):
                for enc in entry.enclosures:
                    if getattr(enc, "type", "").startswith("audio/"):
                        audio_url = enc.href
                        break
        except Exception:
            pass

        item = {
            "url": link,
            "title": entry.get("title"),
            "type": typ,
            "description": desc,
            "published_at": pub,
            "source": src.get("name", src.get("platform","")),
            "platform": src.get("platform",""),
            "image_url": img,
            "author_name": author_name,
            "author_handle": author_handle,
            "author_avatar_url": author_avatar_url,
            "audio_url": audio_url,
        }
        if scan_pertinence(item):
            out.append(item)
    return out

def run_worker():
    ensure_schema()
    session = SessionLocal()
    sources = load_sources()
    state = load_state()
    total = 0
    for src in sources:
        if src.get("type") == "rss":
            items = adapter_rss(src, state)
            for it in items:
                save_to_db(session, it)
            total += len(items)
    save_state(state)
    print(f"✅ Agrégation terminée : {total} éléments traités.")

# =========================
# 7) CLI & Streamlit UI
# =========================
def show_feed_console(limit=40):
    session = SessionLocal()
    items = session.query(Content).order_by(Content.published_at.desc().nullslast()).limit(limit).all()
    print("\n=== Aperçu du Feed ===\n")
    for it in items:
        print(f"[{it.source}] · {it.published_at} · {it.type}")
        if it.type == "Post":
            print(it.description[:280] + ("…" if it.description and len(it.description) > 280 else ""))
        else:
            if it.title: print(it.title)
            if it.description: print((it.description or "")[:160] + ("…" if it.description and len(it.description) > 160 else ""))
        if it.image_url: print(f"(image) {it.image_url}")
        print(it.url)
        print("-"*60)

# ---- Streamlit (exécuté via: streamlit run aggcon_v3.py)
def _streamlit_main():
    import streamlit as st
    st.set_page_config(page_title="Mon Agrégateur", layout="wide")
    st.title("📱 Mon Feed")

    session = SessionLocal()

    # Filtres
    c1, c2, c3 = st.columns([1,1,1])
    with c1:
        cat = st.selectbox("Catégorie", ["Toutes"] + sorted(CATEGORIES))
    with c2:
        src = st.text_input("Filtrer par source (contient)")
    with c3:
        limit = st.number_input("Limite", 10, 500, 200, 10)

    q = session.query(Content)
    if cat != "Toutes":
        q = q.filter(Content.type == cat)
    if src:
        q = q.filter(Content.source.ilike(f"%{src}%"))
    items = q.order_by(Content.published_at.desc().nullslast()).limit(int(limit)).all()

    # Rendu Post façon tweet
    def render_post(it):
        with st.container(border=True):
            colA, colB = st.columns([1, 12])
            with colA:
                if it.author_avatar_url:
                    st.image(it.author_avatar_url, width=48)
            with colB:
                header = ""
                if it.author_name: header += f"**{it.author_name}**  "
                if it.author_handle: header += f"*{it.author_handle}*"
                st.markdown(header or f"**{it.source}**")
                if it.description: st.write(it.description)
                if it.image_url: st.image(it.image_url, use_container_width=True)
                st.caption(f"{it.published_at} · {it.type} · {it.source}")
                st.markdown(f"[Lien]({it.url})")

    # Rendu standard
    def render_default(it):
        if it.image_url: st.image(it.image_url, use_container_width=True)
        if it.title: st.subheader(it.title)
        st.caption(f"{it.published_at} · {it.type} · {it.source}")
        if it.description: st.write(it.description)
        if it.type == "Podcast" and getattr(it, "audio_url", None):
            st.audio(it.audio_url)
        st.markdown(f"[Lien vers la source]({it.url})")

    tabs = st.tabs(["Feed", "Admin"])
    with tabs[0]:
        for it in items:
            if it.type == "Post":
                render_post(it)
            else:
                render_default(it)
            st.divider()

    with tabs[1]:
        st.subheader("⚙️ Éditer sources.yaml")
        current = ""
        if os.path.exists(SOURCES_YAML):
            current = open(SOURCES_YAML, "r", encoding="utf-8").read()
        text_val = st.text_area("sources.yaml", value=current, height=400)
        if st.button("💾 Enregistrer"):
            with open(SOURCES_YAML, "w", encoding="utf-8") as f:
                f.write(text_val)
            st.success("Enregistré. Relance l’agrégation (bouton ci-dessous).")
        if st.button("🔄 Lancer l’agrégateur maintenant"):
            run_worker()
            st.success("Agrégation terminée. Revenez sur l’onglet Feed.")

# Streamlit detect
def _is_streamlit():
    # Streamlit définit généralement cette variable d'env
    return any(k.startswith("STREAMLIT") for k in os.environ.keys())

# =========================
# 8) Entrée programme
# =========================
if __name__ == "__main__":
    ensure_sources_file()
    if _is_streamlit():
        # appelé via: streamlit run aggcon_v3.py
        _streamlit_main()
    else:
        # exécution directe: agrège + aperçu console
        run_worker()
        show_feed_console(40)
        print("\n💡 UI: lancez `streamlit run aggregateur.py` pour l'interface complète (Feed + Admin).")
