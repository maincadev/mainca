# scoring.py
from datetime import datetime, timezone, timedelta
import random
import math
import hashlib
from sqlalchemy import func

# ---- pondérations ----
W_FRESH = 0.6    # importance de la fraîcheur
W_RARE  = 0.3    # importance de la rareté
W_SOCIAL = 0.1   # importance du bonus réseau social

# ---- bonus par type de source ----
BLUESKY_BONUS = 3.0    # fort boost Bluesky
SOCIAL_BONUS  = 1.5    # autres réseaux sociaux
SOCIAL_SOURCES = {"bluesky", "twitter", "mastodon"}

# ---- autres paramètres ----
DAYS_WINDOW = 150
EXCLUDE_PROB = 0.15
JITTER_MAX_SHIFT = 50
TOP_K = 200

# ---- composantes ----

def freshness_score(published_at, now=None, days_window=DAYS_WINDOW):
    """Score de fraîcheur ∈ [0,1] décroissant avec l’âge (fenêtre DAYS_WINDOW jours)."""
    if published_at is None:
        return 0.0
    now = now or datetime.now(timezone.utc)
    pub = published_at if getattr(published_at, "tzinfo", None) else published_at.replace(tzinfo=timezone.utc)
    delta_days = (now - pub).total_seconds() / 86400
    if delta_days < 0:
        return 1.0
    return max(0.0, 1.0 - delta_days / days_window)


def rarity_score(source, counts_by_source):
    """Plus une source est rare (moins de posts récents), plus le score est élevé."""
    c = counts_by_source.get(source, 0)
    return 1.0 / math.sqrt(c + 1.0)


def source_bonus(source: str) -> float:
    """Boost des réseaux sociaux, avec priorité à Bluesky."""
    s = (source or "").lower()
    if "bluesky" in s:
        return BLUESKY_BONUS
    if any(net in s for net in SOCIAL_SOURCES):
        return SOCIAL_BONUS
    return 1.0


def get_counts_last_days_by_source(session, ContentModel, days=DAYS_WINDOW):
    """Compte les posts par source sur les N derniers jours."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        session.query(ContentModel.source, func.count(ContentModel.id))
        .filter(ContentModel.published_at >= since)
        .group_by(ContentModel.source)
        .all()
    )
    return {src: n for src, n in rows}

# ---- variabilité quotidienne ----

def daily_random_boost(item_id, day_seed=None):
    """
    Génère un bruit pseudo-aléatoire stable pour la journée.
    Chaque jour → feed différent, mais stable dans la journée.
    """
    if day_seed is None:
        day_seed = datetime.now().strftime("%Y-%m-%d")
    key = f"{day_seed}-{item_id}"
    h = hashlib.sha1(key.encode()).hexdigest()
    # valeur entre 0.8 et 1.2 (20% de variabilité quotidienne)
    return 0.8 + (int(h[:8], 16) / 0xFFFFFFFF) * 0.4

# ---- score global ----

def base_score(item, counts_by_source, now=None):
    f = freshness_score(item.published_at, now)
    r = rarity_score(item.source, counts_by_source)
    b = source_bonus(item.source)
    d = daily_random_boost(getattr(item, "id", str(item)))

    # Score pondéré
    score = (W_FRESH * f) + (W_RARE * r) + (W_SOCIAL * b)
    return score * d

# ---- ranking ----

def keep_item(exclude_prob=EXCLUDE_PROB):
    """Décide si on garde l’item (variabilité supplémentaire)."""
    return random.random() > exclude_prob


def jitter_ranking(sorted_items, max_shift=JITTER_MAX_SHIFT):
    """Ajoute un décalage aléatoire aux positions pour éviter un classement figé."""
    n = len(sorted_items)
    perturbed = []
    for rank, it in enumerate(sorted_items):
        shift = random.randint(-max_shift, max_shift)
        target_rank = min(n - 1, max(0, rank + shift))
        perturbed.append((target_rank, rank, it))
    perturbed.sort(key=lambda t: (t[0], t[1]))
    return [it for *_, it in perturbed]


def rank_items(items, counts_by_source, top_k=TOP_K,
               exclude_prob=EXCLUDE_PROB, jitter=JITTER_MAX_SHIFT):
    """Classe et filtre les items selon les règles définies."""
    scored = [(base_score(it, counts_by_source), it) for it in items]
    scored.sort(key=lambda x: x[0], reverse=True)

    kept = [it for s, it in scored if keep_item(exclude_prob)]
    return jitter_ranking(kept, max_shift=jitter)[:top_k]
