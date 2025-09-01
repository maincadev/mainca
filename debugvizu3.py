import streamlit as st
from contextlib import contextmanager
from pathlib import Path
import base64

st.set_page_config(layout="wide", page_title="Mur de cartes")


st.markdown("""
<style>
/* Polices */
@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,700;6..72,800&family=Inter:wght@400;500;600&display=swap');

:root{
  --serif: 'Newsreader', Georgia, 'Times New Roman', serif;
  --sans:  'Inter', system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
}

html, body { background:#f7f6f3; }
.block-container{ padding:12px 12px 24px; max-width:780px; }

/* Titre page */
.block-container h2{
  font-family:var(--serif);
  font-weight:800;
  font-size:clamp(1.75rem,6vw,2.5rem);
  line-height:1.08;
  margin:0 0 10px;
}

/* ==== CARD (espacements serrés) ==== */
.card{
  background:#fff; border:none; border-radius:16px;
  box-shadow:0 2px 10px rgba(0,0,0,.06);
  padding:16px;                 /* 20 -> 16 */
  margin:12px 0;                /* 16 -> 12 */
  overflow:clip;
  transition:box-shadow .2s ease, transform .2s ease;
}
.card:hover{ box-shadow:0 6px 20px rgba(0,0,0,.10); transform:translateY(-2px); }


/* Titres de carte */
.card h3,.card h4{
  font-family:var(--serif); font-weight:800;
  font-size:clamp(1.55rem,5vw,1.9rem);   /* un poil plus compact */
  line-height:1.12;
  letter-spacing:-.01em;
  margin:0 0 -20px;                        /* << réduit l'espace titre/texte */
  color:#0b0b0b;
}

/* Paragraphe / chapeau */
.card p{
  font-family:var(--sans); font-weight:400;
  font-size:clamp(1rem,3.4vw,1.1rem);
  line-height:1.45;                      /* plus serré */
  color:#2a2a2a;
  margin:0px 0 4px;                      /* plus serré */
}

            
</style>
""", unsafe_allow_html=True)

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

def card_academique(cover, titre, chapeau, auteurs, url="#"):
    cover_src = _src(cover) or "https://picsum.photos/200/300"
    html = f"""
    <img class="thumb-right" src="{cover_src}" alt="Couverture">
    <h4>{titre}</h4>
    <p class="meta">{auteurs}</p>
    <div class="acad-bottom">
      <p>{chapeau}</p>
      <a href="{url}" class="btn">Lire l’article →</a>
    </div>
    """
    render_card(html)


card_academique(
    cover=r"C:\Users\Emmy\Desktop\Main_channel\revuee.png",
    titre="Les conditions sociales d’une écologie populaire",
    chapeau="Mobilisation environnementale et rapports de classe au sein d’une ferme urbaine en quartier populaire.",
    auteurs="Par Clothilde Saunier, Julien Talpin, Antonio Delfini",
)
