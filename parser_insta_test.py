import instaloader
from feedgen.feed import FeedGenerator

def instagram_to_rss(username: str, max_posts: int = 10) -> str:
    # Initialise Instaloader (pas besoin de login pour un compte public)
    L = instaloader.Instaloader(download_pictures=False,
                                download_videos=False,
                                download_video_thumbnails=False,
                                save_metadata=False,
                                compress_json=False)

    profile = instaloader.Profile.from_username(L.context, username)

    fg = FeedGenerator()
    fg.title(f"Instagram feed de {username}")
    fg.link(href=f"https://www.instagram.com/{username}/")
    fg.description(f"Flux RSS généré à partir d’Instagram (@{username})")

    for post in profile.get_posts():
        if max_posts and fg.entry().__len__() >= max_posts:
            break

        fe = fg.add_entry()
        fe.id(post.shortcode)
        fe.title(post.caption or "📷 Publication Instagram")
        fe.link(href=f"https://www.instagram.com/p/{post.shortcode}/")
        fe.published(post.date_utc)
        fe.content(f'<img src="{post.url}" alt="Instagram post"/>')

    return fg.rss_str(pretty=True).decode("utf-8")


if __name__ == "__main__":
    rss_feed = instagram_to_rss("mk2", max_posts=5)  # ← change "nasa" par le compte public voulu
    with open("instagram_feed.xml", "w", encoding="utf-8") as f:
        f.write(rss_feed)
    print("✅ Flux RSS généré : instagram_feed.xml")
