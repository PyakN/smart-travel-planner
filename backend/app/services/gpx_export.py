"""A plan as a GPX 1.1 file, for GPS and map apps (Organic Maps, OsmAnd, Komoot, Garmin):
every stop is a waypoint with its visit, every day a track along its streets and lines.

Waypoints are numbered by day and stop ("2.3 Torre de Belém": day 2, stop 3), or by stop
alone when the file holds one day. Their time is the arrival, in UTC as GPX has it; plans
without dates have none.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from app.ingest.cities import CITIES
from app.optimizer.planner import MINUTES_PER_DAY
from app.schemas.plan import PlannedDay, PlanResponse
from app.services.saved_trips import default_title

GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
GPX_MEDIA_TYPE = "application/gpx+xml"
CREATOR = "Smart Travel Planner"


def _minutes(clock: str) -> int:
    hours, minutes = clock.split(":")
    return int(hours) * 60 + int(minutes)


def _arrivals(day: PlannedDay, tz: ZoneInfo) -> list[datetime] | None:
    """When each stop of the day is reached, in UTC; None for plans without dates. A day's
    clock only moves forward: a time earlier than the one before it is past midnight."""
    if day.date is None:
        return None
    midnight = datetime.combine(day.date, time(), tz)
    last = _minutes(day.start) if day.start else 0
    arrivals = []
    for stop in day.stops:
        arrive, leave = (_minutes(clock) for clock in (stop.arrive, stop.leave))
        arrive += last - last % MINUTES_PER_DAY
        if arrive < last:
            arrive += MINUTES_PER_DAY
        # Wall-clock arithmetic in the city's zone, then UTC: right across DST changes.
        arrivals.append((midnight + timedelta(minutes=arrive)).astimezone(UTC))
        last = arrive + (leave - arrive) % MINUTES_PER_DAY
    return arrivals


def _text(parent: ET.Element, tag: str, text: str) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.text = text
    return element


def _point(parent: ET.Element, tag: str, lat: float, lon: float) -> ET.Element:
    return ET.SubElement(parent, tag, lat=f"{lat:.6f}", lon=f"{lon:.6f}")


def _gpx_time(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _track_desc(day: PlannedDay) -> str:
    parts = [f"{day.walking_m / 1000:.1f} km on foot"]
    if day.transit_legs:
        parts.append(f"{day.transit_legs} transit {'ride' if day.transit_legs == 1 else 'rides'}")
    if day.stops:
        parts.append(f"{day.stops[0].arrive}–{day.stops[-1].leave}")
    when = f"{day.date:%a} {day.date.day} {day.date:%b %Y}: " if day.date else ""
    return when + ", ".join(parts)


def plan_gpx(plan: PlanResponse, day: int | None = None) -> bytes:
    """The plan, or only its day `day`, as a GPX document (UTF-8)."""
    days: Sequence[PlannedDay] = [d for d in plan.days if day is None or d.day == day]
    if not days:
        raise ValueError(f"day {day} is not in plan {plan.id}")
    city = CITIES.get(plan.city)
    tz = city.tz if city else ZoneInfo("UTC")
    title = default_title(plan)
    numbered = len(days) > 1

    # Children follow the order the GPX 1.1 schema sets for each element.
    gpx = ET.Element("gpx", version="1.1", creator=CREATOR, xmlns=GPX_NAMESPACE)
    metadata = ET.SubElement(gpx, "metadata")
    _text(metadata, "name", title if day is None else f"{title}: day {day}")
    _text(metadata, "desc", plan.request_text)

    if plan.start is not None:
        start = _point(gpx, "wpt", plan.start.lat, plan.start.lon)
        _text(start, "name", "Start and end" if plan.start.round_trip else "Start")
        _text(start, "type", "start")
    for planned in days:
        arrivals = _arrivals(planned, tz)
        for n, stop in enumerate(planned.stops, start=1):
            wpt = _point(gpx, "wpt", stop.lat, stop.lon)
            if arrivals is not None:
                _text(wpt, "time", _gpx_time(arrivals[n - 1]))
            number = f"{planned.day}.{n}" if numbered else f"{n}."
            _text(wpt, "name", f"{number} {stop.name}")
            lines = [f"Day {planned.day}, stop {n}: {stop.arrive}–{stop.leave}."]
            lines += [text for text in (stop.note, stop.description) if text]
            _text(wpt, "desc", "\n\n".join(lines))
            if stop.website:
                link = ET.SubElement(wpt, "link", href=stop.website)
                _text(link, "text", "Website")
            _text(wpt, "type", stop.category)

    for planned in days:
        trk = ET.SubElement(gpx, "trk")
        _text(trk, "name", f"Day {planned.day}")
        _text(trk, "desc", _track_desc(planned))
        _text(trk, "number", str(planned.day))
        for segment in planned.segments:
            if len(segment.geometry) < 2:
                continue  # a lone point: a day of one stop without a start
            trkseg = ET.SubElement(trk, "trkseg")
            for lon, lat in segment.geometry:
                _point(trkseg, "trkpt", lat, lon)

    ET.indent(gpx)
    document: bytes = ET.tostring(gpx, encoding="utf-8", xml_declaration=True)
    return document


def gpx_filename(plan: PlanResponse, day: int | None = None) -> str:
    """ "lisbon-plan-12.gpx", or "lisbon-plan-12-day-2.gpx" for one day."""
    suffix = f"-day-{day}" if day is not None else ""
    return f"{plan.city}-plan-{plan.id}{suffix}.gpx"
