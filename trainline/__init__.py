import logging
import zeep
import azure.functions as func
import os


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
    
    logging.info(f'looking for trains between {left_crs} and {right_crs}')
        
    ldbws = zeep.Client("https://lite.realtime.nationalrail.co.uk/OpenLDBWS/wsdl.aspx?ver=2021-11-01")
    headers = {
        "AccessToken": os.environ["ldbwsAuth"],
    }
    with ldbws.settings(strict=False):
        bhm_to_knn = ldbws.service.GetArrivalBoard(crs=right_crs, filterType="from", filterCrs=left_crs, numRows=2, _soapheaders=headers)
        
        for service in bhm_to_knn.trainServices.service:
            logging.info(service.sta)
        return func.HttpResponse("placeholder")

