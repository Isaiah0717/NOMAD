def adapt_weather_response(weather_data, location_name):
    current = weather_data["current"]

    weather_observation = {
        "location_name": location_name,
        "latitude": weather_data["latitude"],
        "longitude": weather_data["longitude"],
        "observed_at": current["time"],
        "temperature_f": current["temperature_2m"],
        "apparent_temperature_f": current["apparent_temperature"],
        "relative_humidity": current["relative_humidity_2m"],
        "precipitation_inches": current["precipitation"],
        "wind_speed_mph": current["wind_speed_10m"],
        "weather_code": current["weather_code"],
    }

    return weather_observation
