import logging
import azure.functions as func
import zeep
import json
import os
import requests
from typing import Dict, Union, List, Optional


def decimal_time_from_24h_str(time_str: str) -> float:
    """turns a HH:MM time string into a decimal, where the units are the hours since midnight and the decimal is the fraction through the hour

    Args:
        time_str (str): "hh:mm"

    Returns:
        float: hours.fraction_through_hour
    """
    # not sure if this is 24h clock or not yet?
    return int(time_str[0:2]) + (int(time_str[3:]) / 60.0)


def decimal_time_from_12h_str(time_str: str) -> float:
    """easier to do maths with decimal time!

    Args:
        time_str (str): "HH:MM AM"/"HH:MM PM"

    Returns:
        float: 24hour.fraction-through-hour
    """
    h12 = int(time_str[0:2])
    m = float(time_str[3:5])
    h24 = h12 if time_str[6] == "A" else (h12 + 12)
    return h24 + (m / 60.0)


def put_weather_into(postcode: str, response: Dict) -> Dict:
    # current temp, feels like
    # day min, day max
    # wind
    # humidity
    # day chance of rain
    # condition
    # sunrise
    # sunset
    # per hour:
    # - chance of rain
    # - feelslike c

    forecast_url = f'https://api.weatherapi.com/v1/forecast.json?q={postcode}&key={os.environ["weatherAuth"]}'

    weather_req = requests.get(forecast_url)
    logging.info(f"{forecast_url} gave {weather_req}")
    if weather_req.status_code != 200:
        return

    weather_raw_json = weather_req.json()
    weather_day_json = weather_raw_json["forecast"]["forecastday"][0]

    response["temp_now"] = weather_raw_json["current"]["temp_c"]
    response["temp_feelslike_now"] = weather_raw_json["current"]["feelslike_c"]
    response["temp_max"] = weather_day_json["day"]["maxtemp_c"]
    response["temp_min"] = weather_day_json["day"]["mintemp_c"]
    response["wind_now"] = weather_raw_json["current"]["wind_mph"]
    response["humidity_now"] = weather_raw_json["current"]["humidity"]
    response["rain_%_today"] = weather_day_json["day"]["daily_chance_of_rain"]
    response["condition"] = weather_raw_json["current"]["condition"]["text"]
    response["sunrise"] = decimal_time_from_12h_str(
        weather_day_json["astro"]["sunrise"]
    )
    response["sunset"] = decimal_time_from_12h_str(weather_day_json["astro"]["sunset"])

    response["rain_%_hours"] = [
        forecast_hour["chance_of_rain"] for forecast_hour in weather_day_json["hour"]
    ]
    response["temp_feelslike_hours"] = [
        forecast_hour["feelslike_c"] for forecast_hour in weather_day_json["hour"]
    ]

    return response


def put_trains_into(from_station: str, to_station: str, response: Dict) -> Dict:
    loose_settings = zeep.Settings(strict=False)
    ldbws = zeep.Client(
        "https://lite.realtime.nationalrail.co.uk/OpenLDBWS/wsdl.aspx?ver=2021-11-01",
        settings=loose_settings,
    )
    ldbws.set_default_soapheaders({"AccessToken": os.environ["ldbwsAuth"]})
    departures = ldbws.service.GetDepartureBoard(
        crs=from_station,
        numRows=10,
        filterType="to",
        filterCrs=to_station,
    )

    # in case we quit early, make sure there's something
    response["departures_times"] = []

    services = departures.trainServices
    if services is None:
        return response

    service_list = services.service
    if service_list is None:
        return response

    departure_times = [
        decimal_time_from_24h_str(service["std"]) for service in service_list
    ]
    response["departures_times"] = departure_times
    return response


def main(req: func.HttpRequest) -> func.HttpResponse:
    train_to = req.params.get("trainTo")
    train_from = req.params.get("trainFrom")
    weather_postcode = req.params.get("weather")

    if train_to is None:
        # assume they both are
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            train_to = req_body.get("trainTo")
            train_from = req_body.get("trainFrom")
            weather_postcode = req_body.get("weather")

    if weather_postcode is None or train_to is None:
        return func.HttpResponse("expected valid parameters", status_code=400)

    response = put_weather_into(weather_postcode, {})
    response = put_trains_into(train_from, train_to, response)

    logging.info(str(response))
    return func.HttpResponse(json.dumps(response))
