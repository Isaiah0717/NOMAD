import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def read_api(url):
    request = Request(
        url,
        headers={
            "User-Agent": "NOMAD/0.1",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            data = json.load(response)

    except HTTPError as error:
        raise ValueError(f"API returned HTTP {error.code}") from error

    except URLError as error:
        raise ValueError(f"Could not connect to API: {error.reason}") from error

    except json.JSONDecodeError as error:
        raise ValueError(f"API returned invalid JSON: {error}") from error

    if not isinstance(data, list):
        raise ValueError("API response must contain a list of records.")

    return data
