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
.block-container { padding: 12px 12px 28px; max-width: 1600px; }

/* Wrapper de carte — fiable partout */
.card {
  /* Style thread-like */
  background: transparent; 
  border: none;
  border-left: 2px solid #e5e7eb;     /* ligne style fil de discussion */
  padding: 12px 16px;
  margin: 0 0 8px 8px;                /* léger décalage pour la hiérarchie */
  
  color: #111827;                     /* texte bien contrasté */
  line-height: 1.5;
  
  transition: background 160ms ease;
}

.card:hover {
  background: rgba(59, 130, 246, 0.06); /* bleu très léger au hover */
  border-left-color: #3b82f6;           /* accent bleu type twitter */
}

            

.meta{ color:#6b7280; font-size:14px; }
.btn{ background:#1266cc; color:#fff; padding:6px 10px; border-radius:8px; text-decoration:none; display:inline-block; }

/* Tweet */
.tweet-header{ display:flex; align-items:center; gap:10px; margin-bottom:6px; }
.avatar{ width:40px; height:40px; border-radius:50%; object-fit:cover; }
.tweet-actions{ display:flex; gap:18px; color:#6b7280; font-size:14px; margin-top:6px; }

/* Académique */
.acad-top   { display:flex; gap:12px; align-items:stretch; }
.acad-cover { flex:0 0 200px; }
.acad-title { flex:1; display:flex; flex-direction:column; justify-content:center; }
.acad-cover img { width:100%; height:100%; min-height:160px; border-radius:12px; object-fit:cover; }
.acad-bottom{ margin-top:8px; }
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
    <div style="text-align:center">
      <img src="https://upload.wikimedia.org/wikipedia/commons/1/1d/Logo_Senat_Republique_francaise.png" width="56">
      <h4>📑 Rapport du Sénat</h4>
      <h3>Financer l’entreprise de demain</h3>
      <div class="meta">DÉLÉGATION AUX ENTREPRISES</div>
      <div class="meta">Rapport d’information n°70 • L’essentiel</div>
      <div class="meta">4 août 2025</div>
      <a class="btn" href="#">📄 Lire le rapport</a>
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
    <div class="acad-top">
      <div class="acad-cover"><img src="{cover_src}" alt="Couverture"></div>
      <div class="acad-title">
        <h4>{titre}</h4>
        <p class="meta">{auteurs}</p>
      </div>
    </div>
    <div class="acad-bottom">
      <p>{chapeau}</p>
      <a href="{url}" style="color:#1266cc;text-decoration:none">Lire l’article →</a>
    </div>
    """
    render_card(html)

def card_presse(image_url, titre, extrait, meta, url="#"):
    html = f"""
    <img src="{image_url}" style="border-radius:2px;width:100%;height:auto;">
    <h4>{titre}</h4>
    <p>{extrait}</p>
    <p class="meta">{meta}</p>
    <a href="{url}" style="color:#1266cc;text-decoration:none">Lire l’article</a>
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
