"""
Worker Python : cycle complet
Sources -> Adapters -> Pertinence -> DB (PostgreSQL avec SQLAlchemy)
"""
from datetime import datetime
import feedparser
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# ======================================================
# 1. Connexion DB & Modèle Content
# ======================================================

# Connexion PostgreSQL (adapter la chaîne avec ton user/mdp/host/dbname)
engine = create_engine("sqlite:///mydb.db")
#engine = create_engine("postgresql+psycopg2://user:password@localhost:5432/mydb")
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


Base.metadata.create_all(bind=engine) # crée la table si non existante


# ======================================================
# 2. Adapters
# ======================================================
# Un parser prend des données brutes hétérogènes (RSS/JSON/HTML) en entrée et renvoie une liste d’objets Content normalisés prêts à être stockés 
# ici les objets contents sont "une vidéo", un article
# le parser renvoie une liste de contenu indexé 

def adapter_rss(source_url: str, source_name: str, source_platform:str, content_type: str = "ARTICLE"):
    """
    Adapter générique pour flux RSS (Blast, Cairn, France Info).
    Transforme les items RSS en objets Content-like (dicts).
    """
    feed = feedparser.parse(source_url)
    contents = []
    for entry in feed.entries:
        contents.append({
            "type": content_type,
            "title": entry.get("title"),
            "url": entry.get("link"),
            "description": entry.get("summary", ""),
            "published_at": datetime(*entry.published_parsed[:6]) if "published_parsed" in entry else None,
            "source": source_name,
            "platform": source_platform
        })
    return contents


def adapter_podcast(source_url: str, source_name: str):
    """
    Adapter spécifique podcasts (RSS aussi).
    Extrait en plus l'URL du fichier audio.
    """
    feed = feedparser.parse(source_url)
    contents = []
    for entry in feed.entries:
        audio_url = entry.enclosures[0].href if entry.enclosures else None
        contents.append({
            "type": "PODCAST",
            "title": entry.get("title"),
            "url": entry.get("link"),
            "description": entry.get("summary", ""),
            "published_at": datetime(*entry.published_parsed[:6]) if "published_parsed" in entry else None,
            "audio_url": audio_url,
            "source": source_name,
        })
    return contents


# ======================================================
# 3. Pertinence
# ======================================================

def scan_pertinence(item: dict) -> bool:
    """
    Règles simples de pertinence :
    - summary ou description non vide
    - URL non vide
    """
    # Vérifie que summary ou description existent et ne sont pas vides
    content = item.get("summary") or item.get("description")
    if not content or len(content.strip()) < 10:
        return False

    # Vérifie que l'URL existe
    if not item.get("url"):
        return False

    return True



# ======================================================
# 4. Sauvegarde DB
# ======================================================

def save_to_db(session, item: dict):
    """
    Sauvegarde un item dans PostgreSQL s’il est pertinent.
    Utilise SQLAlchemy ORM.
    """
    # Vérifie si l’URL existe déjà (évite les doublons)
    exists = session.query(Content).filter_by(url=item["url"]).first()
    if exists:
        return

    content = Content(
        url=item["url"],
        title=item["title"],
        type=item["type"],
        description=item.get("description"),
        published_at=item.get("published_at"),
        source=item["source"],
        platform=item["platform"]
    )
    session.add(content)
    session.commit()


# ======================================================
# 5. Orchestrateur du worker
# ======================================================

def run_worker():
    """
    Boucle principale du worker :
    - lit les sources configurées
    - appelle l’adapter approprié
    - filtre les items
    - sauvegarde en base
    """
    session = SessionLocal()

    # Liste des sources à agréger
  
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
    {"type": "rss", "platform": "Thinkerview", "url": "https://www.thinkerview.com/feed/podcast/", "name": "Thinkerview (Podcast)"},
    {"type": "rss", "platform": "France Info", "url": "https://radiofrance-podcast.net/podcast09/rss_14088.xml", "name": "Les Informés"},
    {"type": "rss", "platform": "France Culture", "url": "https://radiofrance-podcast.net/podcast09/rss_10076.xml", "name": "Entendez-vous l’éco ?"},
    {"type": "rss", "platform": "France Culture", "url": "https://radiofrance-podcast.net/podcast09/rss_10322.xml", "name": "La Grande Table"},
    {"type": "rss", "platform": "France Culture", "url": "https://radiofrance-podcast.net/podcast09/rss_14312.xml", "name": "Cultures Monde"},

    # --- Revues académiques ---
    {"type": "rss", "platform": "Cairn", "url": "https://shs.cairn.info/rss/discipline/11/numeros/3?lang=fr", "name": "Sociologie"},
    {"type": "rss", "platform": "Cairn", "url": "https://shs.cairn.info/rss/revue/RFS?lang=fr", "name": "Revue Française de Sociologie"},
    {"type": "rss", "platform": "Cairn", "url": "https://shs.cairn.info/rss/revue/rce?lang=fr", "name": "Regards Croisés sur l’Économie"},
    {"type": "rss", "platform": "Cairn", "url": "https://shs.cairn.info/rss/revue/ARSS?lang=fr", "name": "Actes de la recherche en sciences sociales"},
    {"type": "rss", "platform": "Esprit", "url": "https://esprit.presse.fr/rss/news", "name": "Esprit"},
    {"type": "rss", "platform": "La Vie des Idées", "url": "https://laviedesidees.fr/spip.php?page=backend", "name": "La Vie des Idées"},
    {"type": "rss", "platform": "Reporterre", "url": "https://reporterre.net/spip.php?page=backend", "name": "Reporterre"},

    # --- Bluesky (via Nitter) ---
    {"type": "rss", "platform": "Bluesky", "url": "https://bsky.app/profile/thomaspiketty.bsky.social/rss", "name": "Thomas Piketty"},
    {"type": "rss", "platform": "Bluesky", "url": "https://bsky.app/profile/gabrielzucman.bsky.social/rss", "name": "Gabriel Zucman"},
    {"type": "rss", "platform": "Bluesky", "url": "https://bsky.app/profile/francoisruffin.fr/rss", "name": "François Ruffin"},
    {"type": "rss", "platform": "Bluesky", "url": "https://bsky.app/profile/manonaubryfr.bsky.social/rss", "name": "Manon Aubry"},
    {"type": "rss", "platform": "Bluesky", "url": "https://bsky.app/profile/aurorelalucq.bsky.social/rss", "name": "Aurore Lalucq"},

    ]

    for src in sources:
        # Sélectionne l’adapter en fonction du type, ici items est la liste complète des contenus  
        if src["type"] == "rss":
            items = adapter_rss(src["url"], src["name"], src["platform"], content_type="ARTICLE")
        elif src["type"] == "podcast":
            items = adapter_podcast(src["url"], src["name"])
        else:
            continue

        # Pour chaque item, appliquer pertinence + sauvegarde, on prend un contenu dans la liste complète des contenus et on l'enregistre ou non 
        for item in items:
            if scan_pertinence(item):
                save_to_db(session, item)

    print("✅ Worker terminé : contenus agrégés et stockés.")


# ======================================================
# 6. Lancement
# ======================================================
if __name__ == "__main__":
    run_worker()

def show_feed_python():
    session = SessionLocal()
    # on récupère les 20 derniers contenus
    items = session.query(Content).order_by(Content.published_at.desc()).limit(500).all()
    
    print("\n=== Mon Feed ===\n")
    for item in items:

        print(f"{item.description[:500]}...")

        print(f"[{item.source}] · {item.published_at}")
        print(f"{item.title}")
        if item.description:
            print(f"{item.description[:100]}...")
        print(f"{item.url}\n")
        print("-" * 50)

import streamlit as st


def show_feed_streamlit():
    session = SessionLocal()
    items = session.query(Content).filter(Content.source =="Thomas Piketty").order_by(Content.published_at.desc()).limit(500).all()
    #on ouvre Content qui est la vrai base de donnée
    st.title("📱 Mon Feed")

    for item in items:

        st.subheader(item.title)
        st.caption(f"[{item.source}] · {item.published_at}")
        if item.description:
            st.write(item.description[:500] + "...")
        
        st.markdown(f"[Lien vers la source]({item.url})")
        st.divider()

if __name__ == "__main__":
    show_feed_streamlit()
