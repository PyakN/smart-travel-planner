"""Sunrise and sunset from the date and place alone (the sunrise equation), to a minute or
two: darkness is known on every trip day, with or without a weather forecast."""

from datetime import UTC, date, datetime, timedelta
from math import acos, asin, cos, degrees, radians, sin
from zoneinfo import ZoneInfo

J2000 = 2451545.0  # Julian date of 2000-01-01 12:00
UNIX_EPOCH_JD = 2440587.5
EARTH_TILT = radians(23.4397)
# Sunrise and sunset are when the sun's centre is this far below the horizon: refraction
# and the radius of its disc.
HORIZON = radians(-0.833)
MINUTES_PER_DAY = 24 * 60


def _moment(julian: float) -> datetime:
    return datetime.fromtimestamp((julian - UNIX_EPOCH_JD) * 86400, UTC)


def sun_times(day: date, lat: float, lon: float) -> tuple[datetime, datetime]:
    """Sunrise and sunset (UTC) on `day` at the place. In polar night both are noon; in
    polar day they are twelve hours either side of it."""
    days = (day - date(2000, 1, 1)).days - lon / 360  # to the local solar noon
    anomaly = radians((357.5291 + 0.98560028 * days) % 360)
    centre = 1.9148 * sin(anomaly) + 0.02 * sin(2 * anomaly) + 0.0003 * sin(3 * anomaly)
    ecliptic = radians((degrees(anomaly) + centre + 180 + 102.9372) % 360)
    noon = J2000 + days + 0.0053 * sin(anomaly) - 0.0069 * sin(2 * ecliptic)
    declination = asin(sin(ecliptic) * sin(EARTH_TILT))
    phi = radians(lat)
    cos_hour = (sin(HORIZON) - sin(phi) * sin(declination)) / (cos(phi) * cos(declination))
    half_day = degrees(acos(max(-1.0, min(1.0, cos_hour)))) / 360
    return _moment(noon - half_day), _moment(noon + half_day)


def daylight(day: date, lat: float, lon: float, tz: ZoneInfo) -> tuple[int, int]:
    """Sunrise and sunset on `day` in local minutes since its midnight."""

    def minute(moment: datetime) -> int:
        local = moment.astimezone(tz)
        offset = (local.date() - day) // timedelta(days=1)
        return offset * MINUTES_PER_DAY + local.hour * 60 + local.minute

    sunrise, sunset = sun_times(day, lat, lon)
    return minute(sunrise), minute(sunset)
