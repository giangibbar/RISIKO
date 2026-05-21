"""Complete Risiko world map: 42 territories, 6 continents, adjacencies."""

from typing import Dict, List, Set

# Continent bonus troops for holding all territories in a continent
CONTINENT_BONUSES: Dict[str, int] = {
    "north_america": 5,
    "south_america": 2,
    "europe": 5,
    "africa": 3,
    "asia": 7,
    "oceania": 2,
}

# Territories grouped by continent
CONTINENTS: Dict[str, List[str]] = {
    "north_america": [
        "alaska", "northwest_territory", "greenland", "alberta",
        "ontario", "quebec", "western_us", "eastern_us", "central_america",
    ],
    "south_america": [
        "venezuela", "peru", "brazil", "argentina",
    ],
    "europe": [
        "iceland", "scandinavia", "great_britain", "northern_europe",
        "western_europe", "southern_europe", "ukraine",
    ],
    "africa": [
        "north_africa", "egypt", "east_africa", "congo",
        "south_africa", "madagascar",
    ],
    "asia": [
        "ural", "siberia", "yakutsk", "kamchatka", "irkutsk",
        "mongolia", "japan", "afghanistan", "china", "india",
        "siam", "middle_east",
    ],
    "oceania": [
        "indonesia", "new_guinea", "western_australia", "eastern_australia",
    ],
}

# Display names for UI
TERRITORY_NAMES: Dict[str, str] = {
    # North America
    "alaska": "Alaska",
    "northwest_territory": "Northwest Territory",
    "greenland": "Greenland",
    "alberta": "Alberta",
    "ontario": "Ontario",
    "quebec": "Quebec",
    "western_us": "Western US",
    "eastern_us": "Eastern US",
    "central_america": "Central America",
    # South America
    "venezuela": "Venezuela",
    "peru": "Peru",
    "brazil": "Brazil",
    "argentina": "Argentina",
    # Europe
    "iceland": "Iceland",
    "scandinavia": "Scandinavia",
    "great_britain": "Great Britain",
    "northern_europe": "Northern Europe",
    "western_europe": "Western Europe",
    "southern_europe": "Southern Europe",
    "ukraine": "Ukraine",
    # Africa
    "north_africa": "North Africa",
    "egypt": "Egypt",
    "east_africa": "East Africa",
    "congo": "Congo",
    "south_africa": "South Africa",
    "madagascar": "Madagascar",
    # Asia
    "ural": "Ural",
    "siberia": "Siberia",
    "yakutsk": "Yakutsk",
    "kamchatka": "Kamchatka",
    "irkutsk": "Irkutsk",
    "mongolia": "Mongolia",
    "japan": "Japan",
    "afghanistan": "Afghanistan",
    "china": "China",
    "india": "India",
    "siam": "Siam",
    "middle_east": "Middle East",
    # Oceania
    "indonesia": "Indonesia",
    "new_guinea": "New Guinea",
    "western_australia": "Western Australia",
    "eastern_australia": "Eastern Australia",
}

# Adjacency map — each territory lists its neighbors
ADJACENCIES: Dict[str, List[str]] = {
    # North America
    "alaska": ["northwest_territory", "alberta", "kamchatka"],
    "northwest_territory": ["alaska", "alberta", "ontario", "greenland"],
    "greenland": ["northwest_territory", "ontario", "quebec", "iceland"],
    "alberta": ["alaska", "northwest_territory", "ontario", "western_us"],
    "ontario": ["northwest_territory", "greenland", "alberta", "quebec", "western_us", "eastern_us"],
    "quebec": ["ontario", "greenland", "eastern_us"],
    "western_us": ["alberta", "ontario", "eastern_us", "central_america"],
    "eastern_us": ["ontario", "quebec", "western_us", "central_america"],
    "central_america": ["western_us", "eastern_us", "venezuela"],
    # South America
    "venezuela": ["central_america", "peru", "brazil"],
    "peru": ["venezuela", "brazil", "argentina"],
    "brazil": ["venezuela", "peru", "argentina", "north_africa"],
    "argentina": ["peru", "brazil"],
    # Europe
    "iceland": ["greenland", "scandinavia", "great_britain"],
    "scandinavia": ["iceland", "great_britain", "northern_europe", "ukraine"],
    "great_britain": ["iceland", "scandinavia", "northern_europe", "western_europe"],
    "northern_europe": ["scandinavia", "great_britain", "western_europe", "southern_europe", "ukraine"],
    "western_europe": ["great_britain", "northern_europe", "southern_europe", "north_africa"],
    "southern_europe": ["northern_europe", "western_europe", "ukraine", "north_africa", "egypt", "middle_east"],
    "ukraine": ["scandinavia", "northern_europe", "southern_europe", "ural", "afghanistan", "middle_east"],
    # Africa
    "north_africa": ["brazil", "western_europe", "southern_europe", "egypt", "east_africa", "congo"],
    "egypt": ["southern_europe", "north_africa", "east_africa", "middle_east"],
    "east_africa": ["north_africa", "egypt", "congo", "south_africa", "madagascar", "middle_east"],
    "congo": ["north_africa", "east_africa", "south_africa"],
    "south_africa": ["congo", "east_africa", "madagascar"],
    "madagascar": ["east_africa", "south_africa"],
    # Asia
    "ural": ["ukraine", "siberia", "china", "afghanistan"],
    "siberia": ["ural", "yakutsk", "irkutsk", "mongolia", "china"],
    "yakutsk": ["siberia", "irkutsk", "kamchatka"],
    "kamchatka": ["alaska", "yakutsk", "irkutsk", "mongolia", "japan"],
    "irkutsk": ["siberia", "yakutsk", "kamchatka", "mongolia"],
    "mongolia": ["siberia", "irkutsk", "kamchatka", "china", "japan"],
    "japan": ["kamchatka", "mongolia"],
    "afghanistan": ["ukraine", "ural", "china", "india", "middle_east"],
    "china": ["ural", "siberia", "mongolia", "afghanistan", "india", "siam"],
    "india": ["afghanistan", "china", "siam", "middle_east"],
    "siam": ["china", "india", "indonesia"],
    "middle_east": ["southern_europe", "ukraine", "egypt", "east_africa", "afghanistan", "india"],
    # Oceania
    "indonesia": ["siam", "new_guinea", "western_australia"],
    "new_guinea": ["indonesia", "western_australia", "eastern_australia"],
    "western_australia": ["indonesia", "new_guinea", "eastern_australia"],
    "eastern_australia": ["new_guinea", "western_australia"],
}


def get_all_territories() -> List[str]:
    """Return flat list of all 42 territory IDs."""
    return list(TERRITORY_NAMES.keys())


def get_continent_for_territory(territory: str) -> str:
    """Return the continent a territory belongs to."""
    for continent, territories in CONTINENTS.items():
        if territory in territories:
            return continent
    raise ValueError(f"Unknown territory: {territory}")


def are_adjacent(t1: str, t2: str) -> bool:
    """Check if two territories are adjacent."""
    return t2 in ADJACENCIES.get(t1, [])


def get_neighbors(territory: str) -> List[str]:
    """Return list of adjacent territories."""
    return ADJACENCIES.get(territory, [])


def get_player_continent_bonuses(player_territories: Set[str]) -> int:
    """Calculate continent bonus for a player's territory set."""
    bonus = 0
    for continent, territories in CONTINENTS.items():
        if all(t in player_territories for t in territories):
            bonus += CONTINENT_BONUSES[continent]
    return bonus
