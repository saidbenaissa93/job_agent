from playwright.sync_api import sync_playwright

URL = "https://www.welcometothejungle.com/fr/jobs?query=data%20engineer"

JS = """
() => {
    const links = Array.from(document.querySelectorAll("a[href*='/jobs/']"));
    return links.slice(0, 5).map(a => {
        let card = a;
        for (let i = 0; i < 5 && card.parentElement; i++) card = card.parentElement;
        return {
            href: a.href,
            text: a.innerText.slice(0, 100),
            cardTag: card.tagName,
            cardTestId: card.getAttribute("data-testid"),
            cardHtml: card.outerHTML.slice(0, 600)
        };
    });
}
"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    print("URL au chargement :", page.url)

    try:
        page.click("text=Non merci", timeout=5000)
    except Exception:
        print("Pas de bandeau cookies")

    # Laisse la page se stabiliser (redirections, rechargements éventuels)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        print("networkidle non atteint, on continue")
    page.wait_for_timeout(3000)

    print("URL après stabilisation :", page.url)

    info = None
    for attempt in range(3):
        try:
            info = page.evaluate(JS)
            break
        except Exception as e:
            print(f"Tentative {attempt + 1} échouée : {str(e)[:80]}")
            page.wait_for_timeout(3000)

    print("URL finale :", page.url)
    if info:
        for i in info:
            print(i)
    else:
        print("Aucun lien trouvé")

    page.screenshot(path="wttj_result.png")
    input("Entrée pour fermer...")
    browser.close()