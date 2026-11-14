"""Build Swedens polygon frmo Natural Earth

Writes data/ref/sweden_clip.geojson --> Sweden plus a 2km buffer out to sea
And removes Norway, Finland and Denmark so we never cross into neighbouring country

uv run python scripts/make_border.py

"""

import json
import math
from pathlib import Path

import httpx

from shapely import affinity
from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "v5.1.2/geojson/ne_10m_admin_0_countries.geojson"
)

OUT = Path("data/ref/sweden_clip.geojson")
BUFFER_KM = 2.0
REF_LAT = 62.0  # roughly Sweden midpoint


def country(features: list[dict], name: str):
    """Return the shape of one country. Matched on ADMIN - full name of country"""

    for f in features:
        if f["properties"]["ADMIN"] == name:
            return shape(f["geometry"])
    raise KeyError(f"{name} not found in Natural Earth file")


def buffer_km(geom, km: float, ref_lat: float = REF_LAT):
    """Grow a longitude/latitude shape by roughly "km" in every direction

    A degree of longitude is shorter than a degree of latitude this far north
    Therefore we squash longitude to match, buffer and then stretch back

    """

    k = math.cos(math.radians(ref_lat))
    squashed = affinity.scale(geom, xfact=k, yfact=1, origin=(0, 0))
    grown = squashed.buffer(km / 111.32)  # 1 degree of latitude is about 111.32 km
    return affinity.scale(grown, xfact=1 / k, yfact=1, origin=(0, 0))


def main() -> None:

    print("Downloading Natural Earth 1:10 countries ...")
    features = httpx.get(URL, timeout=120, follow_redirects=True).json()["features"]

    sweden = country(features, "Sweden")
    neighbours = unary_union([country(features, n) for n in ("Norway", "Finland", "Denmark")])
    clip = buffer_km(sweden, BUFFER_KM).difference(neighbours)

    # Sanity checks on known places. (Shapely wants (longitude, latitude))
    checks = {
        "Luleå steelworks (keep)": (22.22551, 65.56472, True),
        "Oxelösund, offshore-labelled pixel (keep)": (17.13891, 58.6708, True),
        "Tornio steelworks, Finland (drop)": (24.2, 65.8, False),
        "Mo i Rana, Norway (drop)": (14.17639, 66.30928, False),
    }

    for label, (lon, lat, expected) in checks.items():
        inside = clip.contains(Point(lon, lat))
        status = "ok" if inside == expected else "FAIL"
        print(f"   [{status}] {label}: inside={inside}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    feature = {
        "type": "Feature",
        "properties": {
            "name": "Sweden clipping area",
            "source": "Natural Earth 1:10m admin 0 countries, v5.1.2",
            "buffer_km": BUFFER_KM,
            "minus": ["Norway", "Finland", "Denmark"],
        },
        "geometry": mapping(clip),
    }
    OUT.write_text(json.dumps(feature))
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
