import os
import re
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from collectors.base import JobOffer
from processing.filters import passes_hard_filters

BASE_URL = "https://www.welcometothejungle.com"
MAX_CANDIDATES_TO_CHECK = 8

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

OVERLAY_JS = (
    "document.querySelectorAll('#axeptio_overlay, .axeptio_widget, iframe')"
    ".forEach(e => e.remove());"
)

PROFILE = {
    "job_titles": [
        "Data Engineer",
        "Ingénieur Data",
        "Data Analyst",
        "Analyste Data",
        "Data Scientist",
        "Développeur BI",
        "Ingénieur BI",
        "Consultant Data",
        "ETL Developer",
        "Développeur ETL",
        "AI Engineer",
        "Ingénieur IA",
    ]
}


def _remove_overlays(page):
    try:
        page.evaluate(OVERLAY_JS)
    except Exception:
        pass


def _detect_contract(text: str) -> str:
    m = re.search(r"\b(CDI|CDD)\b", text)
    if m:
        return m.group(1)
    if re.search(r"\b(stage|alternance|apprentissage|freelance|int[eé]rim)\b", text, re.IGNORECASE):
        return "AUTRE"
    return "CDI"


def _parse_job_url(url: str):
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    parts = slug.split("_")
    city = parts[1].replace("-", " ").title() if len(parts) >= 3 else ""
    return slug, city


def _run_search_flow(page, query: str, location: str) -> bool:
    """Suivi robuste du tunnel avec gestion d'hydratation React."""
    try:
        # 1. Navigation sécurisée
        page.goto(f"{BASE_URL}/fr/get-started/job-title", wait_until="domcontentloaded", timeout=25000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        _remove_overlays(page)

        # 1/3 Intitulé de poste
        print(f"   → 1/3 Saisie du poste : '{query}'")
        
        # Sélecteur universel pour trouver le champ texte quel que soit l'état de la page
        input_job = page.locator("input[placeholder*='Product'], input[type='text'], input[type='search'], input").first
        input_job.wait_for(state="visible", timeout=12000)
        
        input_job.click()
        input_job.fill("")
        page.keyboard.type(query, delay=80)
        page.wait_for_timeout(1000)

        # Clic autocomplétion
        try:
            job_opt = page.locator("ul[role='listbox'] li, [role='option'], li").first
            if job_opt.count() > 0 and job_opt.is_visible():
                job_opt.click()
                page.wait_for_timeout(500)
            else:
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
        except Exception:
            page.keyboard.press("Enter")

        page.wait_for_timeout(1000)

        btn_next_1 = page.get_by_text("Suivant").first
        if btn_next_1.count() > 0 and btn_next_1.is_visible():
            btn_next_1.click()

        page.wait_for_timeout(2000)
        _remove_overlays(page)

        # 2/3 Niveau d'expérience
        try:
            page.wait_for_selector("text=Débutant. 0-1 an", timeout=5000)
            print("   → 2/3 Sélection du niveau d'expérience...")
            
            btn_0_1 = page.get_by_text("Débutant. 0-1 an").first
            if btn_0_1.count() > 0:
                btn_0_1.click()
                page.wait_for_timeout(300)

            btn_1_3 = page.get_by_text("Junior. 1-3 ans").first
            if btn_1_3.count() > 0:
                btn_1_3.click()
                page.wait_for_timeout(300)

            btn_next_2 = page.get_by_text("Suivant").first
            if btn_next_2.count() > 0:
                btn_next_2.click()

            page.wait_for_timeout(2000)
            _remove_overlays(page)
        except Exception:
            print("   ⚠️ Étape d'expérience ignorée")

        # 3/3 Localisation
        try:
            print(f"   → 3/3 Saisie de la localisation : '{location}'")
            input_loc = page.locator("input[placeholder*='Londres'], input[type='text'], input").first
            input_loc.wait_for(state="visible", timeout=8000)
            
            input_loc.click()
            input_loc.fill("")
            page.wait_for_timeout(300)
            
            page.keyboard.type(location, delay=100)
            page.wait_for_timeout(1500)

            first_suggestion = page.locator("ul[role='listbox'] li, [role='option'], [data-testid*='autocomplete'] li").first
            first_suggestion.wait_for(state="visible", timeout=5000)
            first_suggestion.click()
            
            print("   ✓ Clic sur la suggestion de localisation !")
            page.wait_for_timeout(1000)

            btn_discover = page.get_by_text("Découvrir mes jobs").first
            btn_discover.wait_for(state="visible", timeout=5000)
            btn_discover.click()
            print("   ✓ Clic sur 'Découvrir mes jobs' !")

            page.wait_for_timeout(4000)
            _remove_overlays(page)
        except Exception as e:
            print(f"   ⚠️ Séquence de secours localisation : {e}")
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(300)
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            btn_discover = page.get_by_text("Découvrir mes jobs").first
            if btn_discover.is_visible():
                btn_discover.click()

        # Attente redirection
        try:
            page.wait_for_url(re.compile(r"/(jobs|jobs-preview)"), timeout=10000)
        except Exception:
            pass

        # Filtre 'Dernières 24h'
        try:
            print("   → Application du filtre 'Dernières 24h'...")
            page.wait_for_selector("text=Toutes les dates", timeout=8000)
            date_filter = page.get_by_text("Toutes les dates").first
            date_filter.click()
            page.wait_for_timeout(800)

            opt_24h = page.get_by_text("Dernières 24 heures").first
            if opt_24h.count() > 0:
                opt_24h.click()
            else:
                page.locator("text=24h, text=24 heures, text=Dernières 24h").first.click()
                
            page.wait_for_timeout(2000)
            print("   ✓ Filtre 24h appliqué avec succès.")
        except Exception as e:
            print(f"   ⚠️ Impossible de sélectionner le filtre 24h : {e}")

        print(f"   ✓ Tunnel et filtres complétés ! Page actuelle : {page.url}")
        return True

    except Exception as e:
        print(f"   ⚠️ Échec du tunnel : {e}")
        return False


def _collect_cards(page) -> list[dict]:
    try:
        page.wait_for_selector("a[href*='/jobs/']", timeout=12000)
    except Exception:
        print("   ⚠️ Timeout lors du chargement des cartes.")

    for _ in range(3):
        page.evaluate("window.scrollBy(0, 800)")
        page.wait_for_timeout(800)

    cards = []
    seen_urls = set()

    job_links = page.locator("a[href*='/jobs/']").all()

    for card in job_links:
        try:
            link = card.get_attribute("href") or ""
            if not link or "/get-started" in link:
                continue

            full_url = (link if link.startswith("http") else BASE_URL + link).split("?")[0]
            if full_url in seen_urls:
                continue

            raw_text = card.inner_text().strip()
            if not raw_text:
                continue

            lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
            title = lines[0] if lines else ""

            if len(title) < 3 or title.lower() in ["voir plus", "suivant", "précédent", "postuler", "en savoir plus"]:
                continue

            seen_urls.add(full_url)
            match = re.search(r"/companies/([^/]+)/jobs", link)
            company = match.group(1).replace("-", " ").title() if match else "N/A"
            slug, city = _parse_job_url(full_url)

            cards.append({
                "id": f"wttj_{slug}",
                "title": title,
                "company": company,
                "url": full_url,
                "location": city,
            })
        except Exception:
            continue

    return cards


def _get_description(page, url: str) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(1000)

        section = page.locator("#the-position-section")
        if section.count() > 0:
            text = section.first.inner_text()
        else:
            text = page.locator("main").first.inner_text()
        return text.strip()
    except Exception as e:
        print(f"    ⚠️ Description WTTJ indisponible : {str(e)[:80]}")
        return ""


def fetch_offers_for_keyword(browser, keyword: str, location: str = "France") -> list[JobOffer]:
    offers = []

    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=USER_AGENT,
        locale="fr-FR",
        timezone_id="Europe/Paris"
    )
    page = context.new_page()

    try:
        search_ok = _run_search_flow(page, keyword, location)
        if not search_ok:
            print(f"  ⚠️ Recherche en échec pour '{keyword}' : mot-clé ignoré")
            return []

        cards = _collect_cards(page)
        print(f"  → {len(cards)} offres trouvées pour '{keyword}' (≤24h)")

        candidates = []
        for c in cards:
            raw = {
                "typeContrat": "CDI",
                "intitule": c["title"],
                "description": "",
                "secteurActiviteLibelle": "",
                "entreprise": {"nom": c["company"]},
            }
            if not passes_hard_filters(raw, debug=True):
                print(f"  ✗ Filtrée (critères titre) : {c['title']} — {c['company']}")
                continue
            candidates.append(c)

        print(f"  → {len(candidates)} candidat(e)s après filtrage rapide")

        if len(candidates) > MAX_CANDIDATES_TO_CHECK:
            print(f"  → limite à {MAX_CANDIDATES_TO_CHECK} candidat(e)s vérifié(e)s")
            candidates = candidates[:MAX_CANDIDATES_TO_CHECK]

        for c in candidates:
            description = _get_description(page, c["url"])

            if not description:
                print(f"  ✗ Filtrée (description introuvable/timeout) : {c['title']}")
                continue

            raw_full = {
                "typeContrat": _detect_contract(description),
                "intitule": c["title"],
                "description": description,
                "secteurActiviteLibelle": "",
                "entreprise": {"nom": c["company"]},
            }
            if not passes_hard_filters(raw_full, debug=True):
                print(f"  ✗ Filtrée (critères complets) : {c['title']} — {c['company']}")
                continue

            print(f"  ✓ Retenue : {c['title']} — {c['company']}")
            offers.append(JobOffer(
                id=c["id"],
                title=c["title"],
                company=c["company"],
                description=description[:2000],
                url=c["url"],
                location=c["location"],
                source="wttj",
                posted_date="dernières 24h",
                raw_data={},
            ))

    except Exception as e:
        print(f"  ⚠️ WTTJ '{keyword}' en échec : {str(e)[:120]}")
    finally:
        context.close()

    return offers


def fetch_offers_batch(keywords: list[str], location: str = "France",
                        headless: bool = True, slow_mo: int = 0) -> dict[str, list[JobOffer]]:
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=["--disable-blink-features=AutomationControlled"]
        )
        for keyword in keywords:
            try:
                results[keyword] = fetch_offers_for_keyword(browser, keyword, location)
            except Exception as e:
                print(f"  ⚠️ Erreur mot-clé '{keyword}' : {e}")
                results[keyword] = []

            time.sleep(2)

        browser.close()
    return results


if __name__ == "__main__":
    print("🚀 Démarrage de la collecte globale WTTJ...")
    
    keywords_to_search = PROFILE.get("job_titles", ["Data Engineer"])

    res = fetch_offers_batch(keywords_to_search, location="France", headless=False, slow_mo=300)

    for kw, offers in res.items():
        print(f"\nRÉSULTATS pour '{kw}' : {len(offers)} offre(s) retenue(s)")
        for o in offers:
            print(f" - {o.title} | {o.company} | {o.location} | {o.url}")