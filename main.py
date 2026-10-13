from collectors.france_travail import fetch_offers as fetch_france_travail
from collectors.hellowork import fetch_offers_batch as fetch_hellowork_batch
from collectors.wttj import fetch_offers_batch as fetch_wttj_batch
from storage.db import init_db, save_offers, delete_old_offers
from config import PROFILE


def run():
    init_db()

    print("=== Nettoyage des offres obsolètes (> 12h) ===")
    deleted = delete_old_offers(max_hours=12)
    print(f"{deleted} offre(s) supprimée(s)\n")

    total_new = 0

    print("=== France Travail ===")
    for title in PROFILE["job_titles"]:
        offers = fetch_france_travail(title)
        new_count = save_offers(offers)
        total_new += new_count
        print(f"{title}: {len(offers)} récupérées, {new_count} nouvelles")

    print("\n=== HelloWork ===")
    hw_results = fetch_hellowork_batch(PROFILE["job_titles"])
    for title, offers in hw_results.items():
        new_count = save_offers(offers)
        total_new += new_count
        print(f"{title}: {len(offers)} récupérées, {new_count} nouvelles")

    # WTTJ est la source la plus fragile (parcours d'accueil du site) :
    # une erreur ici ne doit jamais empêcher le scoring et le commit de la base.
    print("\n=== Welcome to the Jungle ===")
    try:
        wttj_results = fetch_wttj_batch(PROFILE["job_titles"])
        for title, offers in wttj_results.items():
            new_count = save_offers(offers)
            total_new += new_count
            print(f"{title}: {len(offers)} récupérées, {new_count} nouvelles")
    except Exception as e:
        print(f"⚠️ WTTJ ignoré (erreur inattendue) : {e}")

    print(f"\nTotal nouvelles offres stockées : {total_new}")


if __name__ == "__main__":
    run()