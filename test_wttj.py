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
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

OVERLAY_JS = (
    "document.querySelectorAll('#axeptio_overlay, .axeptio_widget, iframe')"
    ".forEach(e => e.remove());"
)


def _remove_overlays(page):
    """Supprime le bandeau cookies (Axeptio) qui bloque les clics."""
    try:
        page.evaluate(OVERLAY_JS)
    except Exception:
        pass


def _detect_contract(text: str) -> str:
    """Détecte le type de contrat dans le texte de la page de détail."""
    m = re.search(r"\b(CDI|CDD)\b", text)
    if m:
        return m.group(1)
    if re.search(r"\b(stage|alternance|apprentissage|freelance|int[eé]rim)\b", text, re.IGNORECASE):
        return "AUTRE"
    return "CDI"


def _parse_job_url(url: str):
    """Extrait un identifiant stable et la ville depuis l'URL d'une offre."""
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    parts = slug.split("_")
    city = parts[1].replace("-", " ").title() if len(parts) >= 3 else ""
    return slug, city


def _run_search_flow(page, query: str, location: str) -> bool:
    """Parcours d'accueil WTTJ (intitulé -> expérience -> localisation) puis filtre 24h."""
    # Étape 1 : Intitulé
    page.goto(f"{BASE_URL}/fr/get-started/job-title", wait_until="domcontentloaded", timeout=12000)
    page.wait_for_timeout(1000)
    _remove_overlays(page)

    input_box = page.locator("input[type='text']").first
    input_box.wait_for(state="visible", timeout=8000)
    input_box.click()
    input_box.fill(query)
    page.wait_for_timeout(1000)
    try:
        page.locator("ul li, div[role='option'], li[role='option']").first.click(timeout=3000)
    except Exception:
        pass

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(500)
    page.locator("button:has-text('Suivant')").last.click(timeout=5000)

    # Étape 2 : Niveau d'expérience (Junior 1-3 ans)
    page.wait_for_url("**/get-started/experience-level**", timeout=10000)
    _remove_overlays(page)
    exp_option = page.locator("label[data-testid='experienceLevel-option-one_to_three']")
    exp_option.wait_for(state="visible", timeout=8000)
    exp_option.click()
    page.wait_for_timeout(500)
    page.locator("button:has-text('Suivant')").last.click(timeout=5000)

    # Étape 3 : Localisation
    page.wait_for_url("**/get-started/location**", timeout=10000)
    _remove_overlays(page)
    loc_input = page.locator("input[data-testid='location-search-input']").first
    loc_input.wait_for(state="visible", timeout=8000)
    loc_input.click()
    loc_input.fill(location)
    page.wait_for_timeout(1000)
    try:
        page.locator("div[role='listbox'] div, ul li, li[role='option']").first.click(timeout=3000)
    except Exception:
        page.keyboard.press("Enter")

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(500)
    page.locator("button:has-text('Découvrir mes jobs')").last.click(timeout=5000)

    # Étape 4 : Page de résultats + filtre 24h
    print("   Application du filtre 24h...")
    page.wait_for_url("**/jobs-preview**", timeout=12000)
    page.wait_for_timeout(2500)
    _remove_overlays(page)

    try:
        date_dropdown = page.get_by_text("Toutes les dates").first
        date_dropdown.wait_for(state="visible", timeout=5000)
        date_dropdown.click()
        page.wait_for_timeout(800)

        option_24h = page.get_by_text("Dernières 24 heures").first
        option_24h.wait_for(state="visible", timeout=5000)
        option_24h.click()
        
        print("   ✓ Filtre 24h appliqué avec succès !")
        page.wait_for_timeout(2000)
        return True
    except Exception as e:
        print(f"   ⚠️ Échec du clic sur le filtre 24h : {e}")
        return False


def _collect_cards(page) -> list[dict]:
    """Fait défiler la page puis récupère les cartes d'offres."""
    for _ in range(3):
        page.evaluate("window.scrollBy(0, 800)")
        page.wait_for_timeout(1000)

    cards = []
    seen_urls = set()

    for card in page.locator("a[href*='/jobs/']").all():
        link = card.get_attribute("href")
        if not link or "/companies/" not in link:
            continue

        full_url = (link if link.startswith("http") else BASE_URL + link).split("?")[0]
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        raw_text = card.inner_text().strip()
        title = raw_text.split("\n")[0].strip() if raw_text else ""
        if not title:
            continue

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

    return cards


def _get_description(page, url: str) -> str:
    """Texte de la page de détail."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(1000)
        _remove_overlays(page)

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
    )
    page = context.new_page()

    try:
        date_filter_ok = _run_search_flow(page, keyword, location)
        if not date_filter_ok:
            print(f"  ⚠️ Filtre 24h non appliqué pour '{keyword}' : mot-clé ignoré")
            return []

        cards = _collect_cards(page)
        print(f"  → {len(cards)} offres trouvées pour '{keyword}' (≤24h)")

        # Passe 1 : filtrage rapide
        candidates = []
        for c in cards:
            raw = {
                "typeContrat": "CDI",
                "intitule": c["title"],
                "description": "",
                "secteurActiviteLibelle": "",
                "entreprise": {"nom": c["company"]},
            }
            if not passes_hard_filters(raw):
                print(f"  ✗ Filtrée (critères titre) : {c['title']} — {c['company']}")
                continue
            candidates.append(c)

        print(f"  → {len(candidates)} candidat(e)s après filtrage rapide")

        if len(candidates) > MAX_CANDIDATES_TO_CHECK:
            print(f"  → limite à {MAX_CANDIDATES_TO_CHECK} candidat(e)s vérifié(e)s")
            candidates = candidates[:MAX_CANDIDATES_TO_CHECK]

        # Passe 2 : lecture de la description + filtres complets
        for c in candidates:
            description = _get_description(page, c["url"])

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
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        for keyword in keywords:
            try:
                results[keyword] = fetch_offers_for_keyword(browser, keyword, location)
            except Exception as e:
                print(f"  ⚠️ Erreur mot-clé '{keyword}' : {e}")
                results[keyword] = []
            
            # Pause de 2 secondes pour éviter d'être bloqué par WTTJ sur les mots-clés suivants
            time.sleep(2)
            
        browser.close()
    return results


if __name__ == "__main__":
    headless = os.getenv("WTTJ_HEADLESS", "0") == "1"
    res = fetch_offers_batch(["Data Engineer", "Data Analyst"], headless=headless, slow_mo=0 if headless else 100)
    for kw, offers in res.items():
        print(f"\n{kw} : {len(offers)} offres retenues")
        for o in offers:
            print(f" - {o.title} | {o.company} | {o.location} | {o.url}")