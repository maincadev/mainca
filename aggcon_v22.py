# -*- coding: utf-8 -*-
"""
Aggrégateur de contenu - v2 (full + robust)
- Ingestion RSS/Podcasts (feedparser)
- Nettoyage HTML, détection type (ARTICLE/VIDEO/PODCAST/TWEET)
- Images: RSS -> OG/Twitter -> 1ère <img> plausible (+ fallback YouTube)
- Podcasts: pas de scraping (image iTunes si dispo)
- Rendu Streamlit, style "tweet" pour microblog
- DB SQLite (par défaut) + migration légère auto (ensure_schema)
- HTTP robuste: retries, timeouts, limite de taille
"""

from datetime import datetime
import os
import re
import html
import requests
from requests.adapters import HTTPAdapter, Retry
from urllib.parse import urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup
import feedparser

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Text,
    inspect, text, case
)
from sqlalchemy.orm import declarative_base, sessionmaker

# ======================================================
# 0) CONFIG DB
# ======================================================
# Pour PostgreSQL, décommente et ajuste :
# engine = create_engine("postgresql+psycopg2://user:password@localhost:5432/mydb")
engine = create_engine("sqlite:///mydb.db", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# ======================================================
# 1) MODELE ORM
# ======================================================
class Content(Base):
    __tablename__ = "contents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, unique=True, nullable=False)   # lien original
    title = Column(String, nullable=True)
    type = Column(String, nullable=False)               # ARTICLE, PODCAST, VIDEO, TWEET
    description = Column(Text)
    published_at = Column(DateTime)
    source = Column(String, nullable=False)             # nom de la source
    platform = Column(String, nullable=False)           # label plate-forme
    image_url = Column(String, nullable=True)           # image représentative

    # Champs auteur pour rendu "tweet"
    author_name = Column(String, nullable=True)
    author_handle = Column(String, nullable=True)
    author_avatar_url = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

def ensure_schema():
    """
    Migration légère pour SQLite : ajoute les colonnes manquantes si besoin.
    """
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("contents")}
    alter = []
    if "image_url" not in cols:
        alter.append("ADD COLUMN image_url VARCHAR")
    if "author_name" not in cols:
        alter.append("ADD COLUMN author_name VARCHAR")
    if "author_handle" not in cols:
        alter.append("ADD COLUMN author_handle VARCHAR")
    if "author_avatar_url" not in cols:
        alter.append("ADD COLUMN author_avatar_url VARCHAR")
    if alter:
        with engine.begin() as conn:
            for stmt in alter:
                conn.execute(text(f"ALTER TABLE contents {stmt}"))
        print("✅ Schéma mis à jour :", ", ".join(s.split()[-1] for s in alter))

ensure_schema()

# ======================================================
# 2) HTTP robuste + utils
# ======================================================
# Session HTTP robuste (retries + timeouts courts)
HTTP = requests.Session()
retries = Retry(
    total=2,                 # 2 tentatives en plus de la 1ère
    backoff_factor=0.2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"],
    raise_on_status=False,
)
HTTP.mount("http://", HTTPAdapter(max_retries=retries))
HTTP.mount("https://", HTTPAdapter(max_retries=retries))

SCRAPE_TIMEOUT = (3.05, 5.0)    # (connect, read)
MAX_HTML_BYTES = 300_000        # on ne parse pas >300 KB

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

WHITESPACE_RE = re.compile(r"\s+")

def strip_html(text_: str) -> str:
    """
    Nettoie un HTML *ou* renvoie tel quel si ça ressemble à un chemin/nom de fichier
    (évite MarkupResemblesLocatorWarning).
    """
    if not text_:
        return ""
    t = str(text_).strip()

    # Visiblement un chemin ?
    if os.path.exists(t) or re.match(r"^[A-Za-z]:\\", t) or re.search(r"\.(txt|pdf|jpg|jpeg|png|mp3|mp4|zip)$", t, re.I):
        return t

    # Pas de chevrons => probablement pas du HTML
    if "<" not in t and ">" not in t:
        return html.unescape(WHITESPACE_RE.sub(" ", t))

    soup = BeautifulSoup(t, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    cleaned = soup.get_text(separator=" ", strip=True)
    cleaned = html.unescape(cleaned)
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned

def looks_like_code_garbage(s: str) -> bool:
    if not s:
        return False
    lt_ratio = s.count("<") + s.count(">")
    return lt_ratio > 10 or ent_ratio > 30

def pick_first_nonempty(*candidates):
    for c in candidates:
        if c and str(c).strip():
            return str(c).strip()
    return ""

def extract_entry_published(entry):
    if "published_parsed" in entry and entry.published_parsed:
        return datetime(*entry.published_parsed[:6])
    if "updated_parsed" in entry and entry.updated_parsed:
        return datetime(*entry.updated_parsed[:6])
    return None

def _youtube_id_from_url(link: str | None) -> str | None:
    if not link:
        return None
    try:
        u = urlparse(link)
        if "youtube.com" in u.netloc and u.path == "/watch":
            return parse_qs(u.query).get("v", [None])[0]
        if "youtu.be" in u.netloc and len(u.path) > 1:
            return u.path.strip("/")
    except Exception:
        pass
    return None

def _first_plausible_img_from_soup(soup, base_link: str):
    # Meta OG/Twitter d'abord
    og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
    if og and og.get("content"):
        return urljoin(base_link, og["content"])
    tw = soup.find("meta", property="twitter:image") or soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        return urljoin(base_link, tw["content"])

    # Ensuite <img> plausibles (srcset, data-src, src)
    for img in soup.find_all("img"):
        srcset = img.get("srcset", "") or img.get("data-srcset", "")
        candidate = ""
        if srcset:
            candidate = srcset.split(",")[0].strip().split(" ")[0]
        if not candidate:
            candidate = img.get("src") or img.get("data-src") or ""
        if not candidate:
            continue
        candidate = urljoin(base_link, candidate)
        low = candidate.lower()
        if any(bad in low for bad in ["sprite", "logo", "icon", "avatar", "placeholder", "blank"]):
            continue
        if any(low.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
            return candidate
    return None

def extract_image_from_entry(entry, base_link: str | None, *, allow_scrape: bool = True):
    """
    Ordre:
      1) RSS: media_thumbnail / media_content / enclosures
      2) Fallback YouTube
      3) Scrape page (OG/Twitter -> 1ère <img> plausible) si allow_scrape=True
    Toutes les requêtes ont retries + timeouts + limite de taille.
    """
    # 1) RSS
    try:
        if "media_thumbnail" in entry and entry.media_thumbnail:
            url = entry.media_thumbnail[0].get("url")
            if url:
                return url
    except Exception:
        pass
    try:
        if "media_content" in entry and entry.media_content:
            for mc in entry.media_content:
                url = mc.get("url")
                if url:
                    return url
    except Exception:
        pass
    try:
        if getattr(entry, "enclosures", None):
            for enc in entry.enclosures:
                url = getattr(enc, "href", None)
                type_ = (getattr(enc, "type", "") or "").lower()
                if url and ("image" in type_ or url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))):
                    return url
    except Exception:
        pass

    # 2) YouTube
    if base_link:
        yt = _youtube_id_from_url(base_link)
        if yt:
            return f"https://i.ytimg.com/vi/{yt}/hqdefault.jpg"

    # 3) Scrape optionnel
    if not allow_scrape or not base_link:
        return None

    try:
        # HEAD rapide pour filtrer PDF/MP3 etc.
        h = HTTP.head(base_link, headers=HTTP_HEADERS, timeout=SCRAPE_TIMEOUT, allow_redirects=True)
        ctype = (h.headers.get("Content-Type") or "").lower()
        if "text/html" not in ctype and ctype != "":
            return None
    except Exception:
        pass  # certains sites ne gèrent pas HEAD

    try:
        r = HTTP.get(base_link, headers=HTTP_HEADERS, timeout=SCRAPE_TIMEOUT, stream=True)
        if r.status_code != 200:
            print(f"[image] GET {base_link} -> {r.status_code}")
            return None
        content = r.raw.read(MAX_HTML_BYTES, decode_content=True)
        try:
            text_small = content.decode(r.encoding or "utf-8", errors="ignore")
        except Exception:
            text_small = content.decode("utf-8", errors="ignore")

        soup = BeautifulSoup(text_small, "html.parser")
        img = _first_plausible_img_from_soup(soup, base_link)
        if not img:
            print(f"[image] Aucune image plausible sur {base_link}")
        return img
    except requests.RequestException as e:
        print(f"[image] Erreur réseau {base_link}: {e}")
        return None
    except Exception as e:
        print(f"[image] Erreur parsing {base_link}: {e}")
        return None

def infer_type_from_source_platform(title: str | None, platform: str, url: str) -> str:
    p = (platform or "").lower()
    u = (url or "").lower()
    if "youtube" in p or "youtube.com" in u or "youtu.be" in u:
        return "VIDEO"
    if "podcast" in p:
        return "PODCAST"
    if "bluesky" in p or "bsky.app" in u or "twitter.com" in u or "x.com" in u:
        return "TWEET"
    return "ARTICLE"

def best_description_for_entry(entry, page_url: str | None):
    rss_summary_html = pick_first_nonempty(
        getattr(entry, "summary", None),
        getattr(entry, "description", None),
        (entry.content[0].value if getattr(entry, "content", None) else None),
    )
    if rss_summary_html and not looks_like_code_garbage(rss_summary_html):
        return strip_html(rss_summary_html)[:2000]
    if page_url:
        try:
            r = HTTP.get(page_url, headers=HTTP_HEADERS, timeout=SCRAPE_TIMEOUT, stream=True)
            if r.status_code == 200:
                content = r.raw.read(MAX_HTML_BYTES, decode_content=True)
                try:
                    text_small = content.decode(r.encoding or "utf-8", errors="ignore")
                except Exception:
                    text_small = content.decode("utf-8", errors="ignore")
                soup = BeautifulSoup(text_small, "html.parser")
                og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
                if og_desc and og_desc.get("content"):
                    return strip_html(og_desc["content"])[:2000]
                for p in soup.find_all("p"):
                    txt = strip_html(p.get_text(" ", strip=True))
                    if len(txt) > 80:
                        return txt[:2000]
        except Exception:
            pass
    return strip_html(rss_summary_html)[:2000]

# ======================================================
# 3) BLUESKY/TWEET: auteur/handle/avatar
# ======================================================
_AVATAR_CACHE = {}

def _guess_bluesky_handle_from_feed_url(feed_url: str | None) -> str | None:
    # ex: https://bsky.app/profile/thomaspiketty.bsky.social/rss
    if not feed_url:
        return None
    try:
        u = urlparse(feed_url)
        if "bsky.app" in u.netloc and u.path.startswith("/profile/"):
            return u.path.split("/")[2]  # handle
    except Exception:
        pass
    return None

def fetch_bluesky_avatar_url(handle: str) -> str | None:
    if not handle:
        return None
    if handle in _AVATAR_CACHE:
        return _AVATAR_CACHE[handle]
    profile_url = f"https://bsky.app/profile/{handle}"
    try:
        r = HTTP.get(profile_url, headers=HTTP_HEADERS, timeout=SCRAPE_TIMEOUT)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            _AVATAR_CACHE[handle] = og["content"]
            return og["content"]
    except Exception:
        return None
    return None

# ======================================================
# 4) ADAPTERS
# ======================================================
def adapter_rss(source_url: str, source_name: str, source_platform: str, default_type: str = "ARTICLE"):
    feed = feedparser.parse(source_url)
    contents = []

    # Pré-déduire handle/avatar si flux Bluesky de profil
    preset_handle = _guess_bluesky_handle_from_feed_url(source_url)
    preset_avatar = fetch_bluesky_avatar_url(preset_handle) if preset_handle else None

    for entry in feed.entries:
        link = entry.get("link")
        pub = extract_entry_published(entry)
        inferred_type = infer_type_from_source_platform(entry.get("title"), source_platform, link)
        desc = best_description_for_entry(entry, link)
        img = extract_image_from_entry(entry, link, allow_scrape=True)

        author_name = None
        author_handle = None
        author_avatar_url = None

        if inferred_type == "TWEET":
            author_handle = preset_handle
            author_name = getattr(feed.feed, "title", None) or getattr(entry, "author", None) or source_name
            author_avatar_url = preset_avatar or fetch_bluesky_avatar_url(author_handle)

            # Si le title contient déjà "Auteur: message", évite les doublons
            if entry.get("title") and author_name and entry["title"].startswith(author_name):
                title_text = entry["title"][len(author_name):].lstrip(":-–— ").strip()
                if desc and len(desc) < 30 and title_text:
                    desc = title_text
                elif not desc:
                    desc = title_text

        contents.append({
            "type": inferred_type or default_type,
            "title": entry.get("title"),
            "url": link,
            "description": desc,
            "published_at": pub,
            "source": source_name,
            "platform": source_platform,
            "image_url": img,
            "author_name": author_name,
            "author_handle": author_handle,
            "author_avatar_url": author_avatar_url,
        })
    return contents

def adapter_podcast(source_url: str, source_name: str, source_platform: str = "Podcast"):
    feed = feedparser.parse(source_url)
    contents = []
    for entry in feed.entries:
        # audio
        audio_url = entry.enclosures[0].href if getattr(entry, "enclosures", None) else None

        # image iTunes (selon les flux : itunes:image -> entry.image.href ou feed.image.href)
        itunes_img = None
        try:
            itunes_img = (getattr(entry, "image", None) or {}).get("href")
        except Exception:
            pass
        if not itunes_img:
            try:
                itunes_img = (getattr(feed.feed, "image", None) or {}).get("href")
            except Exception:
                pass

        link = entry.get("link")
        pub = extract_entry_published(entry)
        desc = best_description_for_entry(entry, link)

        # IMPORTANT : allow_scrape=False (on ne va pas sur la page d’un podcast)
        img = itunes_img or extract_image_from_entry(entry, link, allow_scrape=False)

        contents.append({
            "type": "PODCAST",
            "title": entry.get("title"),
            "url": link,
            "description": desc,
            "published_at": pub,
            "audio_url": audio_url,
            "source": source_name,
            "platform": source_platform,
            "image_url": img,
        })
    return contents

# ======================================================
# 5) PERTINENCE
# ======================================================
def scan_pertinence(item: dict) -> bool:
    content = item.get("description")
    if not content or len(content.strip()) < 10:
        return False
    if not item.get("url"):
        return False
    return True

# ======================================================
# 6) SAUVEGARDE DB
# ======================================================
def save_to_db(session, item: dict):
    exists = session.query(Content).filter_by(url=item["url"]).first()
    if exists:
        updated = False
        for k in ("image_url", "author_name", "author_handle", "author_avatar_url"):
            v = item.get(k)
            if v and not getattr(exists, k):
                setattr(exists, k, v)
                updated = True
        if (not exists.description or len(exists.description) < 50) and item.get("description"):
            exists.description = item["description"]; updated = True
        if updated:
            session.commit()
        return

    content = Content(
        url=item["url"],
        title=item.get("title"),
        type=item["type"],
        description=item.get("description"),
        published_at=item.get("published_at"),
        source=item["source"],
        platform=item["platform"],
        image_url=item.get("image_url"),
        author_name=item.get("author_name"),
        author_handle=item.get("author_handle"),
        author_avatar_url=item.get("author_avatar_url"),
    )
    session.add(content)
    session.commit()

# ======================================================
# 7) ORCHESTRATEUR
# ======================================================
def run_worker():
    session = SessionLocal()
    sources = [
        # --- Médias indépendants ---
        {"type": "rss", "platform": "Blast", "url": "https://api.blast-info.fr/rss.xml", "name": "Blast"},

        # --- Chaînes YouTube ---
        {"type": "rss", "platform": "YouTube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCyJDHgrsUKuWLe05GvC2lng", "name": "StupidEconomist"},
        {"type": "rss", "platform": "YouTube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCVjzunJmfNx4YtW7d5oQg1g", "name": "Eurêka"},
        {"type": "rss", "platform": "YouTube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCQgWpmt02UtJkyO32HGUASQ", "name": "Thinkerview"},
        {"type": "rss", "platform": "YouTube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCj4bY7EoypA4lY7j4mVt4Jw", "name": "Usul & Cotentin"},
        {"type": "rss", "platform": "YouTube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCt6wG0g3mwa5rAfR2zY5XXQ", "name": "Osons Causer"},
        {"type": "rss", "platform": "YouTube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCJ0-oS6QFbA8l6jEO3aAcfQ", "name": "Le Média TV"},

        # --- Podcasts / Radios ---
        {"type": "podcast", "platform": "Podcast", "url": "https://www.thinkerview.com/feed/podcast/", "name": "Thinkerview (Podcast)"},
        {"type": "podcast", "platform": "France Info", "url": "https://radiofrance-podcast.net/podcast09/rss_14088.xml", "name": "Les Informés"},
        {"type": "podcast", "platform": "France Culture", "url": "https://radiofrance-podcast.net/podcast09/rss_10076.xml", "name": "Entendez-vous l’éco ?"},
        {"type": "podcast", "platform": "France Culture", "url": "https://radiofrance-podcast.net/podcast09/rss_10322.xml", "name": "La Grande Table"},
        {"type": "podcast", "platform": "France Culture", "url": "https://radiofrance-podcast.net/podcast09/rss_14312.xml", "name": "Cultures Monde"},

        # --- Revues académiques ---
        {"type": "rss", "platform": "Cairn", "url": "https://shs.cairn.info/rss/discipline/11/numeros/3?lang=fr", "name": "Sociologie"},
        {"type": "rss", "platform": "Cairn", "url": "https://shs.cairn.info/rss/revue/RFS?lang=fr", "name": "Revue Française de Sociologie"},
        {"type": "rss", "platform": "Cairn", "url": "https://shs.cairn.info/rss/revue/rce?lang=fr", "name": "Regards Croisés sur l’Économie"},
        {"type": "rss", "platform": "Cairn", "url": "https://shs.cairn.info/rss/revue/ARSS?lang=fr", "name": "Actes de la recherche en sciences sociales"},
        {"type": "rss", "platform": "Esprit", "url": "https://esprit.presse.fr/rss/news", "name": "Esprit"},
        {"type": "rss", "platform": "La Vie des Idées", "url": "https://laviedesidees.fr/spip.php?page=backend", "name": "La Vie des Idées"},
        {"type": "rss", "platform": "Reporterre", "url": "https://reporterre.net/spip.php?page=backend", "name": "Reporterre"},

        # --- Bluesky (microblog) ---
        {"type": "rss", "platform": "Bluesky", "url": "https://bsky.app/profile/thomaspiketty.bsky.social/rss", "name": "Thomas Piketty"},
        {"type": "rss", "platform": "Bluesky", "url": "https://bsky.app/profile/gabrielzucman.bsky.social/rss", "name": "Gabriel Zucman"},
        {"type": "rss", "platform": "Bluesky", "url": "https://bsky.app/profile/francoisruffin.fr/rss", "name": "François Ruffin"},
        {"type": "rss", "platform": "Bluesky", "url": "https://bsky.app/profile/manonaubryfr.bsky.social/rss", "name": "Manon Aubry"},
        {"type": "rss", "platform": "Bluesky", "url": "https://bsky.app/profile/aurorelalucq.bsky.social/rss", "name": "Aurore Lalucq"},
    ]

    for src in sources:
        if src["type"] == "rss":
            items = adapter_rss(src["url"], src["name"], src["platform"], default_type="ARTICLE")
        elif src["type"] == "podcast":
            items = adapter_podcast(src["url"], src["name"], src["platform"])
        else:
            continue

        for item in items:
            if scan_pertinence(item):
                save_to_db(session, item)

    print("✅ Worker terminé : contenus agrégés et stockés.")

# ======================================================
# 8) AFFICHAGE (CLI + Streamlit)
# ======================================================
def _format_datetime(dt) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")

def _render_avatar_html(avatar_url: str | None, size: int = 48):
    if not avatar_url:
        return f'<div style="width:{size}px;height:{size}px;border-radius:50%;background:#ddd;"></div>'
    return (f'<img src="{avatar_url}" alt="avatar" '
            f'style="width:{size}px;height:{size}px;border-radius:50%;object-fit:cover;" />')

def _format_handle(handle: str | None) -> str:
    if not handle:
        return ""
    return handle if handle.startswith("@") else f"@{handle}"

def show_feed_python():
    session = SessionLocal()
    order_clause = (
        case((Content.published_at.is_(None), 1), else_=0).asc(),
        Content.published_at.desc()
    )
    items = session.query(Content).order_by(*order_clause).limit(200).all()

    print("\n=== Mon Feed ===\n")
    for item in items:
        print(f"[{item.source}] · {_format_datetime(item.published_at)} · {item.type}")
        if item.type == "TWEET":
            print(item.description[:280] + ("..." if item.description and len(item.description) > 280 else ""))
            if item.author_name or item.author_handle:
                print(f"— {item.author_name or ''} { _format_handle(item.author_handle) }")
        else:
            if item.title:
                print(item.title)
            if item.description:
                print(item.description[:160] + ("..." if len(item.description) > 160 else ""))
        if item.image_url:
            print(f"(image) {item.image_url}")
        print(item.url)
        print("-" * 50)

# --- Streamlit ---
import streamlit as st

def render_tweet_st(item):
    col1, col2 = st.columns([1, 9], gap="small")
    with col1:
        st.markdown(_render_avatar_html(item.author_avatar_url or None, size=48), unsafe_allow_html=True)
    with col2:
        name = item.author_name or item.source or "Auteur"
        handle = _format_handle(item.author_handle or None)
        time_txt = _format_datetime(item.published_at)
        st.markdown(
            f"<div style='font-weight:600; display:inline;'>{name}</div> "
            f"<span style='color:#6b7280;'>{handle} · {time_txt}</span>",
            unsafe_allow_html=True
        )
        if item.description:
            st.write(item.description)
        if item.image_url:
            st.image(item.image_url, use_column_width=True)
        st.markdown(f"[Ouvrir le post]({item.url})")

def show_feed_streamlit():
    session = SessionLocal()
    order_clause = (
        case((Content.published_at.is_(None), 1), else_=0).asc(),
        Content.published_at.desc()
    )
    items = session.query(Content).order_by(*order_clause).limit(200).all()

    st.title("📱 Mon Feed")

    for item in items:
        if item.type == "TWEET":
            render_tweet_st(item)
        else:
            if item.image_url:
                st.image(item.image_url, use_column_width=True)
            meta = f"[{item.source}] · {_format_datetime(item.published_at)} · {item.type}"
            if item.title:
                st.subheader(item.title)
            st.caption(meta)
            if item.description:
                st.write(item.description)
            st.markdown(f"[Lien vers la source]({item.url})")
        st.divider()

# ======================================================
# 9) BACKFILL IMAGES / AVATARS (optionnel)
# ======================================================
def backfill_missing_images(batch_size: int = 100):
    """
    Parcourt les contenus sans image_url et tente d'en trouver une.
    """
    session = SessionLocal()
    try:
        offset = 0
        total_updated = 0
        while True:
            rows = (
                session.query(Content)
                .filter((Content.image_url.is_(None)) | (Content.image_url == ""))
                .order_by(Content.id.asc())
                .limit(batch_size)
                .offset(offset)
                .all()
            )
            if not rows:
                break
            for item in rows:
                img = extract_image_from_entry(entry={}, base_link=item.url, allow_scrape=True)
                if img:
                    item.image_url = img
                    total_updated += 1
            session.commit()
            offset += batch_size
        print(f"✅ Backfill images terminé. {total_updated} lignes mises à jour.")
    finally:
        session.close()

def backfill_tweet_avatars(batch_size: int = 100):
    """
    Remplit author_avatar_url/author_handle pour les TWEET manquants.
    """
    session = SessionLocal()
    try:
        q = (
            session.query(Content)
            .filter(Content.type == "TWEET")
            .filter((Content.author_avatar_url.is_(None)) | (Content.author_avatar_url == ""))
            .order_by(Content.id.asc())
        )
        updated = 0
        for row in q.yield_per(batch_size):
            handle = row.author_handle
            if not handle:
                try:
                    u = urlparse(row.url)
                    if "bsky.app" in u.netloc and "/profile/" in u.path:
                        parts = u.path.split("/")
                        if len(parts) > 2:
                            handle = parts[2]
                            row.author_handle = handle
                except Exception:
                    pass
            avatar = fetch_bluesky_avatar_url(handle) if handle else None
            if avatar:
                row.author_avatar_url = avatar
                updated += 1
        session.commit()
        print(f"✅ Backfill avatars terminé ({updated} lignes).")
    finally:
        session.close()

# ======================================================
# 10) MAIN (flags)
# ======================================================
if __name__ == "__main__":
    RUN_WORKER = True            # True pour lancer l’ingestion
    RUN_BACKFILL_IMAGES = False  # True (une fois) pour remplir images manquantes
    RUN_BACKFILL_AVATARS = False # True (une fois) pour remplir avatars manquants
    RUN_STREAMLIT = False        # True pour démarrer l’UI avec Streamlit (voir commande ci-dessous)

    if RUN_WORKER:
        run_worker()
    if RUN_BACKFILL_IMAGES:
        backfill_missing_images()
    if RUN_BACKFILL_AVATARS:
        backfill_tweet_avatars()
    if RUN_STREAMLIT:
        show_feed_streamlit()
