"""
bot/api_keys.py

A projekt kizárólag ingyenes, API-kulcs nélküli forrásokból dolgozik
(SofaScore / Flashscore / LiveScore scraping). Nincs fizetős API
(SPORTS_API_KEY, ODDS_API_KEY, SPORTMONKS_API_TOKEN, SPORTSDATAIO_API,
ALLSPORTSAPI_KEY, OPENAI_API_KEY, stb.) a kódbázisban.
"""


def resolve_sports_provider() -> str:
    """Mindig az ingyenes scraper providert adja vissza.

    A korábbi verzió itt több fizetős API (api-sports, sportmonks,
    sportsdataio, allsportsapi) közül választott. Ezeket kivettük –
    a bot kizárólag a szabadon elérhető, publikus weboldalak
    scrapelésével dolgozik, kulcs nélkül.
    """
    return "free_scraper"
