"""
bot/weather.py

Weather API Integration for Match Analysis
- Fetch weather conditions for match venues
- Analyze impact on play style and scoring
- Integrate with OpenWeatherMap API
"""

from __future__ import annotations

import logging
import os
import requests
import time
from typing import Dict, Optional
from datetime import datetime

log = logging.getLogger(__name__)


class WeatherAnalyzer:
    """Fetch and analyze weather conditions for football matches."""

    def __init__(self):
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self.cache = {}
        self.cache_timeout = 3600  # 1 hour

    def get_weather(self, city: str, country: str, match_time: str) -> Optional[Dict]:
        """
        Fetch weather forecast for a match.
        
        Args:
            city: Stadium city (e.g., "London")
            country: Country code (e.g., "GB")
            match_time: ISO datetime string
        
        Returns:
            {
                "temp": 15.5,  # Celsius
                "feels_like": 13.2,
                "humidity": 75,  # percentage
                "wind_speed": 8.5,  # m/s
                "precipitation": 2.5,  # mm
                "condition": "Rain",
                "description": "light rain",
                "impact": "moderate",  # low/moderate/high
                "analysis": "Wet conditions may favor defensive play..."
            }
        """
        if not self.api_key:
            log.warning("OPENWEATHER_API_KEY not set")
            return None

        cache_key = f"{city}_{country}_{match_time[:10]}"
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if time.time() - cached_time < self.cache_timeout:
                return cached_data

        try:
            # Use 5-day forecast API
            url = "https://api.openweathermap.org/data/2.5/forecast"
            params = {
                "q": f"{city},{country}",
                "appid": self.api_key,
                "units": "metric",
            }

            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                log.warning(f"OpenWeather API error: {response.status_code}")
                return None

            data = response.json()
            
            # Find forecast closest to match time
            match_dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
            match_timestamp = match_dt.timestamp()
            
            closest_forecast = None
            min_diff = float('inf')
            
            for forecast in data.get("list", []):
                forecast_timestamp = forecast.get("dt", 0)
                diff = abs(forecast_timestamp - match_timestamp)
                
                if diff < min_diff:
                    min_diff = diff
                    closest_forecast = forecast
            
            if not closest_forecast:
                return None
            
            # Extract weather data
            main = closest_forecast.get("main", {})
            weather = closest_forecast.get("weather", [{}])[0]
            wind = closest_forecast.get("wind", {})
            rain = closest_forecast.get("rain", {})
            snow = closest_forecast.get("snow", {})
            
            weather_data = {
                "temp": main.get("temp", 0),
                "feels_like": main.get("feels_like", 0),
                "humidity": main.get("humidity", 0),
                "wind_speed": wind.get("speed", 0),
                "precipitation": rain.get("3h", 0) + snow.get("3h", 0),
                "condition": weather.get("main", "Clear"),
                "description": weather.get("description", ""),
            }
            
            # Analyze impact
            impact_analysis = self._analyze_impact(weather_data)
            weather_data.update(impact_analysis)
            
            self.cache[cache_key] = (weather_data, time.time())
            
            return weather_data

        except Exception as e:
            log.error(f"get_weather error: {e}")
            return None

    def _analyze_impact(self, weather: Dict) -> Dict:
        """
        Analyze weather impact on match.
        
        Returns:
            {
                "impact": "low/moderate/high",
                "analysis": "Detailed analysis text",
                "factors": ["rain", "wind", "cold"]
            }
        """
        temp = weather.get("temp", 15)
        wind = weather.get("wind_speed", 0)
        precip = weather.get("precipitation", 0)
        condition = weather.get("condition", "").lower()
        
        impact_score = 0
        factors = []
        analysis_parts = []
        
        # Temperature impact
        if temp < 5:
            impact_score += 2
            factors.append("cold")
            analysis_parts.append("Hideg időjárás → lassabb játék, több fizikai megterhelés")
        elif temp > 30:
            impact_score += 2
            factors.append("heat")
            analysis_parts.append("Meleg időjárás → fáradtság, több szünet, lassabb tempó")
        
        # Wind impact
        if wind > 10:
            impact_score += 3
            factors.append("strong_wind")
            analysis_parts.append("Erős szél → pontatlan passzok, nehéz labdakezelés, alacsonyabb gólszám")
        elif wind > 6:
            impact_score += 1
            factors.append("wind")
            analysis_parts.append("Szeles → kicsit pontatlanabb játék")
        
        # Precipitation impact
        if precip > 5:
            impact_score += 3
            factors.append("heavy_rain")
            analysis_parts.append("Erős eső → csúszós pálya, védők előnyben, kisebb gólszám várható")
        elif precip > 1:
            impact_score += 2
            factors.append("rain")
            analysis_parts.append("Eső → nedves pálya, defenzív játék valószínűbb")
        
        if "snow" in condition:
            impact_score += 4
            factors.append("snow")
            analysis_parts.append("Havazás → extrém feltételek, kiszámíthatatlan meccs")
        
        # Determine overall impact level
        if impact_score >= 5:
            impact = "high"
        elif impact_score >= 2:
            impact = "moderate"
        else:
            impact = "low"
        
        # Default analysis if no factors
        if not analysis_parts:
            analysis_parts.append("Jó időjárási feltételek, nincs jelentős hatás")
        
        return {
            "impact": impact,
            "impact_score": impact_score,
            "factors": factors,
            "analysis": " | ".join(analysis_parts),
        }

    def get_stadium_location(self, team_name: str) -> Optional[Dict[str, str]]:
        """
        Get stadium location for a team.
        In production, this should query a database of team stadiums.
        For now, using a basic mapping.
        """
        # Simplified stadium mapping (expand as needed)
        stadium_map = {
            # Premier League
            "Arsenal": {"city": "London", "country": "GB"},
            "Chelsea": {"city": "London", "country": "GB"},
            "Liverpool": {"city": "Liverpool", "country": "GB"},
            "Manchester United": {"city": "Manchester", "country": "GB"},
            "Manchester City": {"city": "Manchester", "country": "GB"},
            "Tottenham": {"city": "London", "country": "GB"},
            
            # La Liga
            "Real Madrid": {"city": "Madrid", "country": "ES"},
            "Barcelona": {"city": "Barcelona", "country": "ES"},
            "Atletico Madrid": {"city": "Madrid", "country": "ES"},
            
            # Bundesliga
            "Bayern Munich": {"city": "Munich", "country": "DE"},
            "Borussia Dortmund": {"city": "Dortmund", "country": "DE"},
            
            # Serie A
            "Juventus": {"city": "Turin", "country": "IT"},
            "AC Milan": {"city": "Milan", "country": "IT"},
            "Inter Milan": {"city": "Milan", "country": "IT"},
            
            # Ligue 1
            "PSG": {"city": "Paris", "country": "FR"},
            "Paris Saint Germain": {"city": "Paris", "country": "FR"},
            "Marseille": {"city": "Marseille", "country": "FR"},
        }
        
        # Try exact match
        if team_name in stadium_map:
            return stadium_map[team_name]
        
        # Try partial match
        for team, location in stadium_map.items():
            if team.lower() in team_name.lower():
                return location
        
        return None


def enrich_with_weather(dossier: Dict) -> Dict:
    """
    Enrich match dossier with weather data.
    """
    if os.getenv("TIPPMIX_USE_WEATHER", "1") != "1":
        return dossier
    
    analyzer = WeatherAnalyzer()
    
    home_team = dossier.get("home", "")
    kickoff = dossier.get("kickoff", "")
    
    if not home_team or not kickoff:
        return dossier
    
    try:
        # Get stadium location
        location = analyzer.get_stadium_location(home_team)
        
        if not location:
            # Try to extract city from league/country info
            country = dossier.get("country", "")
            if country:
                # Use country capital as fallback
                capitals = {
                    "England": {"city": "London", "country": "GB"},
                    "Spain": {"city": "Madrid", "country": "ES"},
                    "Germany": {"city": "Berlin", "country": "DE"},
                    "Italy": {"city": "Rome", "country": "IT"},
                    "France": {"city": "Paris", "country": "FR"},
                }
                location = capitals.get(country)
        
        if not location:
            return dossier
        
        # Fetch weather
        weather = analyzer.get_weather(
            city=location["city"],
            country=location["country"],
            match_time=kickoff
        )
        
        if weather:
            dossier["weather"] = weather
        
        return dossier
        
    except Exception as e:
        log.warning(f"Failed to enrich weather for {dossier.get('fixture_id')}: {e}")
        return dossier


def format_weather_context(dossier: Dict) -> str:
    """Format weather analysis for AI context."""
    weather = dossier.get("weather")
    
    if not weather:
        return ""
    
    impact = weather.get("impact", "low")
    impact_emoji = {"low": "🌤️", "moderate": "⛅", "high": "⛈️"}.get(impact, "🌤️")
    
    lines = [
        f"{impact_emoji} Időjárás ({weather.get('condition', 'N/A')}): "
        f"{weather.get('temp', 0):.1f}°C, szél: {weather.get('wind_speed', 0):.1f} m/s, "
        f"csapadék: {weather.get('precipitation', 0):.1f} mm"
    ]
    
    if impact != "low":
        lines.append(f"   ⚠️ Hatás: {weather.get('analysis', '')}")
    
    return "\n".join(lines)
