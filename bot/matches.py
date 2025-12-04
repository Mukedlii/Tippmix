from datetime import datetime

def fetch_matches_for_today():
    """
    Itt kell majd a VALÓDI sport API-t hívni (API-Football, TheOddsAPI stb.).
    Most visszaadunk pár példa-meccset, hogy menjen a rendszer.
    """

    today = datetime.utcnow().date().isoformat()

    sample_matches = [
        {
            "id": 1,
            "league": "Premier League",
            "home": "Manchester United",
            "away": "West Ham",
            "start_time": f"{today}T20:00:00Z",
            "odds": {"home": 1.47, "draw": 4.50, "away": 6.50},
            "stats": {
                "home_last5": "4W1L",
                "away_last5": "1W1D3L",
                "home_goals_for_avg": 2.1,
                "home_goals_against_avg": 0.8,
                "away_goals_for_avg": 0.9,
                "away_goals_against_avg": 1.7,
                "note": "Hazai xG magasabb, több kapura lövés."
            },
        },
        {
            "id": 2,
            "league": "Serie B",
            "home": "Juve Stabia",
            "away": "Bari",
            "start_time": f"{today}T18:30:00Z",
            "odds": {"home": 1.90, "draw": 3.20, "away": 4.20},
            "stats": {
                "home_last5": "3W1D1L",
                "away_last5": "1W2D2L",
                "home_goals_for_avg": 1.4,
                "home_goals_against_avg": 0.9,
                "away_goals_for_avg": 0.8,
                "away_goals_against_avg": 1.3,
                "note": "Hazai stabil otthon, Bari idegenben gyengébb."
            },
        },
        {
            "id": 3,
            "league": "Brazil Serie A",
            "home": "Cruzeiro",
            "away": "Botafogo",
            "start_time": f"{today}T22:30:00Z",
            "odds": {"home": 2.05, "draw": 3.10, "away": 3.60},
            "stats": {
                "home_last5": "2W2D1L",
                "away_last5": "2W1D2L",
                "home_goals_for_avg": 1.3,
                "home_goals_against_avg": 1.1,
                "away_goals_for_avg": 1.2,
                "away_goals_against_avg": 1.2,
                "note": "Kiegyenlített, de hazai pálya dönthet."
            },
        },
    ]

    return sample_matches
