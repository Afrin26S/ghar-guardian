import json
import os

import state_machine as sm
import notify
from storage import get_store

HOME_ID = "DEMO001"


def _resp(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}


def lambda_handler(event, context=None):
    http = event.get("requestContext", {}).get("http", {})
    method, path = http.get("method", "GET"), event.get("rawPath", "/")
    store = get_store()
    try:
        if method == "GET" and path.endswith("/snapshot"):
            home = (event.get("queryStringParameters") or {}).get("home_id", HOME_ID)
            if home != HOME_ID:
                return _resp(404, {"ok": False, "error": "UNKNOWN_HOME", "message": "Only DEMO001 exists."})
            return _resp(200, {"ok": True, "home_id": home, "storage": store.name,
                               "state": store.get_state(home), "events": store.list_events(home)})
        if method == "POST" and path.endswith("/event"):
            try:
                body = json.loads(event.get("body") or "{}")
            except json.JSONDecodeError:
                return _resp(400, {"ok": False, "error": "BAD_JSON", "message": "Body must be JSON."})
            home = body.get("home_id", HOME_ID)
            if home != HOME_ID:
                return _resp(404, {"ok": False, "error": "UNKNOWN_HOME", "message": "Only DEMO001 exists."})
            params = body.get("params") or {}
            if not isinstance(params, dict):
                return _resp(400, {"ok": False, "error": "BAD_PARAM", "message": "params must be an object."})
            state, new_events, decision = sm.handle(store.get_state(home), body.get("event_type"), params)
            new_events = new_events + notify.maybe_alert(new_events)
            store.save(home, state, new_events)
            print(json.dumps({"home": home, "event_type": body.get("event_type"), "new_events": len(new_events)}))
            return _resp(200, {"ok": True, "storage": store.name, "decision": decision, "state": state,
                               "new_events": new_events, "event_id": new_events[-1]["event_id"] if new_events else None})
        return _resp(404, {"ok": False, "error": "NOT_FOUND", "message": "Unknown route."})
    except sm.Rejected as e:
        return _resp(409 if e.code in ("BAD_STATE", "SCENARIO_RUNNING") else 400,
                     {"ok": False, "error": e.code, "message": e.message})
    except Exception as e:  # surfaced to the UI as a cloud error, never as success
        print("ERROR", repr(e))
        return _resp(500, {"ok": False, "error": "INTERNAL", "message": "Backend error. Check CloudWatch logs."})
