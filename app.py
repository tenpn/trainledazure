"""Train and weather info for the unicorn display, served by Vercel as one Flask app.

Routes match the old Azure Functions URLs, so clients only need a new hostname:
  /api/localinfo?trainFrom=KNN&trainTo=BHX&weather=B30&code=<API_KEY>
  /api/trainline?left_crs=BHM&right_crs=KNN&code=<API_KEY>

Parameters can be sent as query params or a JSON body (GET or POST).
"""

import hmac
import os

from flask import Flask, abort, jsonify, request

from localinfo import get_localinfo
from trainline import get_trainline

app = Flask(__name__)


@app.before_request
def check_key():
    # same scheme as Azure function keys: ?code=... or x-functions-key header.
    # fails closed if API_KEY isn't configured.
    expected = os.environ.get("API_KEY", "")
    given = request.args.get("code") or request.headers.get("x-functions-key") or ""
    if not expected or not hmac.compare_digest(given, expected):
        abort(401)


def get_params(*names: str) -> dict:
    body = request.get_json(silent=True) or {}
    params = {name: request.args.get(name) or body.get(name) for name in names}
    if any(value is None for value in params.values()):
        abort(400, "expected valid parameters: " + ", ".join(names))
    return params


@app.route("/api/localinfo", methods=["GET", "POST"])
def localinfo():
    p = get_params("trainFrom", "trainTo", "weather")
    return jsonify(get_localinfo(p["trainFrom"], p["trainTo"], p["weather"]))


@app.route("/api/trainline", methods=["GET", "POST"])
def trainline():
    p = get_params("left_crs", "right_crs")
    return jsonify(get_trainline(p["left_crs"], p["right_crs"]))
