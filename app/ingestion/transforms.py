"""Field transform functions for the ingestion adapter framework."""

from datetime import datetime, timezone


def to_utc_timestamp(value) -> datetime:
    """Convert a Unix epoch (int/float) or ISO string to a UTC datetime."""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        # Try ISO format
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
        # Try epoch string
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OSError):
            pass
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    raise ValueError(f"Cannot convert {value!r} to UTC timestamp")


def to_lowercase(value) -> str:
    """Convert a value to lowercase string."""
    return str(value).lower()


def to_string(value) -> str:
    """Convert any value to its string representation."""
    return str(value)


def identity(value):
    """Pass-through transform — returns value unchanged."""
    return value


# Registry of available transforms
TRANSFORM_REGISTRY = {
    "to_utc_timestamp": to_utc_timestamp,
    "to_lowercase": to_lowercase,
    "to_string": to_string,
    "identity": identity,
}


def get_transform(name: str | None):
    """Look up a transform by name. Returns identity if name is None."""
    if name is None:
        return identity
    if name not in TRANSFORM_REGISTRY:
        raise ValueError(f"Unknown transform: {name}")
    return TRANSFORM_REGISTRY[name]
