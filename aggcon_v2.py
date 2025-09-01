"""
📌 Git pense-bête

4. Récupérer les changements depuis GitHub :
   git pull origin master   # ou git pull origin main
1. Ajouter tous les fichiers modifiés :
   git add -A

2. Créer un commit avec un message :
   git commit -m "Description de mes changements"

3. Envoyer sur GitHub :
   git push origin master   # ou git push origin main


"""


from datetime import datetime
import re
import html
import time
import feedparser
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from tqdm import tqdm
import json
import math 
from itertools import islice
from typing import Optional, List, Dict
from pathlib import Path

data_file = Path(__file__).parent / "sources_actuelles.json"
print(data_file)

RUN_WORKER = False            # mets True si tu veux relancer l’ingestion
RUN_BACKFILL_IMAGES = False    # <-- lance une fois pour remplir les images manquantes
RUN_STREAMLIT = True         # True si tu veux démarrer l'UI immédiatement
RECREATE_DB = False  # set True if you want to drop and recreate the database

from scoring import (
    get_counts_last_days_by_source,
    rank_items,
    base_score
)

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# ======================================================
# 1. Connexion DB & Modèle Content
# ======================================================

# engine = create_engine("postgresql+psycopg2://user:password@localhost:5432/mydb")
# construit le chemin complet vers mydb.db (au même niveau que ce script)
db_file = Path(__file__).parent / "mydb.db"

# crée l’engine SQLite avec le chemin absolu
engine = create_engine(f"sqlite:///{db_file}")
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Content(Base):
    """
    Table qui stocke tous les contenus agrégés.
    """
    __tablename__ = "contents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, unique=True, nullable=False)  # lien vers le contenu original
    title = Column(String, nullable=True)
    type = Column(String, nullable=False)              # ARTICLE, PODCAST, VIDEO, TWEET, etc.
    description = Column(Text)
    published_at = Column(DateTime)
    source = Column(String, nullable=False)            # nom de la source
    platform = Column(String, nullable=False)
    image_url = Column(String, nullable=True)          # <-- NOUVEAU : image représentative
    institution_logo_url = Column(String, nullable=True)          # <-- NOUVEAU : image représentative
    profile_image_url = Column(String, nullable=True)          # <-- NOUVEAU : photo de profil
    language = Column(String, nullable=True)          # <-- NOUVEAU : photo de profil



if RECREATE_DB:
    Base.metadata.drop_all(bind=engine)   # deletes all tables (schema only, not the .db file)
    Base.metadata.create_all(bind=engine) # rebuilds them fresh
else:
    Base.metadata.create_all(bind=engine) # only creates missing tables

# ======================================================
# 2. Utilitaires : nettoyage & images
# ======================================================


# --- Headers réseau plus "réalistes"
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

# --- Utilitaires HTML ---
WHITESPACE_RE = re.compile(r"\s+")

def contains_html(text: str) -> bool:
    if not text:
        return False
    soup = BeautifulSoup(text, "html.parser")
    return bool(soup.find())  # True s’il y a au moins une balise

def strip_html(text: str) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
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
    ent_ratio = s.count("&")
    return lt_ratio > 10 or ent_ratio > 30

def pick_first_nonempty(*candidates):
    for c in candidates:
        if c and str(c).strip():
            return str(c).strip()
    return ""

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


def truncate(text, max_length=280):
    if not text:
        return ""
    return text if len(text) <= max_length else text[:max_length] + "..."

from datetime import datetime
from dateutil import parser

def extract_entry_published(entry):
    """
    Extrait une date d'un item RSS/Atom-like en essayant, dans l'ordre :
      1) published_parsed (chaîne)
      2) updated_parsed   (chaîne)
      3) date             (chaîne)

    Retourne un objet datetime ou None.
    """
    for key in ("published_parsed", "updated_parsed", "date"):
        value = entry.get(key) if isinstance(entry, dict) else getattr(entry, key, None)
        if isinstance(value, str):
            try:
                return parser.parse(value)
            except Exception:
                pass
    return None


def _first_plausible_img_from_soup(soup, base_link: str):
    # Rechercher d'abord meta OG/Twitter
    og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
    if og and og.get("content"):
        return urljoin(base_link, og["content"])
    tw = soup.find("meta", property="twitter:image") or soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        return urljoin(base_link, tw["content"])

    # Ensuite <img> plausibles (src, data-src, srcset)
    for img in soup.find_all("img"):
        # srcset prioritaire si présent
        srcset = img.get("srcset", "") or img.get("data-srcset", "")
        candidate = ""
        if srcset:
            # prendre la première URL du srcset
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


from parser_profile_image_test import extract_profile_image
from parser_logo_image_test import extract_logo_institution


def extract_image_from_entry(entry, base_link: str | None):
    """
    Ordre:
      1) Champs RSS (media:thumbnail, media:content, enclosures)
      2) Fallback YouTube (si lien YT)
      3) Scrape de la page (OG/Twitter, puis première <img> plausible)
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

    # 2) Fallback YouTube (beaucoup de flux donnent un lien watch sans media_thumbnail)
    if base_link:
        yt_id = _youtube_id_from_url(base_link)
        if yt_id:
            return f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg"

    # 3) Scrape
    if not base_link:
        return None
    try:
        resp = requests.get(base_link, headers=HTTP_HEADERS, timeout=10)
        if resp.status_code != 200 or not resp.text:
            print(f"[image] GET {base_link} -> {resp.status_code}")
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        img = _first_plausible_img_from_soup(soup, base_link)
        if not img:
            print(f"[image] Aucune image plausible trouvée sur {base_link}")
        return img
    except requests.RequestException as e:
        print(f"[image] Erreur réseau {base_link}: {e}")
        return None
    except Exception as e:
        print(f"[image] Erreur parsing {base_link}: {e}")
        return None

def infer_visualization_from_platform(
    title: str,
    platform: str,
    link: str,
    category: str = None
) -> str:
    """
    Retourne le type de visualisation à appliquer en fonction de la plateforme/source.
    Si une catégorie valide est déjà fournie en input, elle est prioritaire.
    """

    # Liste des catégories possibles
    valid_categories = {
        "video", "podcast_audio", "card_tweet", "presse",
        "académique", "rapport", "forum", "expo_live", "dataviz"
    }

    # --- PRIORITÉ À category si valide ---
    if category and category in valid_categories:
        return category

    # Normalisation
    title = (title or "").lower()
    platform = (platform or "").lower()
    link = (link or "").lower()
    text = " ".join([title, platform, link])

    # --- VIDEO ---
    if any(k in text for k in {"youtube", "vimeo", "dailymotion", "ted", "thinkerview", "datagueule"}):
        return "video"

    # --- PODCAST AUDIO ---
    if any(k in text for k in {"spotify", "apple podcast", "deezer", "soundcloud", "france culture", "podcast"}):
        return "podcast_audio"

    # --- TWEETS / MICRO-POSTS ---
    if any(k in text for k in {"twitter", "x.com", "mastodon", "bluesky"}):
        return "card_tweet"

    # --- PRESSE / JOURNALISME ---
    if any(k in text for k in {"le monde", "figaro", "guardian", "nytimes",
                               "alternatives économiques", "slate", "mediapart",
                               "libération", "reporterre", "public sénat"}):
        return "presse"

    # --- ARTICLES ACADÉMIQUES ---
    if any(k in text for k in {"cairn", "jstor", "hal", "persee", "revue",
                               "econometrica", "nature", "science direct",
                               "hypotheses", "la vie des idées", "esprit"}):
        return "académique"

    # --- RAPPORTS / THINK TANKS / INSTITUTIONS ---
    if any(k in text for k in {"ocde", "fmi", "imf", "banque mondiale", "onu",
                               "institut montaigne", "ofce", "ifri", "terra nova",
                               "banque de france", "commission européenne", "ec.europa",
                               "senat", "assemblée nationale", "attac"}):
        return "rapport"

    # --- FORUMS / COMMUNAUTÉS ---
    if any(k in text for k in {"reddit", "stackexchange", "quora", "forum", "h-net"}):
        return "forum"

    # --- EXPOSITIONS / SPECTACLE VIVANT ---
    if any(k in text for k in {"centre pompidou", "avignon", "collège de france", "moma", "exposition", "festival"}):
        return "expo_live"

    # --- DONNÉES / DATAVIZ ---
    if any(k in text for k in {"our world in data", "nytimes data", "gapminder",
                               "data.gouv", "visualisation", "interactive chart"}):
        return "dataviz"

    # --- FALLBACK ---
    return "presse"




def best_description_for_entry(entry, page_url: str | None):
    #on cherche si c'est déjà bien indiqué
    #fonction in line, getattr permet de tester si les différents attributs, summary, description sont vides 
    rss_summary_html = pick_first_nonempty(
        getattr(entry, "summary", None),
        getattr(entry, "description", None),
        (entry.content[0].value if getattr(entry, "content", None) else None),
    )

    
    #si on trouve qqch et que c'est pas du HTML on le renvoie
    if rss_summary_html and not looks_like_code_garbage(rss_summary_html):
        return strip_html(rss_summary_html)[:2000]
    
    #si on trouve rien on utilise directement sur la page web 

    if page_url:
        try:
            #on télécharge la page web  
            resp = requests.get(page_url, headers=HTTP_HEADERS, timeout=10)

            #si la page se lance bien et qu'il y a du texte   
            if resp.status_code == 200 and resp.text:
                soup = BeautifulSoup(resp.text, "html.parser")

                #on essaye de chercehr des métadonnées pertinentes dans le code HTML
                og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
                if og_desc and og_desc.get("content"):
                    return strip_html(og_desc["content"])[:2000]
                
                #sinon on essaye de prendre n'importe quel paragraphe 
                for p in soup.find_all("p"):
                    txt = strip_html(p.get_text(" ", strip=True))
                    if len(txt) > 80:
                        return txt[:2000]
        except Exception:
            pass

    
    return strip_html(rss_summary_html)[:2000]


# ===============================
#  TITRES : exceptions simples
# ===============================

TITLE_RULES = {
    # --- par nom de source exact ---
    "OEIL": {"use": "summary"},
}

TITLE_MAX = 160

from urllib.parse import urlparse

def _clean(s: str | None) -> str:
    if not s:
        return ""
    t = strip_html(str(s))
    t = WHITESPACE_RE.sub(" ", t).strip()
    return t[:TITLE_MAX]

def _summary_text(entry):
    # summary/description/content -> premier non vide
    return (
        getattr(entry, "summary", None)
        or getattr(entry, "description", None)
        or (entry.content[0].value if getattr(entry, "content", None) else None)
        or ""
    )

def _domain(url: str | None) -> str:
    try:
        return urlparse(url or "").netloc.lower()
    except Exception:
        return ""

def _page_title(url: str | None) -> str:
    if not url:
        return ""
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=8)
        if r.status_code != 200 or not r.text:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        og = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
        if og and og.get("content"):
            return _clean(og["content"])
        if soup.title and soup.title.string:
            return _clean(soup.title.string)
        h1 = soup.find("h1")
        if h1:
            return _clean(h1.get_text(" ", strip=True))
    except Exception:
        pass
    return ""

def _find_rule(source_name: str | None, link: str | None):
    # priorité : source exacte > domaine
    if source_name and source_name in TITLE_RULES:
        return TITLE_RULES[source_name]
    dom = _domain(link)
    if dom:
        for k, v in TITLE_RULES.items():
            if k.startswith("@domain:") and k.split(":", 1)[1] in dom:
                return v
    return None

def choose_title(entry, link: str | None, source_name: str | None) -> str | None:
    rule = _find_rule(source_name, link)

    if rule:
        use = rule.get("use", "summary")

        if use == "title":
            t = _clean(getattr(entry, "title", None) or (entry.get("title") if isinstance(entry, dict) else None))
        elif use == "summary":
            t = _clean(_summary_text(entry))
        elif use == "summary_if_empty":
            t = _clean(getattr(entry, "title", None) or (entry.get("title") if isinstance(entry, dict) else None))
            if not t:
                t = _clean(_summary_text(entry))
        elif use == "page":
            t = _page_title(link)
        else:
            t = _clean(_summary_text(entry))

        # petites corrections post-traitement
        for pat, repl in rule.get("regex", []) or []:
            t = re.sub(pat, repl, t)

        return t or None

    # défaut (aucune règle) : title sinon summary
    t = _clean(getattr(entry, "title", None) or (entry.get("title") if isinstance(entry, dict) else None))
    if not t:
        t = _clean(_summary_text(entry))
    return t or None


# ------------------ BACKFILL IMAGES (exécuter une fois) ------------------
def backfill_missing_images(SessionLocal, Content, batch_size: int = 100):
    """
    Parcourt les contenus sans image_url et tente d'en trouver une.
    Lance-le après avoir peuplé la base.
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
                img = extract_image_from_entry(
                    entry={},  # pas de RSS ici, on reconstruit depuis la page
                    base_link=item.url,
                )
                if img:
                    item.image_url = img
                    total_updated += 1
            session.commit()
            offset += batch_size

        print(f"✅ Backfill terminé. {total_updated} lignes mises à jour avec image_url.")
    finally:
        session.close()
# =================== FIN PATCH IMAGES ===================

# ======================================================
# 3. Adapters
# ======================================================

def adapter_rss(source_url: str, source_name: str, source_platform: str, default_type: str = "ARTICLE", category: str=None,     max_posts: Optional[int] = None,  # << NEW: limite d'items
):
    """
    Adapter générique pour flux RSS/Atom.
    - Nettoie descriptions “sales”
    - Déduit le type
    - Tente de récupérer une image pertinente (RSS ou page)
    """
    feed = feedparser.parse(source_url)
    contents = []

    entries_iter = (
        feed.entries if not max_posts or max_posts < 1
        else islice(feed.entries, int(max_posts))
    )
    
    #Prend un feed, le décompose en feed.feed (info générale) feed.entries 
    #Prend chaque entrée, extrait les différentes caractéristiques 
    for entry in entries_iter:
        #et les enregistre dans les variables temporaires  ci-dessous

        link = entry.get("link")
        pub = extract_entry_published(entry)
        inferred_type = infer_visualization_from_platform(entry.get("title"), source_platform, link, category)
        desc = best_description_for_entry(entry, link)
        
        #exclusion des sources sans images 
        if source_name == "OEIL":
            img = None
        else:
            img = extract_image_from_entry(entry, link)

        #exclusion des sources sans photo de profils càd tout sauf les tweets
        if category != "tweet":
            pfp = None
        else:
            pfp = extract_profile_image(entry, link)

        #exclusion des sources sans logo càd tout sauf les rapports
        if category != "rapport":
            logo = None
        else:
            logo = extract_logo_institution(
                entry=entry,
                base_link=link,
                fallback_url="https://upload.wikimedia.org/wikipedia/commons/6/65/No-Image-Placeholder.svg",
                google_api_key="AIzaSyAW0z5kTEXvQzpJcCAEkzmzGD16tyzNc6Y",
                google_cx="c58a6887ca71e4e4c",
                force_refresh=False)

        print(logo)
        contents.append({
            "type": inferred_type or default_type,
            "title" : choose_title(entry, link, source_name),
            "url": link,
            "description": desc,
            "published_at": pub,
            "source": source_name,
            "platform": source_platform,
            "image_url": img,
            "institution_logo_url":logo,
            "profile_image_url" : pfp
        })
    return contents



# ======================================================
# 4. Pertinence
# ======================================================

def scan_pertinence(item: dict) -> bool:
    """
    Règles simples de pertinence :
    - description non vide et informative
    - URL non vide
    """
    content = item.get("description")
    if not content or len(content.strip()) < 10:
        return False
    if not item.get("url"):
        return False
    return True


# ======================================================
# 5. Sauvegarde DB
# ======================================================

def save_to_db(session, item: dict):
    """
    Sauvegarde un item dans la DB s’il est pertinent.
    """
    exists = session.query(Content).filter_by(url=item["url"]).first()
    #vérifie s'il y a déjà une ligne qui existe
    if exists:
        # Option: on peut mettre à jour image/description si vides
        updated = False
        if not exists.image_url and item.get("image_url"):
            exists.image_url = item["image_url"]
            updated = True
        if (not exists.description or len(exists.description) < 50) and item.get("description"):
            exists.description = item["description"]
            updated = True
        if not exists.published_at and item.get("published_at"):
            exists.published_at = item["published_at"]
            updated = True

        if contains_html(exists.description) :
            exists.description = item["description"]
            updated = True

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
        institution_logo_url=item.get("institution_logo_url"),
        profile_image_url =item.get("profile_image_url"),
        language =None
    )
    session.add(content)
    session.commit()


# ======================================================
# 6. Orchestrateur du worker
# ======================================================

def run_worker():
    """
    Boucle principale du worker :
    - lit les sources configurées
    - appelle l’adapter
    - filtre les items
    - sauvegarde en base
    """
    session = SessionLocal()
    #---------------------------------Importe les sources qui sont une liste de dictionnaire, avec notamment les liens RSS-----------------------
    with open(data_file, encoding="utf-8") as f:
        sources = json.load(f)
    #----------------------------------------------------------------------------------------



    #---------------------------MESURE DU TEMPS -----------------
    #rappel tqdm c'est pour mesurer le temps de l'itération, avec desc la description de la barre de progression, il sert d'itérateur 
    bar = tqdm(sources, desc="Avancée générale")
    timings = []
    #---------------------------MESURE DU TEMPS -----------------

    for src in bar:

        #---------------------------MESURE DU TEMPS -----------------
        bar.set_description(f"Avancée générale (on en est à {src['name']})")
        start = time.perf_counter()
        #---------------------------MESURE DU TEMPS -----------------


        items = adapter_rss(
    source_url=src["url"],
    source_name=src["name"],
    source_platform=src["platform"],
    default_type="ARTICLE",
    category=src["category"],
    max_posts=5
)

        
        for item in items:
            if scan_pertinence(item):
                save_to_db(session, item)
        
        end = time.perf_counter()

        #timings est une liste de couple ("Thinkerview", 20s)
        timings.append((src["name"], end - start))
        #--------------------------------------------------

    #---------------------------MESURE DU TEMPS -----------------
    print("\n🐢 Top 5 :")
    for name, dt in sorted(timings, key=lambda x: x[1], reverse=True)[:5]:
        print(f"- {name}: {dt:.2f}s")
    #--------------------------------------------------


    print("✅ Worker terminé : contenus agrégés et stockés.")


# ======================================================
# 7. Affichages
# ======================================================
def show_feed_python():
    session = SessionLocal()
    items = session.query(Content).order_by(Content.published_at.desc().nullslast()).limit(30).all()
    
    print("\n=== Mon Feed ===\n")
    for item in items:
        # Affichage dynamique
        print(f"[{item.source}] · {item.published_at} · {item.type}")
        if item.type == "TWEET":
            # Pas de titre pour microblogging
            print(item.description[:280] + ("..." if len(item.description) > 280 else ""))
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
from style import COMPONENT_CSS, render_item


def show_feed_streamlit():
    session = SessionLocal()
    st.title("📱 Mon Feed")

#-----------Choix de plateforme --------------------
    platforms_list = sorted({s["platform"] for s in json.load(open(data_file, encoding="utf-8"))})
    platform_choice = st.selectbox(
    "Choisir une plateforme",
    options=["Toutes"]+platforms_list)

    from sqlalchemy import or_

    if platform_choice == "Toutes":
        items = session.query(Content).filter(
        ~Content.source.in_(["franceinfo", "Le Monde (YouTube)", "Le Monde - À la Une", "PoliticalDiscussion", "AskSocialScience"]),
        or_(Content.platform.is_(None), Content.platform != "France Culture"),
        ).order_by(Content.published_at.desc().nullslast()).limit(200).all()
    else:
        items = session.query(Content).filter(Content.platform == platform_choice).order_by(Content.published_at.desc().nullslast()).limit(200).all()
#-------------------------------------------------------------------------------------

##----------- Classement aléatoire ---------------------------------------------------

    # 1) compte par source sur 7j
    counts = get_counts_last_days_by_source(session, Content)

    # 2) scoring + jitter + top 200
    final_items = rank_items(items, counts, top_k=200)

##----------------Affichage--------------------
    
    #sélectionne le parser à adopter, le parser prend un lien et renvoie 
    #une liste d'item déjà formatté
    #"type": inferred_type or default_type,
    #"title": entry.get("title"),
    #"url": link,
    #"description": desc,
    #"published_at": pub,
    #"source": source_name,
    #"platform": source_platform,
    #"image_url": img,
    
    st.markdown(f"<style>{COMPONENT_CSS}</style>", unsafe_allow_html=True)

    for item in final_items:
        
        # Image en tête si dispo

        render_item(st, item)

        
from sqlalchemy import inspect, text, case   # ajoute ces imports
# ======================================================
# Après Base.metadata.create_all(bind=engine)
# ======================================================

def ensure_schema():
    """
    Vérifie que la table 'contents' contient bien la colonne image_url.
    Si elle n'existe pas (SQLite), on l'ajoute.
    """
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("contents")]
    if "image_url" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE contents ADD COLUMN image_url VARCHAR"))
        print("✅ Colonne 'image_url' ajoutée à la table 'contents'.")

# appelle la fonction juste après la création du schéma
Base.metadata.create_all(bind=engine)
ensure_schema()
# ======================================================
# CODE LANCE

if __name__ == "__main__":

    if RUN_WORKER:
        run_worker()

    if RUN_BACKFILL_IMAGES:
        backfill_missing_images(SessionLocal, Content)

    if RUN_STREAMLIT:
        show_feed_streamlit()


