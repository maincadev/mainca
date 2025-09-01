import streamlit as st
from contextlib import contextmanager
from pathlib import Path
import base64

st.set_page_config(layout="wide", page_title="Mur de cartes")

# =========================
# CSS global
# =========================

st.markdown("""
<style>

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
}

/* Mode clair par défaut */
html, body, .stApp {
  background: var(--bg-light);
  color: var(--text-light);
}

/* Appliquer .dark-mode sur html pour passer en mode sombre */
html.dark-mode, html.dark-mode body, html.dark-mode .stApp {
  background: var(--bg-dark) !important;
  color: var(--text-dark) !important;
}

/* Cartes */
.card{
  background: var(--card-light);
  border:none; border-radius:6px;
  box-shadow:0 2px 10px rgba(0,0,0,.06);
  padding:16px; margin:12px 0;
  transition:box-shadow .2s ease, transform .2s ease;
  border-left:2px solid #e5e7eb;
}
html.dark-mode .card{
  background: var(--card-dark);
  border-left-color:#30363d;
}
.card:hover{ 
  box-shadow:0 6px 20px rgba(0,0,0,.15); 
  transform:translateY(-2px); 
  background: rgba(59, 130, 246, 0.06);
  border-left-color: var(--accent);
}

/* Titres */
.card h3,.card h4{
  font-family:var(--serif); font-weight:700;
  margin:0 0 -15px;
  color:inherit;
}

/* Métadonnées */
.meta{
  font-family:var(--sans); font-weight:500;
  font-size:clamp(.88rem,3vw,.95rem);
  color:var(--meta-light);
}
html.dark-mode .meta{ color:var(--meta-dark); }
            
/* ==== IMAGES ==== */

/* Académique : vignette à droite, hauteur flexible */
.card img.thumb-right{
  width:120px;          /* plus large */
  max-height:180px;     /* permet plus de longueur */
  object-fit:cover; 
  border-radius:12px;
  float:right;
  margin:0 0 8px 12px;
  clear:right;          /* évite que le texte empiète */
}

/* Image “horizontale en bas, grande” */
.card img.hero-below{
  display:block;
  width:100%;           /* prend toute la largeur de la carte */
  height:auto;
  border-radius:2px;
  margin:8px 0 0;
}

/* Logo (Sénat) petit */
.card img.logo{
  width:40px; height:auto; border-radius:6px;
  float:right; margin:-2px 0 6px 10px;
}
            
/* Tweet */
.tweet-header{ display:flex; align-items:center; gap:10px; margin-bottom:6px; }
.avatar{ width:40px; height:40px; border-radius:50%; object-fit:cover; }
.tweet-actions{ display:flex; gap:18px; color:#6b7280; font-size:14px; margin-top:6px; }

</style>
""", unsafe_allow_html=True)


# =========================
# Utils
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


def render_card(inner_html: str):
    """Affiche le HTML fourni à l'intérieur d'un wrapper .card en un seul bloc."""
    st.markdown(f'<div class="card">{inner_html}</div>', unsafe_allow_html=True)


# =========================
# Composants de cartes
# =========================
def card_senat():
    html = """
    <div style="text-align:left">
      <img class="logo" src="https://upload.wikimedia.org/wikipedia/fr/thumb/6/63/Logo_S%C3%A9nat_%28France%29_2018.svg/1200px-Logo_S%C3%A9nat_%28France%29_2018.svg.png" alt="Sénat">
      <h3>Financer l’entreprise de demain</h3>
      <div class="meta">DÉLÉGATION AUX ENTREPRISES</div>
      <div class="meta">Rapport d’information n°70 • L’essentiel</div>
      <div class="meta">4 août 2025</div>
    </div>
    """
    render_card(html)

def card_tweet(name="Huckberry", handle="@huckberry", date="12 Apr",
               text=("On the Journal: 6 Items That Leveled Up My Car Camping Game... "
                     '<a href="https://bit.ly/3MbbSed" style="color:#1266cc;text-decoration:none">https://bit.ly/3MbbSed</a>'),
               avatar=r"C:\Users\Emmy\Desktop\Main_channel\avatar.png",
               counts=("💬 32","↻ 48","❤ 230")):
    avatar_src = _src(avatar) or "https://picsum.photos/80"
    html = f"""
    <div class="tweet-header">
      <img class="avatar" src="{avatar_src}" alt="avatar">
      <div>
        <div><b>{name}</b> <span class="meta">· {date}</span></div>
        <div class="meta">{handle}</div>
      </div>
    </div>
    <div>{text}</div>
    <div class="tweet-actions"><span>{counts[0]}</span><span>{counts[1]}</span><span>{counts[2]}</span></div>
    """
    render_card(html)

def card_academique(cover, titre, chapeau, auteurs, url="#"):
    cover_src = _src(cover) or "https://picsum.photos/200/300"
    html = f"""
    <img class="thumb-right" src="{cover_src}" alt="Couverture">
    <h4>{titre}</h4>
    <p class="meta">{auteurs}</p>
    <div class="acad-bottom">
      <p>{chapeau}</p>
    </div>
    """
    render_card(html)


def card_presse(image_url, titre, extrait, meta, url="#"):
    html = f"""
    <h4>{titre}</h4>
    <p>{extrait}</p>
    <img class="hero-below" src="{image_url}" alt="">
    <p class="meta">{meta}</p>
    """
    render_card(html)




# =========================
# Rendu
# =========================
st.markdown("## 📲 Mon Feed")

card_senat()

card_tweet()

card_academique(
    cover=r"C:\Users\Emmy\Desktop\Main_channel\revuee.png",
    titre="Les conditions sociales d’une écologie populaire",
    chapeau="Mobilisation environnementale et rapports de classe au sein d’une ferme urbaine en quartier populaire.",
    auteurs="Par Clothilde Saunier, Julien Talpin, Antonio Delfini",
)

card_presse(
    "https://picsum.photos/1400/360",
    "À Mont-Saint-Michel, dans les secrets de l’abbaye",
    "Exploration des coulisses du chef-d’œuvre gothique restauré.",
    "Le Monde · 12 mars 2024"
)
