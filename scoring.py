# scoring_max_diversity.py
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import math, random
from typing import List, Dict, Tuple, Optional, Iterable

# ---------- Réglages par défaut ----------
TOP_K_DEFAULT = 200

FRESH_HALF_LIFE_H = 72.0     # demi-vie fraîcheur (h)
RARE_HALF_LIFE_D = 30.0      # demi-vie rareté (jours)
W_RARE, W_FRESH = 0.75, 0.25 # poids score de base (r + f)

RARE_SMOOTHING = 0.5         # lissage additif rareté

# Max diversité : paramètres de rotation
PER_SOURCE_WINDOW = 3        # combien de candidats on regarde dans chaque source pour varier
GUMBEL_TAU_INTRA = 0.12      # bruit pour faire tourner les items d’une source
GUMBEL_TAU_INTER = 0.20      # bruit pour faire tourner l’ordre des sources
REFRESH_PERIOD_S = 60        # change de seed par minute (par défaut)

# ---------- Utilitaires ----------
def _now_utc():
    return datetime.now(timezone.utc)

def _aware(dt: datetime) -> datetime:
    return dt if getattr(dt, "tzinfo", None) else dt.replace(tzinfo=timezone.utc)

def _gumbel(tau: float) -> float:
    if tau <= 0: return 0.0
    u = max(1e-12, random.random())
    return -math.log(-math.log(u)) * tau

def freshness_score(published_at: Optional[datetime],
                    now: Optional[datetime] = None,
                    half_life_h: float = FRESH_HALF_LIFE_H) -> float:
    if published_at is None: return 0.0
    now = now or _now_utc()
    age_h = max(0.0, (now - _aware(published_at)).total_seconds() / 3600.0)
    return 0.5 ** (age_h / max(1e-9, half_life_h))

def decayed_counts_by_source(items: Iterable, now: Optional[datetime] = None,
                             half_life_d: float = RARE_HALF_LIFE_D) -> Dict[str, float]:
    now = now or _now_utc()
    counts = defaultdict(float)
    hl = max(1e-9, half_life_d)
    for it in items:
        src = getattr(it, "source", None) or "unknown"
        pub = getattr(it, "published_at", None)
        if pub is None:
            contrib = 0.25
        else:
            age_d = max(0.0, (now - _aware(pub)).total_seconds() / 86400.0)
            contrib = 0.5 ** (age_d / hl)
        counts[src] += contrib
    return counts

def base_score(item, dec_counts: Dict[str, float], now: Optional[datetime] = None,
               w_rare: float = W_RARE, w_fresh: float = W_FRESH,
               rare_smoothing: float = RARE_SMOOTHING) -> float:
    src = getattr(item, "source", None) or "unknown"
    c = float(dec_counts.get(src, 0.0))
    r = 1.0 / math.sqrt(max(1e-9, rare_smoothing + c))  # (0, ~1]
    f = freshness_score(getattr(item, "published_at", None), now=now)
    denom = max(1e-9, (w_rare + w_fresh))
    return min(1.0, max(0.0, (w_rare * r + w_fresh * f) / denom))

# ---------- Rang “max diversité par refresh” ----------
def _seed_for_refresh(now: datetime, refresh_period_s: int) -> int:
    # change de seed tous les REFRESH_PERIOD_S pour varier à chaque refresh
    return int(now.timestamp()) // max(1, refresh_period_s)

def _pick_from_bucket(bucket: List[Tuple[float, object]],
                      window: int,
                      tau: float) -> Optional[Tuple[float, object, int]]:
    """
    Choisit un item dans les 'window' premiers d’une source en ajoutant du Gumbel.
    Retourne (score, item, index_dans_bucket) ou None si vide.
    """
    if not bucket: return None
    m = min(window, len(bucket))
    best_idx, best_val = 0, -1e9
    for i in range(m):
        s, it = bucket[i]
        v = s + _gumbel(tau)
        if v > best_val:
            best_val, best_idx = v, i
    s, it = bucket[best_idx]
    return s, it, best_idx

def rank_items(items: List[object],
               top_k: int = TOP_K_DEFAULT,
               now: Optional[datetime] = None,
               fresh_half_life_h: float = FRESH_HALF_LIFE_H,
               rare_half_life_d: float = RARE_HALF_LIFE_D,
               w_rare: float = W_RARE,
               w_fresh: float = W_FRESH,
               # mode "max diversité par refresh"
               per_source_window: int = PER_SOURCE_WINDOW,
               gumbel_tau_intra: float = GUMBEL_TAU_INTRA,
               gumbel_tau_inter: float = GUMBEL_TAU_INTER,
               refresh_period_s: int = REFRESH_PERIOD_S,
               refresh_seed: Optional[int] = None) -> List[object]:
    """
    Max diversité par refresh :
      1) score de base (fraîcheur + rareté décayée)
      2) round-robin strict entre sources (1 item/source/“tour”)
      3) rotation intra-source à chaque refresh (Gumbel) pour ne pas voir toujours le #1
      4) si certaines sources manquent d’items, on rééquilibre avec les restantes
    """
    if not items: return []

    now = now or _now_utc()
    # Seed de refresh (deterministic per time-slice)
    if refresh_seed is None:
        refresh_seed = _seed_for_refresh(now, refresh_period_s)
    random.seed(refresh_seed)

    # 1) Comptes décayés + scores
    dec_counts = decayed_counts_by_source(items, now=now, half_life_d=rare_half_life_d)
    per_source: Dict[str, List[Tuple[float, object]]] = defaultdict(list)
    for it in items:
        s = base_score(it, dec_counts, now=now, w_rare=w_rare, w_fresh=w_fresh)
        src = getattr(it, "source", None) or "unknown"
        per_source[src].append((s, it))

    # Tri décroissant dans chaque source
    for src in per_source:
        per_source[src].sort(key=lambda t: t[0], reverse=True)

    sources = list(per_source.keys())
    if not sources: return []
    n_src = len(sources)

    # 2) Ordre de passage des sources = leurs meilleures têtes + petite rotation
    sources.sort(
        key=lambda s: (per_source[s][0][0] if per_source[s] else 0.0) + _gumbel(gumbel_tau_inter),
        reverse=True
    )

    # 3) Round-robin strict : 1 item / source / tour
    selected: List[object] = []
    # max équitable par source ~ ceil(top_k / n_src)
    fair_cap = max(1, math.ceil(top_k / n_src))
    used = defaultdict(int)

    # On itère en "tours". À chaque tour, on parcourt les sources dans l'ordre.
    # À l’intérieur d’une source, on choisit dans une fenêtre courte avec Gumbel pour varier.
    while len(selected) < top_k and sources:
        progressed = False
        for src in list(sources):
            if len(selected) >= top_k:
                break
            bucket = per_source[src]
            if not bucket:
                # plus d’items dans cette source -> on la retire du round
                sources.remove(src)
                continue
            if used[src] >= fair_cap:
                # cette source a déjà sa part équitable pour le moment
                continue
            pick = _pick_from_bucket(bucket, per_source_window, gumbel_tau_intra)
            if pick is None:
                sources.remove(src)
                continue
            _, it, idx = pick
            # retire l’item choisi du bucket
            bucket.pop(idx)
            selected.append(it)
            used[src] += 1
            progressed = True
        if not progressed:
            break  # aucun progrès possible (toutes caps atteints ou buckets vides)

    # 4) Remplissage si on n’a pas atteint top_k (certaines sources vides)
    if len(selected) < top_k:
        # rassembler tous les restants, triés par score décroissant
        rest: List[Tuple[float, object, str]] = []
        for src, bucket in per_source.items():
            for s, it in bucket:
                rest.append((s, it, src))
        rest.sort(key=lambda t: t[0], reverse=True)

        for s, it, src in rest:
            if len(selected) >= top_k:
                break
            # on laisse un léger amortissement pour ne pas exploser une source
            if used[src] <= fair_cap + 1:  # “+1” = relâchement doux
                selected.append(it)
                used[src] += 1

        # si toujours pas assez, on complète strictement par score
        if len(selected) < top_k:
            leftovers = [it for _, it, _ in rest if it not in selected]
            selected.extend(leftovers[:(top_k - len(selected))])

    return selected[:top_k]
