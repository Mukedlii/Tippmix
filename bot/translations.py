"""
Fordítási map - angol -> magyar tipp nevek
"""

# Piaci típusok
MARKET_NAMES_HU = {
    "1X2": "1X2 (Végeredmény)",
    "OU": "Gólok száma",
    "BTTS": "Mindkét csapat góloz",
    "DNB": "DNB (Döntetlen visszajár)",
}

# Tipp nevek
TIP_NAMES_HU = {
    # 1X2
    "Hazai győzelem": "Hazai győzelem",
    "Döntetlen": "Döntetlen",
    "Vendég győzelem": "Vendég győzelem",
    "Home": "Hazai győzelem",
    "Draw": "Döntetlen", 
    "Away": "Vendég győzelem",
    
    # Over/Under
    "Over 2.5": "2.5 felett (min. 3 gól)",
    "Under 2.5": "2.5 alatt (max. 2 gól)",
    "Over 3.5": "3.5 felett (min. 4 gól)",
    "Under 3.5": "3.5 alatt (max. 3 gól)",
    
    # BTTS
    "BTTS: YES": "Mindkét csapat góloz",
    "BTTS: NO": "Legalább egy 0-n marad",
    "Both Teams To Score": "Mindkét csapat góloz",
    
    # DNB
    "Hazai DNB": "Hazai (döntetlen visszajár)",
    "Vendég DNB": "Vendég (döntetlen visszajár)",
    "Home DNB": "Hazai (döntetlen visszajár)",
    "Away DNB": "Vendég (döntetlen visszajár)",
}


def translate_tip(tip_name: str) -> str:
    """
    Fordít egy tipp nevet magyarra.
    
    Args:
        tip_name: Angol vagy vegyes tipp név
    
    Returns:
        Magyar tipp név
    """
    return TIP_NAMES_HU.get(tip_name, tip_name)


def translate_market(market_code: str) -> str:
    """
    Fordít egy piaci kódot magyarra.
    
    Args:
        market_code: Piaci kód (1X2, OU, BTTS, DNB)
    
    Returns:
        Magyar piaci név
    """
    return MARKET_NAMES_HU.get(market_code, market_code)
