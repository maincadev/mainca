import streamlit as st

st.set_page_config(page_title="Swipeable Fullscreen Test", layout="wide")

# --- Masquer header/footer et padding Streamlit ---
hide_streamlit_style = """
<style>
.block-container {padding:0 !important; margin:0 !important; max-width:100% !important;}
header, footer {visibility:hidden;}
body, html {overflow:auto; margin:0; height:100%;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- Swiper HTML avec contenu scrollable ---
swiper_code = """
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.css"/>
<script src="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.js"></script>

<style>
.swiper { width:100%; height:100vh; }
.swiper-slide { display:flex; flex-direction:column; padding:20px; box-sizing:border-box; font-size:18px; background:#f0f2f6; overflow:auto; }
.page1 { background:#4dabf7; color:white; }
.page2 { background:#51cf66; color:white; }
.page3 { background:#ff922b; color:white; }
.block { margin:10px 0; padding:15px; background:rgba(255,255,255,0.2); border-radius:8px; }
</style>

<div class="swiper">
  <div class="swiper-wrapper">
    <div class="swiper-slide page1">
      <h2>📊 Page 1 : Dashboard</h2>
      <div class="block">Bloc 1</div>
      <div class="block">Bloc 2</div>
      <div class="block">Bloc 3</div>
      <div class="block">Bloc 4</div>
      <div class="block">Bloc 5</div>
    </div>
    <div class="swiper-slide page2">
      <h2>⚙️ Page 2 : Réglages</h2>
      <div class="block">Option A</div>
      <div class="block">Option B</div>
      <div class="block">Option C</div>
      <div class="block">Option D</div>
      <div class="block">Option E</div>
    </div>
    <div class="swiper-slide page3">
      <h2>📧 Page 3 : Messages</h2>
      <div class="block">Message 1</div>
      <div class="block">Message 2</div>
      <div class="block">Message 3</div>
      <div class="block">Message 4</div>
      <div class="block">Message 5</div>
    </div>
  </div>
  <div class="swiper-pagination"></div>
</div>

<script>
const swiper = new Swiper('.swiper', {
  loop:false,
  pagination:{ el:'.swiper-pagination', clickable:true },
});
</script>
"""

# --- Affichage ---
# Ici on met une hauteur très grande pour permettre scroll test
st.components.v1.html(swiper_code, height=1200, scrolling=True)
