"""Sri Lanka-oriented vocabulary and coarse GPS hints (not verified attraction identity)."""
from __future__ import annotations
from math import radians, sin, cos, asin, sqrt

ACTIVITIES = {
    "Wildlife safari": "wildlife safari jeep observing animals in a Sri Lankan national park",
    "Elephant watching": "wild elephants photographed in a Sri Lankan natural habitat",
    "Birdwatching": "birdwatching and a wild tropical bird",
    "Leopard watching": "a Sri Lankan leopard in the wild",
    "Whale watching": "whale watching on a boat in the ocean",
    "Snorkeling": "snorkeling underwater with a mask near coral reef",
    "Surfing": "a surfer riding a wave on a tropical beach",
    "Beach leisure": "people enjoying tropical sandy beach and palm trees",
    "Hiking / trekking": "trekking hiking along a mountain path in Sri Lanka",
    "Rock climbing": "tourist climbing a tall rock outcrop with stairs",
    "Waterfall visit": "visiting a tropical waterfall",
    "Tea plantation visit": "lush terraced tea plantation and people picking tea leaves",
    "Scenic train ride": "scenic blue or red passenger train passing green hills",
    "Boat ride": "tourists taking a small boat across a lake or river",
    "Temple visit": "Buddhist temple visit with Buddhist statues and shrines",
    "Historical ruins": "ancient stone ruins and archaeological site in Sri Lanka",
    "Cooking class": "travelers learning to cook Sri Lankan food in a kitchen",
    "Village experience": "traditional Sri Lankan rural village experience",
    "Cycling": "travelers cycling on bicycles through countryside",
    "Tuk tuk ride": "a tuk tuk three wheeler riding in Sri Lanka",
    "City sightseeing": "tourists sightseeing in a historic town",
    "Market visit": "visiting a busy tropical street food or fruit market",
    "Ayurveda / wellness": "Ayurveda spa treatment or massage",
    "Photography": "tourist taking photographs with a camera",
    "Wildlife / nature": "photograph of wild animals and tropical natural scenery",
}
ATTRACTIONS = {
    "Sigiriya Rock Fortress": "Sigiriya Lion Rock ancient palace massive flat-topped stone monolith Sri Lanka",
    "Pidurangala Rock": "Pidurangala rocky summit overlooking Sigiriya rock Sri Lanka",
    "Dambulla Cave Temple": "Dambulla painted Buddha statues inside a cave temple Sri Lanka",
    "Polonnaruwa": "Polonnaruwa Gal Vihara stone Buddha statues archaeological ruins Sri Lanka",
    "Anuradhapura": "Anuradhapura white Buddhist stupas ancient sacred city Sri Lanka",
    "Ruwanwelisaya": "Ruwanwelisaya massive round white Buddhist stupa Anuradhapura",
    "Mihintale": "Mihintale white stupa on a hill steps Anuradhapura Sri Lanka",
    "Temple of the Tooth": "Sri Dalada Maligawa Temple of the Tooth ornate Buddhist temple Kandy",
    "Kandy Lake": "Kandy Lake with the white island pavilion and green hills Sri Lanka",
    "Royal Botanical Gardens Peradeniya": "Peradeniya botanical gardens giant palm avenue Sri Lanka",
    "Nine Arch Bridge": "Nine Arch Bridge Ella stone railway viaduct nine arches lush tea plantation Sri Lanka",
    "Little Adam's Peak": "Little Adam's Peak Ella mountain ridge viewpoints Sri Lanka",
    "Ella Rock": "Ella Rock viewpoint mountain valley hiking Sri Lanka",
    "Ravana Falls": "Ravana Ella Falls broad cascading waterfall Sri Lanka",
    "Ramboda Falls": "Ramboda waterfall in Sri Lankan hill country",
    "Nuwara Eliya": "Nuwara Eliya hill station colonial buildings tea fields Sri Lanka",
    "Horton Plains / World's End": "Horton Plains World's End sheer cliff grasslands Sri Lanka",
    "Adam's Peak": "Adam's Peak Sri Pada pyramid mountain sunrise pilgrimage summit Sri Lanka",
    "Galle Fort": "Galle Dutch Fort lighthouse old stone ramparts Indian Ocean Sri Lanka",
    "Koggala Lake": "Koggala Lake lagoon fishing boats and small islands Sri Lanka",
    "Yala National Park": "Yala National Park leopard wildlife jeep safari dry tropical forest Sri Lanka",
    "Udawalawe National Park": "Udawalawe National Park wild elephant safari open grasslands Sri Lanka",
    "Wilpattu National Park": "Wilpattu National Park leopard safari lakes forest Sri Lanka",
    "Minneriya National Park": "Minneriya National Park large gathering of wild elephants Sri Lanka",
    "Kaudulla National Park": "Kaudulla National Park elephant gathering safari Sri Lanka",
    "Trincomalee / Nilaveli": "Nilaveli Trincomalee beach clear turquoise blue water Sri Lanka",
    "Negombo Lagoon": "Negombo lagoon fishing boats and coconut palms Sri Lanka",
    "Colombo Lotus Tower": "Colombo Lotus Tower tall pink and green tower Sri Lanka",
    "Ambuluwawa Tower": "Ambuluwawa narrow white spiral tower mountain Gampola Sri Lanka",
    "Buduruwagala": "Buduruwagala ancient standing Buddha relief carved into huge rock Sri Lanka",
    "Ritigala": "Ritigala ancient monastery ruins covered in rainforest Sri Lanka",
    "Nalanda Gedige": "Nalanda Gedige small ancient stone temple in Sri Lanka",
}
# A location point is approximate: GPS proximity can suggest an area, not certify a landmark.
GPS_PLACES = [
    ("Negombo", 7.2094, 79.8358, 24), ("Colombo", 6.9271, 79.8612, 27),
    ("Galle", 6.0329, 80.2168, 22), ("Ahangama", 5.9734, 80.3703, 14),
    ("Mirissa", 5.9483, 80.4716, 15), ("Tangalle", 6.0259, 80.7966, 16),
    ("Sigiriya", 7.9570, 80.7603, 20), ("Dambulla", 7.8687, 80.6517, 16),
    ("Polonnaruwa", 7.9403, 81.0188, 20), ("Anuradhapura", 8.3114, 80.4037, 24),
    ("Kandy", 7.2906, 80.6337, 26), ("Nuwara Eliya", 6.9497, 80.7891, 22),
    ("Ella", 6.8667, 81.0466, 20), ("Haputale", 6.7667, 80.9500, 15),
    ("Tissamaharama", 6.2827, 81.2870, 19), ("Yala National Park", 6.4000, 81.4800, 35),
    ("Udawalawe", 6.4717, 80.8886, 24), ("Wilpattu", 8.4510, 80.0120, 38),
    ("Trincomalee", 8.5874, 81.2152, 27), ("Nilaveli", 8.6835, 81.2008, 14),
    ("Arugam Bay", 6.8404, 81.8362, 22), ("Jaffna", 9.6615, 80.0255, 25),
    ("Minneriya", 8.0369, 80.8972, 19),
]

def gps_hint(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None: return ""
    def dist(a, b, c, d):
        x = sin(radians(c-a)/2)**2 + cos(radians(a))*cos(radians(c))*sin(radians(d-b)/2)**2
        return 6371 * 2 * asin(min(1, sqrt(x)))
    near = sorted((dist(lat, lon, y, x), name, maxkm) for name, y, x, maxkm in GPS_PLACES)
    km, name, maxkm = near[0]
    return name if km <= maxkm else ""
