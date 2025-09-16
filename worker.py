# worker.py
import json, time
from pathlib import Path
from tqdm import tqdm

# 👇 importe SessionLocal et Content depuis aggcon_v2
from aggcon_v2 import SessionLocal, Content, adapter_rss, scan_pertinence, save_to_db,  Base, engine, ensure_schema
Base.metadata.create_all(bind=engine)
ensure_schema()

data_file = Path(__file__).parent / "sources_actuelles.json"

def run_worker():
    """
    Boucle principale du worker :
    - lit les sources configurées
    - appelle l’adapter
    - filtre les items
    - sauvegarde en base
    """
    session = SessionLocal()
    #---------------------------------Importe les sources qui sont une liste de dictionnaire, avec notamment les liens RSS-----------------------
    with open(data_file, encoding="utf-8") as f:
        sources = json.load(f)
    #----------------------------------------------------------------------------------------



    #---------------------------MESURE DU TEMPS -----------------
    #rappel tqdm c'est pour mesurer le temps de l'itération, avec desc la description de la barre de progression, il sert d'itérateur 
    bar = tqdm(sources, desc="Avancée générale")
    timings = []
    #---------------------------MESURE DU TEMPS -----------------

    for src in bar:

        #---------------------------MESURE DU TEMPS -----------------
        bar.set_description(f"Avancée générale (on en est à {src['name']})")
        start = time.perf_counter()
        #---------------------------MESURE DU TEMPS -----------------


        items = adapter_rss(
            source_url=src["url"],
            source_name=src["name"],
            source_platform=src["platform"],
            default_type="ARTICLE",
            category=src["category"],
            max_posts=5
            )

        
        for item in items:
            if scan_pertinence(item):
                save_to_db(session, item)
        
        end = time.perf_counter()

        #timings est une liste de couple ("Thinkerview", 20s)
        timings.append((src["name"], end - start))
        #--------------------------------------------------

    #---------------------------MESURE DU TEMPS -----------------
    print("\n🐢 Top 5 :")
    for name, dt in sorted(timings, key=lambda x: x[1], reverse=True)[:5]:
        print(f"- {name}: {dt:.2f}s")
    #--------------------------------------------------


    print("✅ Worker terminé : contenus agrégés et stockés.")

if __name__ == "__main__":

    run_worker()
