import logging
import zeep
import azure.functions as func
import os
import json
from typing import Dict, Union, List

def hours_decimal_from_time_str(time_str: str) -> float:
    """turns a HH:MM time string into a decimal, where the units are the hours since midnight and the decimal is the fraction through the hour

    Args:
        time_str (str): "hh:mm"

    Returns:
        float: hours.fraction_through_hour
    """
    # not sure if this is 24h clock or not yet?
    return int(time_str[0:2]) + (int(time_str[3:])/60.0)

def get_locations_from_train_details(train_details, start_crs: str) -> Dict[str, Union[str, float]]:
    """generates info about when this train will be visiting each station 

    Args:
        train_details: ldbws ServiceDetails
        start_crs (str): what station are we starting at?

    Returns:
        Dict[str, Union[str, float]]: { crs: "crs code", time: decimal-hours-when-train-is-due }
    """
    # find stations between left and right inc:
    # (why is the list buried like this)
    prev_locations = train_details.previousCallingPoints.callingPointList[0].callingPoint
    interesting_locations = []
    for prev_location in prev_locations:
        if len(interesting_locations) > 0 or prev_location.crs.lower() == start_crs.lower():
            interesting_locations.append({
                'crs': prev_location.crs,
                'time': hours_decimal_from_time_str(prev_location.st),
            })
    interesting_locations.append({
        'crs': train_details.crs,
        'time': hours_decimal_from_time_str(train_details.sta),
    })
    return interesting_locations

def get_details_from_service(train_service, ldbws):
    """makes sure the service is valid

    Args:
        train_service (ServiceItem): 
        ldbws: it's ldbws!!!

    Returns:
        ServiceDetails: makes sure sta is vaid and populated
    """
    details = ldbws.service.GetServiceDetails(train_service.serviceID)
    if details.sta is None:
        details.sta = train_service.sta
    return details

def filter_for_soon_train_locs(cutoff_departure: float, train_locs: List) -> List:
    return [train_loc for train_loc in train_locs
            if train_loc[0]["time"] <= cutoff_departure]

def main(req: func.HttpRequest) -> func.HttpResponse:
    left_crs = req.params.get('left_crs')
    right_crs = req.params.get('right_crs')
    
    if left_crs is None:
        # assume they both are
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            left_crs = req_body.get("left_crs")
            right_crs = req_body.get("right_crs")
            
    if left_crs is None or right_crs is None:
        return func.HttpResponse("expected valid parameters", status_code=400)
    
    left_crs = left_crs.upper()
    right_crs = right_crs.upper()
    
    logging.info(f'looking for trains between {left_crs} and {right_crs}')
    
    loose_settings = zeep.Settings(strict=False)
    ldbws = zeep.Client("https://lite.realtime.nationalrail.co.uk/OpenLDBWS/wsdl.aspx?ver=2021-11-01", settings=loose_settings)
    ldbws.set_default_soapheaders({"AccessToken": os.environ["ldbwsAuth"]})

    left_to_right = ldbws.service.GetArrivalBoard(crs=right_crs, 
                                                  filterType="from", 
                                                  filterCrs=left_crs, 
                                                  numRows=10)
    decimal_now = hours_decimal_from_time_str(f"{left_to_right.generatedAt.hour:02d}:{left_to_right.generatedAt.minute:02d}")
    cutoff_departure = decimal_now + 1
    
    lr_train_details = [get_details_from_service(service, ldbws)
                        for service in left_to_right.trainServices.service] \
                if left_to_right.areServicesAvailable is not None and left_to_right.areServicesAvailable \
                else []
    
    lr_train_locs = filter_for_soon_train_locs(
        cutoff_departure, 
        [get_locations_from_train_details(train_details, left_crs)
         for train_details in lr_train_details])
    
    right_to_left = ldbws.service.GetArrivalBoard(crs=left_crs, 
                                                  filterType="from", 
                                                  filterCrs=right_crs, 
                                                  numRows=10)
    rl_train_details = [get_details_from_service(service, ldbws)
                        for service in right_to_left.trainServices.service] \
                if right_to_left.areServicesAvailable is not None and right_to_left.areServicesAvailable \
                else []
    rl_train_locs = filter_for_soon_train_locs(
        cutoff_departure, 
        [get_locations_from_train_details(train_details, right_crs) 
         for train_details in rl_train_details])
    
    timetables = {
        "lr": lr_train_locs,
        "rl": rl_train_locs,
        "now": decimal_now
    }    
    logging.info(str(timetables))
    return func.HttpResponse(json.dumps(timetables))

