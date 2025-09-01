    for item in final_items:
        
        # Image en tête si dispo

        if item.image_url:
            st.image(item.image_url, use_column_width=True)

        # Affichage dynamique selon type
        meta = f"[{item.source}] · {item.published_at} · {item.type}"

        if item.type == "TWEET":
            # microblog : pas de titre, juste le texte
            st.caption(meta)
            st.write(item.description)

        elif item.type == "VIDEO":
            # si YouTube, on peut afficher la miniature (déjà ci-dessus) et le titre
            if item.title:
                st.subheader(item.title)
            st.caption(meta)
            if item.description:
                st.write(truncate(item.description))

        elif item.type == "PODCAST":
            if item.title:
                st.subheader(item.title)
            st.caption(meta)
            if item.description:
                st.write(truncate(item.description))
            # Tentative de lecteur audio si URL audio stockée (si tu l’ajoutes en DB)
            # st.audio(item.audio_url)  # nécessiterait de stocker audio_url en base

        else:
            # ARTICLE et autres
            if item.title:
                st.subheader(item.title)
            st.caption(meta)
            if item.description:
                st.write(truncate(item.description))

        st.markdown(f"[Lien vers la source]({item.url})")
        st.divider()