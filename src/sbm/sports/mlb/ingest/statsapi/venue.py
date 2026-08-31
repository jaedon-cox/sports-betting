"""Venue structural facts: coordinates, orientation, roof, turf.

All four come from one MLB StatsAPI call (`/venues/{id}?hydrate=location,
fieldInfo`) — confirmed live at build time to include `location.azimuthAngle`
(home-plate bearing, needed for the wind x park-orientation interaction that
model doc §3.7 flags as the primary weather alpha source) and
`fieldInfo.{roofType,turfType}` directly. Coordinates feed `weather.py`'s
forecast calls. None of this is hardcoded — unlike a numeric park run
*factor* (magnitude of scoring environment), which neither MLB StatsAPI nor
pybaseball expose on the free tier (message sent to `main`).
"""

from __future__ import annotations

from dataclasses import dataclass

from sbm.sports.mlb.ingest.statsapi.client import StatsApiClient


@dataclass(frozen=True, slots=True)
class VenueInfo:
    """Structural facts for `features/park.py` and `weather.py`."""

    venue_id: int
    name: str | None
    latitude: float | None
    longitude: float | None
    orientation_deg: float | None
    """Home-plate azimuth (StatsAPI's `azimuthAngle`): 0=N, 90=E, clockwise."""
    roof_type: str | None
    turf_type: str | None


def fetch_venue(venue_id: int, *, client: StatsApiClient) -> VenueInfo:
    payload = client.get(f"/venues/{venue_id}", params={"hydrate": "location,fieldInfo"})
    venues = payload.get("venues", [])
    if not venues:
        return VenueInfo(venue_id, None, None, None, None, None, None)
    raw = venues[0]
    location = raw.get("location", {})
    coords = location.get("defaultCoordinates", {})
    field = raw.get("fieldInfo", {})
    return VenueInfo(
        venue_id=venue_id,
        name=raw.get("name"),
        latitude=coords.get("latitude"),
        longitude=coords.get("longitude"),
        orientation_deg=location.get("azimuthAngle"),
        roof_type=field.get("roofType"),
        turf_type=field.get("turfType"),
    )
