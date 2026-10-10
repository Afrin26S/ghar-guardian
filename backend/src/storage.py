"""Storage: DynamoDB when TABLE_NAME is set, otherwise in-memory (local dev only)."""
import json
import os
from decimal import Decimal

import state_machine as sm


def _clean(o):
    return json.loads(json.dumps(o), parse_float=Decimal)


def _plain(o):
    if isinstance(o, list):
        return [_plain(x) for x in o]
    if isinstance(o, dict):
        return {k: _plain(v) for k, v in o.items()}
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    return o


class MemoryStore:
    name = "memory"

    def __init__(self):
        self.states, self.events = {}, {}

    def get_state(self, home):
        return self.states.get(home) or sm.initial_state()

    def save(self, home, state, events):
        self.states[home] = state
        self.events.setdefault(home, []).extend(events)

    def list_events(self, home, limit=40):
        return list(reversed(self.events.get(home, [])))[:limit]


class DynamoStore:
    name = "dynamodb"

    def __init__(self, table_name):
        import boto3
        self.t = boto3.resource("dynamodb").Table(table_name)

    def get_state(self, home):
        item = self.t.get_item(Key={"pk": f"HOME#{home}", "sk": "STATE"}).get("Item")
        if not item:
            return sm.initial_state()
        return {k: v for k, v in _plain(item).items() if k not in ("pk", "sk")}

    def save(self, home, state, events):
        with self.t.batch_writer() as b:
            b.put_item(Item=_clean({"pk": f"HOME#{home}", "sk": "STATE", **state}))
            for e in events:
                b.put_item(Item=_clean({"pk": f"HOME#{home}", "sk": f"EVENT#{e['created_at']}#{e['event_id']}", **e}))

    def list_events(self, home, limit=40):
        from boto3.dynamodb.conditions import Key
        r = self.t.query(KeyConditionExpression=Key("pk").eq(f"HOME#{home}") & Key("sk").begins_with("EVENT#"),
                         ScanIndexForward=False, Limit=limit)
        return [{k: v for k, v in _plain(i).items() if k not in ("pk", "sk")} for i in r["Items"]]


_store = None


def get_store():
    global _store
    if _store is None:
        t = os.getenv("TABLE_NAME")
        _store = DynamoStore(t) if t else MemoryStore()
    return _store
