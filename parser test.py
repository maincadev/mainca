import feedparser
from datetime import datetime

def test_parse(feed_url: str):
    feed = feedparser.parse(feed_url)

    print(f"=== Flux : {feed_url} ===")
    print(f"Titre du flux : {feed.feed.get('title', 'Inconnu')}")
    print(f"Nombre d'entrées : {len(feed.entries)}\n")

    for i, entry in enumerate(feed.entries[:5], 1):  # affiche les 5 premiers
        print(f"[{i}] {entry.get('title')}")
        print(f"    Lien       : {entry.get('link')}")
        print(f"    Résumé     : {entry.get('summary', '')[:120]}...")
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            pubdate = datetime(*entry.published_parsed[:6])
            print(f"    Publié le  : {pubdate}")
        else:
            print("    Publié le  : (non fourni)")
        print()
    
    #un feed c'est feed.feed['titre du feed et autres info propres au feed'] ou feed.entries[numéro de l'entrée].get('summary'))

    print(feed.entries[0])


# Exemple d’utilisation
test_parse("http://videos.senat.fr/video/videos.rss")
