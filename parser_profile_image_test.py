import re
import requests
from urllib.parse import urlparse, quote

# ===== Bluesky: endpoint public officiel =====
BLSKY_PROFILE_ENDPOINT = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile"

def fetch_bluesky_avatar(username_or_did: str,
                         fallback_url: str = "https://example.com/default_avatar.png") -> str:
    """
    Récupère l'avatar d'un utilisateur Bluesky via l'API publique:
      GET https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor=<handle|did>
    Retourne avatar ou fallback_url en cas d'échec.
    """
    try:
        resp = requests.get(BLSKY_PROFILE_ENDPOINT, params={"actor": username_or_did}, timeout=5)
        if resp.ok:
            data = resp.json() or {}
            return data.get("avatar") or fallback_url
        else:
            print(f"[Bluesky] HTTP {resp.status_code} for {username_or_did}")
            return fallback_url
    except requests.RequestException as e:
        print(f"[Bluesky] Error: {e}")
        return fallback_url


# ===== Mastodon: lookup public de l’instance =====
def fetch_mastodon_avatar(acct: str,
                          fallback_url: str = "https://example.com/default_avatar.png") -> str:
    """
    acct = 'user@instance.tld'
    Utilise: https://<instance>/api/v1/accounts/lookup?acct=<acct>
    """
    if "@" not in acct:
        return fallback_url
    user, instance = acct.split("@", 1)
    api = f"https://{instance}/api/v1/accounts/lookup"
    try:
        resp = requests.get(api, params={"acct": acct}, timeout=5)
        if resp.ok:
            data = resp.json() or {}
            return data.get("avatar") or data.get("avatar_static") or fallback_url
        else:
            print(f"[Mastodon] HTTP {resp.status_code} for {acct}")
            return fallback_url
    except requests.RequestException as e:
        print(f"[Mastodon] Error: {e}")
        return fallback_url


# ===== Fonction principale (même signature qu’avant) =====
def extract_profile_image(entry: dict | None, base_link: str | None,
                          fallback_url: str = "https://www.shutterstock.com/image-vector/default-avatar-profile-icon-social-600nw-1906669723.jpg") -> str | None:
    """
    Retourne l'URL de la photo de profil pour Twitter/X, Mastodon, Bluesky.
    - Bluesky: API publique (public.api.bsky.app)
    - Mastodon: API publique d’instance
    - Twitter/X: fallback unavatar (pas d’API publique simple)
    """
    # 1) Champs directs déjà présents
    if entry:
        for key in ("author_image", "author_icon", "profile_image", "avatar", "avatar_url", "user_image"):
            url = entry.get(key)
            if isinstance(url, str) and url.strip():
                return url.strip()

    # 2) Choisir le lien de référence
    link = None
    for key in ("link", "url", "id", "origin_link", "author_url"):
        if entry and isinstance(entry.get(key), str) and entry[key].startswith(("http://", "https://")):
            link = entry[key]
            break
    if not link and isinstance(base_link, str):
        link = base_link
    if not isinstance(link, str):
        return None

    parsed = urlparse(link)
    host = (parsed.netloc or "").lower()

    # ===== Bluesky =====
    #   https://bsky.app/profile/<handle|did>/...
    if "bsky.app" in host:
        m = re.search(r"bsky\.app/profile/([^/?#]+)", link, re.IGNORECASE)
        if m:
            handle_or_did = m.group(1)
            return fetch_bluesky_avatar(handle_or_did, fallback_url)
    if entry:
        for key in ("author_handle", "bsky_handle", "bsky_did"):
            v = entry.get(key)
            if isinstance(v, str) and v.strip():
                return fetch_bluesky_avatar(v.strip(), fallback_url)

    # ===== Mastodon =====
    mastodon_match = re.search(r"https?://([^/]+)/@([^/?#]+)", link, re.IGNORECASE)
    if mastodon_match:
        instance = mastodon_match.group(1).lower()
        user = mastodon_match.group(2)
        acct = f"{user}@{instance}"
        return fetch_mastodon_avatar(acct, fallback_url)
    if entry:
        author_name = entry.get("author") or entry.get("author_name") or ""
        if isinstance(author_name, str):
            m = re.search(r"@([A-Za-z0-9_\.]+)@([A-Za-z0-9\.-]+\.[A-Za-z]{2,})", author_name)
            if m:
                acct = f"{m.group(1)}@{m.group(2)}"
                return fetch_mastodon_avatar(acct, fallback_url)

    # ===== Twitter / X =====
    if "twitter.com" in host or host == "x.com":
        m = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})(?:/|$)", link, re.IGNORECASE)
        if m:
            username = m.group(1)
            return f"https://unavatar.io/twitter/{username}"

    # ===== Fallback =====
    return fallback_url


print(extract_profile_image(entry=None, base_link="https://bsky.app/profile/thomaspiketty.bsky.social/post/3lp75rtetzk2i"))