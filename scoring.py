# scoring.py
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
import random
import math

# ---- paramètres réglables ----
DAYS_WINDOW = 150          # fenêtre rareté (jours)
EXCLUDE_PROB = 0.25      # proba d’exclure un item (nombre aléatoire négatif)
JITTER_MAX_SHIFT = 200     # décalage max ± places
WEIGHT_RARETE = 100.30      # 90% du score = rareté
WEIGHT_FRESH  = 0.01   
#

def _freshness(published_at, now=None):
    """Fraîcheur peu impactante : demi-vie ~3 jours."""
    if published_at is None: return 0.0

    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    pub = published_at if getattr(published_at, "tzinfo", None) else published_at.replace(tzinfo=timezone.utc)
    hours = max(1, (now - pub).total_seconds() / 3600)
    # ex: 0h -> ~1.0 ; 72h -> ~0.5 ; >72h décroit lentement
    return 1.0 / (1.0 + (hours / 72.0))

def get_counts_last_days_by_source(session, ContentModel, days=DAYS_WINDOW):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (session.query(ContentModel.source, func.count(ContentModel.id))
            .filter(ContentModel.published_at >= since)
            .group_by(ContentModel.source)
            .all())
    return {src: n for src, n in rows}

def base_score(item, counts_by_source, now=None):
    f = 1 #pour l'instant on modifie ça _freshness(item.published_at, now)
    rarity = 1 / max(1, counts_by_source.get(item.source, 1))
    return 100 * f * rarity

def base_score(item, counts_by_source, now=None):
    """
    Score final = 100 * (0.90 * rareté + 0.10 * fraîcheur)
    - rareté: 1/sqrt(count+1) -> booste fortement les sources très peu fréquentes
    - fraîcheur: faible poids (voir _freshness)
    """
    f = _freshness(item.published_at, now)
    c = counts_by_source.get(item.source, 0)
    r = 1.0 / math.sqrt(c + 1.0)  # très rare -> proche de 1 ; très fréquent -> plus petit
    return 100.0 * (WEIGHT_RARETE * r + WEIGHT_FRESH * f)

def keep_item(exclude_prob=EXCLUDE_PROB):
    # nombre aléatoire ∈ [-p,1], négatif ⇒ exclu
    return random.uniform(-exclude_prob, 1.0) >= 0

def jitter_ranking(sorted_items, max_shift=JITTER_MAX_SHIFT):
    n = len(sorted_items)
    perturbed = []
    for rank, it in enumerate(sorted_items):
        shift = random.randint(-max_shift, max_shift)
        target_rank = min(n-1, max(0, rank + shift))
        perturbed.append((target_rank, rank, it))
    perturbed.sort(key=lambda t: (t[0], t[1]))
    return [it for *_ , it in perturbed]

def rank_items(items, counts_by_source, top_k=200, exclude_prob=EXCLUDE_PROB, jitter=JITTER_MAX_SHIFT):
    scored = [(base_score(it, counts_by_source), it) for it in items]
    scored.sort(key=lambda x: x[0], reverse=True)
    kept = [it for s, it in scored if random.uniform(-exclude_prob, 1.0) >= 0]
    return jitter_ranking(kept, max_shift=jitter)[:top_k]

