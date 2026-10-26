import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from playwright.sync_api import sync_playwright
from collectors.base import JobOffer
from processing.filters import passes_hard_filters
from processing.recency import is_recent_indeed_text

SEARCH_URL = "https://www.hellowork.com/fr-fr/emploi/recherche.html"
MAX_CANDIDATES_TO_CHECK = 8

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def _clean_page_text(full_text: str) -> str:
    end_markers = [
        "ces offres pourraient aussi",
        "recherches similaires",
        "créez votre compte hellowork",
    ]
    lower_text = full_text.lower()
    cut_idx = len(full_text)
    for marker in end_markers:
        idx = lower_text.find(marker)
        if idx != -1 and idx < cut_idx:
            cut_idx = idx
    cleaned = full_text[:cut_idx].strip()
    cleaned = cleaned.replace("Aller au contenu principal", "")
    return cleaned.strip()


def _extract_job_content_fast(soup: BeautifulSoup) -> str:
    """Extrait le contenu des accordéons 'Missions'/'Profil recherché',
    ET le badge d'expérience (souvent hors accordéon, dans les métadonnées du poste)."""
    parts = []

    for li in soup.find_all("li"):
        li_text = li.get_text(strip=True)
        if re.search(r"exp\.?\s*\d", li_text, re.IGNORECASE):
            parts.append(li_text)

    for details in soup.find_all("details"):
        summary = details.find("summary")
        if not summary:
            continue
        summary_text = summary.get_text(strip=True).lower()
        if "profil recherche" in summary_text or "missions du poste" in summary_text or "profil recherché" in summary_text:
            parts.append(details.get_text(separator=" ", strip=True))

    return " ".join(parts).strip()


def _get_full_description_fast(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")

        targeted = _extract_job_content_fast(soup)
        if targeted and len(targeted) > 100:
            return targeted

        raw_text = soup.get_text(separator=" ", strip=True)
        return _clean_page_text(raw_text)
    except Exception:
        return ""


def _get_full_description(page, url: str) -> str:
    fast_result = _get_full_description_fast(url)
    if fast_result and len(fast_result) > 100:
        return fast_result

    try:
        page.goto(url, timeout=10000)
        page.wait_for_timeout(1000)

        try:
            cookie_button = page.query_selector("text=Continuer sans accepter")
            if cookie_button:
                cookie_button.click()
                page.wait_for_timeout(500)
            else:
                accept_button = page.query_selector("text=Tout accepter")
                if accept_button:
                    accept_button.click()
                    page.wait_for_timeout(500)
        except Exception:
            pass

        targeted = page.evaluate("""
            () => {
                let parts = [];

                const lis = Array.from(document.querySelectorAll('li'));
                for (const li of lis) {
                    const t = (li.textContent || '').trim();
                    if (/exp\\.?\\s*\\d/i.test(t)) {
                        parts.push(t);
                    }
                }

                const detailsList = Array.from(document.querySelectorAll('details'));
                for (const d of detailsList) {
                    const summary = d.querySelector('summary');
                    if (!summary) continue;
                    const st = (summary.textContent || '').toLowerCase();
                    if (st.includes('profil recherche') || st.includes('missions du poste')) {
                        parts.push(d.textContent || '');
                    }
                }

                return parts.join(' ').trim();
            }
        """)

        if targeted and len(targeted) > 100:
            return targeted

        raw_text = page.inner_text("body")
        return _clean_page_text(raw_text)

    except Exception as e:
        print(f"    ⚠️ Impossible de charger la description complète : {e}")
        return ""


def fetch_offers_for_keyword(page, keyword: str, max_hours: int = 48) -> list[JobOffer]:
    offers = []

    url = f"{SEARCH_URL}?k={quote(keyword)}&st=date&d=h"
    page.goto(url, timeout=30000)
    page.wait_for_timeout(2000)

    try:
        cookie_button = page.query_selector("text=Continuer sans accepter")
        if cookie_button:
            cookie_button.click()
            page.wait_for_timeout(500)
    except Exception:
        pass

    cards = page.query_selector_all("li[data-id-storage-target='item']")
    print(f"  → {len(cards)} cartes trouvées pour '{keyword}' (≤24h, triées par date)")

    consecutive_old = 0
    candidates = []

    for card in cards:
        title_el = card.query_selector('a[data-cy="offerTitle"] h3 p:first-child')
        company_el = card.query_selector('a[data-cy="offerTitle"] h3 p:nth-child(2)')
        link_el = card.query_selector('a[data-cy="offerTitle"]')
        location_el = card.query_selector('[data-cy="localisationCard"]')
        contract_el = card.query_selector('[data-cy="contractCard"]')
        date_el = card.query_selector('.typo-s.text-grey-500.pl-1.pt-1')

        if not title_el or not link_el:
            continue

        title = title_el.inner_text().strip()
        company = company_el.inner_text().strip() if company_el else "N/A"
        location = location_el.inner_text().strip() if location_el else ""
        raw_contract = contract_el.inner_text().strip() if contract_el else "CDI"
        posted_text = date_el.inner_text().strip() if date_el else ""
        href = link_el.get_attribute("href") or ""
        url_job = f"https://www.hellowork.com{href}" if href.startswith("/") else href
        offer_id = href.split("/")[-1].replace(".html", "") if href else ""

        # Normalisation rapide du contrat (ex: "CDI 39h" -> "CDI")
        if "cdi" in raw_contract.lower():
            contract = "CDI"
        elif "cdd" in raw_contract.lower():
            contract = "CDD"
        else:
            contract = "AUTRE"

        if not is_recent_indeed_text(posted_text, max_hours=max_hours):
            print(f"  ✗ Filtrée (date : '{posted_text}') : {title} — {company}")
            consecutive_old += 1
            if consecutive_old >= 3:
                print(f"  ⏹ Arrêt anticipé : {consecutive_old} offres trop vieilles d'affilée")
                break
            continue
        else:
            consecutive_old = 0

        raw = {
            "typeContrat": contract,
            "intitule": title,
            "description": "",
            "secteurActiviteLibelle": "",
            "entreprise": {"nom": company},
        }

        # MODIFICATION : debug=True activé ici pour afficher la cause du rejet
        if not passes_hard_filters(raw, debug=True):
            print(f"  ✗ Filtrée (critères titre) : {title} — {company}")
            continue

        candidates.append({
            "id": f"hellowork_{offer_id}",
            "title": title,
            "company": company,
            "location": location,
            "url": url_job,
            "posted_date": posted_text,
            "contract": contract,
        })

    print(f"  → {len(candidates)} candidat(e)s après filtrage rapide")

    if len(candidates) > MAX_CANDIDATES_TO_CHECK:
        print(f"  → limite à {MAX_CANDIDATES_TO_CHECK} candidat(e)s vérifié(e)s (les plus récent(e)s)")
        candidates = candidates[:MAX_CANDIDATES_TO_CHECK]

    for c in candidates:
        full_text = _get_full_description(page, c["url"])

        raw_full = {
            "typeContrat": c["contract"],
            "intitule": c["title"],
            "description": full_text,
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
            description=full_text[:2000],
            url=c["url"],
            location=c["location"],
            source="hellowork",
            posted_date=c["posted_date"],
            raw_data={},
        ))

    return offers


def fetch_offers(keyword: str, max_hours: int = 48) -> list[JobOffer]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())
        offers = fetch_offers_for_keyword(page, keyword, max_hours)
        browser.close()
        return offers


def fetch_offers_batch(keywords: list[str], max_hours: int = 48) -> dict[str, list[JobOffer]]:
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())

        for keyword in keywords:
            results[keyword] = fetch_offers_for_keyword(page, keyword, max_hours)

        browser.close()
    return results


if __name__ == "__main__":
    offers = fetch_offers("Data Engineer")
    print(f"{len(offers)} offres retenues après filtrage")
    if offers:
        print(offers[0])