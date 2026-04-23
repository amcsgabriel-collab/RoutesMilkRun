import datetime as dt
import uuid


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id() -> str:
    return str(uuid.uuid4())


def decimal_to_dms(value: float):
    sign = -1 if value < 0 else 1
    value = abs(value)

    degrees = int(value)
    minutes_full = (value - degrees) * 60
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60

    return sign * degrees, minutes, seconds


def decimal_to_dms_str(coordinates: tuple[float, float]):
    directions = {
        "lat": ("N", "S"),
        "lon": ("E", "W"),
    }

    formatted = []
    for value, axis in zip(coordinates, ("lat", "lon")):
        direction = directions[axis][0 if value >= 0 else 1]
        degrees, minutes, seconds = decimal_to_dms(value)
        formatted.append(f"{abs(degrees)}°{minutes}'{seconds:.2f}\" {direction}")

    return f"({formatted[0]}, {formatted[1]})"
