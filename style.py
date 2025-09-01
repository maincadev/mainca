from pathlib import Path
from datetime import datetime
import base64

# =========================
# CSS (scopé aux composants)
# =========================
COMPONENT_CSS = """
.block-container { padding: 12px 12px 28px; max-width: 1600px; }

/* ===== THEMES ===== */
:root {
  --bg-light: #f7f6f3;
  --bg-dark: #0d1117;
  --card-light: #fff;
  --card-dark: #161b22;
  --text-light: #0b0b0b;
  --text-dark: #e6edf3;
  --meta-light: #6b7280;
  --meta-dark: #9ca3af;
  --accent: #3b82f6;

  /* Sécurise la typo si non définie ailleurs */
  --serif: Georgia, 'Times New Roman', serif;
  --sans:  system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
}

/* Mode clair par défaut */
html, body, .stApp {
  background: var(--bg-light);
  color: var(--text-light);
}



/* Appliquer .dark-mode sur <html> pour basculer en sombre */
html.dark-mode, html.dark-mode body, html.dark-mode .stApp {
  background: var(--bg-dark) !important;
  color: var(--text-dark) !important;
}

.block-container {
        max-width: 800px;   /* largeur max de ta colonne */
        margin: 0 auto;     /* centre horizontalement */
    }

/* Cartes */
.card{
  background: var(--card-light);
  border:none; border-radius:6px;
  box-shadow:0 2px 10px rgba(0,0,0,.06);
  padding:16px; margin:12px 0;
  transition:box-shadow .2s ease, transform .2s ease, background .2s ease, border-left-color .2s ease;
  border-left:2px solid #e5e7eb;
}
html.dark-mode .card{
  background: var(--card-dark);
  border-left-color:#30363d;
}
.card:hover{
  box-shadow:0 6px 20px rgba(0,0,0,.15);
  transform:translateY(-2px);
  background: rgba(59,130,246,.06);
  border-left-color: var(--accent);
}

/* Titres et texte ultra-compacts */
.card h3, .card h4{
  font-family: var(--serif);
  font-weight:700;
  margin:0 0 -10px 0 -20px; /* << colle le texte juste en dessous */
  color:inherit;
}

.card p{line-height: 1.3;}


/* ==== VIDEO VIZU ==== */

.card h4.titre-video {
  font-family: var(--serif);
  font-weight:600;
  margin:0 0 -10px; /* << colle le texte juste en dessous */
  color:black;
  font-size:16px
}

#crop-image_video {
  width: auto ;  /* desired width */
  height: 130px;  /* desired height */
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.card img.image-video {
  object-fit:cover; /* rogne sans déformer */
  object-position:center;
  }



/* Métadonnées */
.meta{
  font-family: var(--sans);
  font-weight:500;
  font-size:clamp(.88rem,3vw,.95rem);
  color:var(--meta-light);
  margin:0 0 0px;
}
html.dark-mode .meta{ color:var(--meta-dark); }

/* ==== IMAGES ==== */

/* Académique : vignette à droite, hauteur flexible */
.card img.thumb-right{
  width:120px;
  max-height:180px;
  object-fit:cover;
  border-radius:12px;
  float:right;
  margin:0 0 8px 12px;
  clear:right;
}

/* Image “horizontale en bas, grande” */
.card img.hero-below{
  display:block;
  width:100%;
  height:auto;
  border-radius:2px;
  flex : 0 0 auto;
  margin: 0 -16px 0 -16px;
}

/* Logo (ex. Sénat) petit, en haut à droite */
.card img.logo{
  width:120px; height:auto; border-radius:6px;
  float:right; margin:-2px 0 6px 10px;
}

/* ==== TWEET-LIKE ==== */
.tweet-header{ display:flex; align-items:center; gap:10px; margin-bottom:6px; }
.avatar{ width:40px; height:40px; border-radius:50%; object-fit:cover; }
.tweet-actions{ display:flex; gap:18px; color:#6b7280; font-size:14px; margin-top:6px; }

/* Utilitaires */
a.btn{
  background:#1266cc; color:#ffffff; padding:6px 10px;
  border-radius:8px; text-decoration:none; display:inline-block;
}
.badge{
  display:inline-block; padding:2px 6px; border-radius:6px;
  background:#eef2ff; color:#4338ca; font-size:12px;
}

/* Sécurité texte */
.card *{ max-width:100%; overflow-wrap:anywhere; word-break:break-word; }
"""

# =========================
# Utils HTML / formatage
# =========================
def _src(path_or_url: str | None) -> str | None:
    if not path_or_url:
        return None
    if str(path_or_url).startswith(("http://", "https://", "data:")):
        return path_or_url
    p = Path(path_or_url)
    if p.exists():
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        mime = "image/png" if p.suffix.lower() in [".png", ".webp"] else "image/jpeg"
        return f"data:{mime};base64,{b64}"
    return None

def _fmt_date_fr(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            return date_str
    mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
            "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    return f"{dt.day} {mois[dt.month-1]} {dt.year}"

def _meta_line(source: str | None, published_at, platform: str | None) -> str:
    # Supporte datetime, str, ou None
    if isinstance(published_at, datetime):
        pub_str = _fmt_date_fr(published_at.isoformat())
    else:
        pub_str = _fmt_date_fr(published_at) if published_at else None
    parts = [p for p in [source, pub_str, platform] if p]
    return " · ".join(map(str, parts))

def _truncate(text: str | None, n: int = 240) -> str:
    if not text:
        return ""
    return text if len(text) <= n else text[:n-1].rstrip() + "…"

def render_card(st, inner_html: str):
    st.markdown(f'<div class="card">{inner_html}</div>', unsafe_allow_html=True)

# =========================
# Cartes basées sur item
# =========================

def card_tweet_item(st, item: dict):
    """
    Rendu façon 'card_tweet' demandé :
    - header avatar + titre (nom) + meta
    - texte
    - actions (si counts fourni)
    """
    avatar_src = _src(item.get("profile_image_url")) 
    title = item.get("title") or "Post"
    text  = item.get("description") or ""
    url   = item.get("url") or "#"

    # Handle/author/date si disponibles
    handle = item.get("handle") or item.get("author") or ""
    meta   = _meta_line(handle or item.get("source"), item.get("published_at"), item.get("platform"))

    counts = item.get("counts") or []  # e.g. ["💬 32","↻ 48","❤ 230"]
    actions_html = ""
    if counts:
        spans = "".join(f"<span>{c}</span>" for c in counts)
        actions_html = f"""<div class="tweet-actions">{spans}</div>"""

    html = f"""
    <div class="tweet-header">
      <img class="avatar" src="{avatar_src}" alt="avatar">
      <div>
        <div><b>{title}</b> <span class="meta">{'' if not meta else '· ' + meta if handle else meta}</span></div>
        <div class="meta">{handle}</div>
      </div>
    </div>
    <div>{_truncate(text, 280)}</div>
    """
    html += actions_html + "<!-- vide -->"

    # Lien (facultatif) sous forme de bouton discret
    
    lien_html = f"""
    <div class="tweet-actions" style="margin-top:8px">
    <a class="btn" href="{url}">Voir le post →</a>
    </div>
    """
    html += lien_html
    render_card(st, html)


def card_academic_item(st, item: dict):
    """
    Rendu 'académique' demandé :
    - image vignettes à droite (thumb-right)
    - h4 titre compact + ligne auteurs/meta
    - chapeau texte
    """
    cover_src = _src(item.get("image_url")) or "https://picsum.photos/200/300"
    titre     = item.get("title") or "Publication"
    chapeau   = _truncate(item.get("description"), 300)
    auteurs   = item.get("authors") or item.get("by") or ""
    url       = item.get("url") or "#"
    meta_line = _meta_line(item.get("source"), item.get("published_at"), item.get("platform"))

    # On suit exactement la structure que tu as montrée
    html = f"""
    <img class="thumb-right" src="{cover_src}" alt="Couverture">
    <h4>{titre}</h4>
    <p class="meta">{auteurs or meta_line}</p>
    <div class="acad-bottom">
      <p>{chapeau}</p>
    </div>
    """
    # Lien (optionnel)
    if url and url != "#":
        html += f'<a href="{url}" style="color:#1266cc;text-decoration:none">Lire l’article →</a>'
    render_card(st, html)


def card_press_item(st, item: dict):
    """
    Rendu 'presse' demandé :
    - Titre
    - Extrait
    - Image large en bas (hero-below)
    - Meta
    """
    img     = _src(item.get("image_url")) or "https://picsum.photos/1400/360"
    titre   = item.get("title") or ""
    extrait = _truncate(item.get("description"), 280)
    url     = item.get("url") or "#"
    meta    = _meta_line(item.get("source"), item.get("published_at"), item.get("platform"))

    html = f"""
    <h4>{titre}</h4>
    <p>{extrait}</p>
    <img class="hero-below" src="{img}" alt="">
    <p class="meta">{meta}</p>
    """
    if url and url != "#":
        html += f'<a href="{url}" style="color:#1266cc;text-decoration:none">Lire l’article</a>'
    render_card(st, html)

def card_video_item(st, item: dict):
    """
    Rendu 'video' demandé :
    - Image large en bas (hero-below)
    - Meta
    - Titre
    - Extrait
    """
    img     = _src(item.get("image_url")) or "https://picsum.photos/1400/360"
    titre   = item.get("title") or ""
    extrait = _truncate(item.get("description"), 150)
    url     = item.get("url") or "#"
    meta    = _meta_line(item.get("source"), item.get("published_at"), item.get("platform"))

    html = f"""
    <div id="crop-image_video"> 
    <img class="image-video" src="{img}" alt="">
    </div>
    <p class="meta">{meta}</p>
    <h4 class="titre-video">{titre}</h4>
    <p>{extrait}</p>
    """
    if url and url != "#":
        html += f'<a href="{url}" style="color:#1266cc;text-decoration:none">Lire l’article</a>'
    render_card(st, html)


def card_report_item(st, item: dict):
    """
    Rendu type 'Sénat' :
    - petit logo en haut à droite
    - h3 titre
    - plusieurs lignes meta (si besoin) + date
    """
    logo = _src(item.get("institution_logo_url"))
    titre = item.get("title") or "Rapport"
    url   = item.get("url") or "#"

    # On formate la date comme dans l’exemple
    date_txt = _fmt_date_fr(item.get("published_at"))
    source   = item.get("source") or ""
    platform = item.get("platform") or ""

    # Quelques lignes de meta indépendantes
    meta_lines = [l for l in [source, platform, date_txt] if l]
    meta_html = "".join(f'<div class="meta">{l}</div>' for l in meta_lines)

    logo_html = f'<img class="logo" src="{logo}" alt="Logo">' if logo else ""
    html = f"""
    <div style="text-align:left">
      {logo_html}
      <h3>{titre}</h3>
      {meta_html}
    </div>
    """
    if url and url != "#":
        html += f'<div style="margin-top:8px"><a class="btn" href="{url}">📄 Ouvrir</a></div>'
    render_card(st, html)


def card_fallback_item(st, item: dict):
    """
    Fallback générique qui respecte la grammaire visuelle (titres compacts, meta,
    image en bas si présente).
    """
    titre = item.get("title") or "Lien"
    desc  = _truncate(item.get("description"), 260)
    url   = item.get("url") or "#"
    meta  = _meta_line(item.get("source"), item.get("published_at"), item.get("platform"))
    img   = _src(item.get("image_url"))

    html = f"""
    <h4>{titre}</h4>
    <p>{desc}</p>
    """
    if img:
        html += f'<img class="hero-below" src="{img}" alt="">'
    html += f'<p class="meta">{meta}</p>'
    if url and url != "#":
        html += f'<a href="{url}" style="color:#1266cc;text-decoration:none">Ouvrir →</a>'
    render_card(st, html)

# =========================
# Dispatcher
# =========================
def render_item(st, item):
    """
    Rend un item en fonction de son type de visualisation.
    Accepte un dict ou un objet.
    """

    # Normalisation en dict
    if not isinstance(item, dict):
        item = item.__dict__

    t = (item.get("type") or "").lower()

    # Mapping type -> fonction
    mapping = {
        "video": "card_video_item",
        "card_tweet": "card_tweet_item",
        "presse": "card_press_item",
        "académique": "card_academic_item",
        "rapport": "card_report_item",
        "forum": "card_forum_item",
        "expo_live": "card_expo_item",
        "dataviz": "card_dataviz_item",
        "podcast_audio": "card_podcast_item",
    }

    func_name = mapping.get(t)
    func = globals().get(func_name)

    if callable(func):
        return func(st, item)

    # fallback générique
    return card_fallback_item(st, item)

