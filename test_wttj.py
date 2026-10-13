import time
import re
from playwright.sync_api import sync_playwright

def scrape_wttj_complet(query="data engineer", location="France"):
    jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=150)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        page = context.new_page()

        # --- ÉTAPE 1 : Intitulé de poste ---
        print("1. Saisie de l'intitulé de poste...")
        page.goto("https://www.welcometothejungle.com/fr/get-started/job-title", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        page.evaluate("document.querySelectorAll('#axeptio_overlay, .axeptio_widget, iframe').forEach(e => e.remove());")

        input_box = page.locator("input[type='text']").first
        input_box.click()
        input_box.fill(query)
        page.wait_for_timeout(1000)

        try:
            page.locator("ul li, div[role='option'], li[role='option']").first.click(timeout=3000)
            page.wait_for_timeout(800)
        except Exception:
            pass

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)
        try:
            page.locator("button:has-text('Suivant')").last.click(timeout=3000)
        except Exception:
            page.keyboard.press("Enter")

        # --- ÉTAPE 2 : Niveau d'expérience ---
        print("2. Sélection du niveau d'expérience...")
        page.wait_for_url("**/get-started/experience-level**", timeout=10000)
        page.wait_for_timeout(1000)
        page.evaluate("document.querySelectorAll('#axeptio_overlay, .axeptio_widget, iframe').forEach(e => e.remove());")

        page.locator("label[data-testid='experienceLevel-option-one_to_three']").click()
        page.wait_for_timeout(1000)

        next_button = page.locator("button:has-text('Suivant')").last
        next_button.scroll_into_view_if_needed()
        next_button.click()

        # --- ÉTAPE 3 : Localisation ---
        print("3. Saisie de la localisation...")
        page.wait_for_url("**/get-started/location**", timeout=10000)
        page.wait_for_timeout(1000)
        page.evaluate("document.querySelectorAll('#axeptio_overlay, .axeptio_widget, iframe').forEach(e => e.remove());")

        loc_input = page.locator("input[data-testid='location-search-input']").first
        loc_input.click()
        loc_input.fill(location)
        page.wait_for_timeout(1200)

        try:
            page.locator("div[role='listbox'] div, ul li, li[role='option']").first.click(timeout=3000)
            page.wait_for_timeout(800)
        except Exception:
            page.keyboard.press("Enter")

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)
        
        try:
            discover_btn = page.locator("button:has-text('Découvrir mes jobs')").last
            discover_btn.click(timeout=3000)
        except Exception:
            page.keyboard.press("Enter")

        # --- ÉTAPE 4 : Application du filtre "Dernières 24 heures" ---
        print("4. Application du filtre de date (Dernières 24h)...")
        page.wait_for_url("**/jobs-preview**", timeout=15000)
        page.wait_for_timeout(3000)

        # Clic sur le menu déroulant "Toutes les dates"
        try:
            date_dropdown = page.locator("button:has-text('Toutes les dates'), div:has-text('Toutes les dates')").last
            date_dropdown.click(timeout=3000)
            page.wait_for_timeout(800)

            # Clic sur l'option "Dernières 24 heures"
            last_24h_option = page.locator("text='Dernières 24 heures'").first
            last_24h_option.click(timeout=3000)
            print("Filtre 24h appliqué !")
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"Erreur lors du choix du filtre de date : {e}")

        # --- ÉTAPE 5 : Extraction des offres filtrées ---
        print("5. Extraction des résultats récents...")
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 800)")
            page.wait_for_timeout(1000)

        cards = page.locator("a[href*='/jobs/']").all()
        seen_urls = set()

        for card in cards:
            link = card.get_attribute("href")
            if link and "/companies/" in link and link not in seen_urls:
                seen_urls.add(link)
                full_url = link if link.startswith("http") else f"https://www.welcometothejungle.com{link}"
                
                raw_text = card.inner_text().strip()
                title = raw_text.split("\n")[0] if raw_text else "Offre WTTJ"
                
                match = re.search(r'/companies/([^/]+)/jobs', link)
                if match:
                    company = match.group(1).replace("-", " ").title()
                else:
                    company = "Entreprise WTTJ"

                jobs.append({
                    "title": title,
                    "company": company,
                    "url": full_url
                })

        browser.close()

    return jobs

if __name__ == "__main__":
    resultats = scrape_wttj_complet("data engineer", "France")
    print(f"\n{len(resultats)} offres des dernières 24h récupérées :")
    for job in resultats[:10]:
        print(f"- {job['title']} chez {job['company']}")
        print(f"  {job['url']}")