"""City centres and venue layout for the mock month (A-T10). Values from plan A section 3, A-T10."""

# city: (lat, lon, meter count, venue code prefix, bars_in_stratum by size S/M/L)
CITIES = {
    "Douala":   (4.0511, 9.7679, 8, "DLA", {"S": 4250, "M": 2975, "L": 1275}),
    "Yaounde":  (3.8480, 11.5021, 8, "YDE", {"S": 3250, "M": 2275, "L": 975}),
    "Buea":     (4.1527, 9.2410, 3, "BUEA", {"S": 150, "M": 100, "L": 50}),
    "Limbe":    (4.0186, 9.2043, 2, "LIM", {"S": 120, "M": 85, "L": 35}),
    "Bamenda":  (5.9631, 10.1591, 3, "BAM", {"S": 160, "M": 110, "L": 50}),
    "Bafoussam": (5.4778, 10.4176, 2, "BAF", {"S": 100, "M": 70, "L": 30}),
    "Garoua":   (9.3014, 13.3977, 2, "GAR", {"S": 110, "M": 80, "L": 30}),
    "Maroua":   (10.5910, 14.3159, 1, "MAR", {"S": 60, "M": 40, "L": 15}),
    "Kribi":    (2.9395, 9.9095, 1, "KRI", {"S": 50, "M": 35, "L": 15}),
}

# Venue names used by the scenarios and by the device configs (A-T03)
NAMED = {
    ("Douala", 0): "V-DLA-AKWA01",
    ("Yaounde", 0): "V-YDE-BASTO1",
    ("Buea", 0): "V-BUEA-MOLYK1",
}

LIVE_VENUE = "V-BUEA-CIMFEST"
