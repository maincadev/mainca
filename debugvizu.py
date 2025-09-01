import streamlit as st


# ---------- 1. Rapport Sénat ----------
def render_senat_report():
    with st.container():
        st.markdown(
            """
            <div style="background:white; border-radius:16px; padding:20px; box-shadow:0px 2px 6px rgba(0,0,0,0.1); text-align:center;">
                <img src="https://upload.wikimedia.org/wikipedia/commons/1/1d/Logo_Senat_Republique_francaise.png" width="60">
                <h4 style="margin:8px 0;">📑 Rapport du Sénat</h4>
                <h3>Financer l’entreprise de demain</h3>
                <p style="color:#555; margin:4px 0;">DÉLÉGATION AUX ENTREPRISES</p>
                <p style="color:#777;">Rapport d’information n°70 • L’essentiel</p>
                <p style="color:#999;">4 août 2025</p>
                <a href="#" style="background:#1266cc; color:white; padding:8px 16px; border-radius:8px; text-decoration:none;">
                📄 Lire le rapport</a>
            </div>
            """,
            unsafe_allow_html=True
        )

# ---------- 2. Tweet ----------
def render_tweet():
    with st.container():
        st.markdown(
            """
            <div style="background:white; border-radius:16px; padding:20px; box-shadow:0px 2px 6px rgba(0,0,0,0.1);">
                <b>🐦 Huckberry</b> · 12 Apr · Camping
                <p>On the Journal: 6 Items That Leveled Up My Car Camping Game... 
                <a href="https://bit.ly/3MbbSed">https://bit.ly/3MbbSed</a></p>
                <div style="color:#777;">💬 32 &nbsp; ↻ 48 &nbsp; ❤ 230</div>
            </div>
            """,
            unsafe_allow_html=True
        )

# ---------- 3. Article académique ----------
def render_academic_article():
    with st.container():
        col1, col2 = st.columns([1,2])
        
        with col1:
            st.image(r"c:/Users/Emmy/Desktop/Main_channel/revuee.png")

        with col2:
            st.markdown(
                """
                <div style="padding:10px;">
                    <h4>Les conditions sociales d’une écologie populaire</h4>
                    <p>Mobilisation environnementale et rapports de classe au sein d’une ferme urbaine en quartier populaire.</p>
                    <p style="color:#777;">Par Clothilde Saunier, Julien Talpin, Antonio Delfini</p>
                    <a href="#">Lire l’article →</a>
                </div>
                """,
                unsafe_allow_html=True
            )

# ---------- 4. Article de presse ----------
def render_press_article():
    with st.container():
        st.markdown(
            """
            <div style="background:white; border-radius:16px; padding:20px; box-shadow:0px 2px 6px rgba(0,0,0,0.1);">
                <img src="https://fakeimg.pl/600x200/cccccc/000000/?text=Mont-Saint-Michel" style="border-radius:12px; width:100%;">
                <h4>À Mont-Saint-Michel, dans les secrets de l’abbaye</h4>
                <p>Exploration des coulisses du chef-d’œuvre gothique restauré.</p>
                <p style="color:#777;">Le Monde · 12 mars 2024</p>
                <a href="#">Lire l’article</a>
            </div>
            """,
            unsafe_allow_html=True
        )

# ---------- Render unified feed ----------
st.markdown("## 📲 Mon Feed")
render_senat_report()
st.write("---")
render_tweet()
st.write("---")
render_academic_article()
st.write("---")
render_press_article()
