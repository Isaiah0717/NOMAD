import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def read_weather_api(latitude, longitude):
    base_url = "https://api.open-meteo.com/v1/forecast"

    parameters = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,"
            "apparent_temperature,"
            "relative_humidity_2m,"
            "precipitation,"
            "wind_speed_10m,"
            "weather_code"
        ),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "UTC",
    }

    url = f"{base_url}?{urlencode(parameters)}"

    request = Request(
        url,
        headers={
            "User-Agent": "NOMAD/0.2",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            data = json.load(response)

    except HTTPError as error:
        raise ValueError(f"Weather API returned HTTP {error.code}") from error

    except URLError as error:
        raise ValueError(f"Could not connect to weather API: {error.reason}") from error

    except json.JSONDecodeError as error:
        raise ValueError(f"Weather API returned invalid JSON: {error}") from error

    if "current" not in data:
        raise ValueError("Weather API response does not contain current weather data.")

    return data
