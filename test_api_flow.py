import json
import os
import time
import urllib.request
from pathlib import Path


BOT_URL = os.environ.get("BOT_URL", "http://127.0.0.1:8080").rstrip("/")
ROOT = Path(__file__).parent
DATASET = ROOT / "dataset"


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BOT_URL + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def push(scope: str, context_id: str, payload: dict, version: int) -> dict:
    return call(
        "POST",
        "/v1/context",
        {
            "scope": scope,
            "context_id": context_id,
            "version": version,
            "payload": payload,
            "delivered_at": "2026-05-01T00:00:00Z",
        },
    )


def load_seed() -> tuple[dict, dict, dict]:
    category = json.loads((DATASET / "categories" / "dentists.json").read_text(encoding="utf-8"))
    merchants = json.loads((DATASET / "merchants_seed.json").read_text(encoding="utf-8"))["merchants"]
    triggers = json.loads((DATASET / "triggers_seed.json").read_text(encoding="utf-8"))["triggers"]
    merchant = next(item for item in merchants if item["merchant_id"] == "m_001_drmeera_dentist_delhi")
    trigger = next(item for item in triggers if item["id"] == "trg_001_research_digest_dentists")
    return category, merchant, trigger


def main() -> None:
    print(f"Testing bot at {BOT_URL}")

    print("\n1. Health")
    print(json.dumps(call("GET", "/v1/healthz"), indent=2))

    print("\n2. Metadata")
    print(json.dumps(call("GET", "/v1/metadata"), indent=2))

    print("\n3. Reset state")
    print(json.dumps(call("POST", "/v1/teardown", {}), indent=2))

    category, merchant, trigger = load_seed()
    version = int(time.time())

    print("\n4. Push contexts")
    print(json.dumps(push("category", category["slug"], category, version), indent=2))
    print(json.dumps(push("merchant", merchant["merchant_id"], merchant, version), indent=2))
    print(json.dumps(push("trigger", trigger["id"], trigger, version), indent=2))

    print("\n5. Tick: judge asks bot if it wants to send")
    tick = call(
        "POST",
        "/v1/tick",
        {
            "now": "2026-05-01T00:05:00Z",
            "available_triggers": [trigger["id"]],
        },
    )
    print(json.dumps(tick, indent=2, ensure_ascii=False))

    actions = tick.get("actions", [])
    if not actions:
        raise SystemExit("No action returned from /v1/tick")

    action = actions[0]
    print("\nGenerated WhatsApp message:")
    print(action["body"])

    print("\n6. Reply: simulate merchant saying yes")
    reply = call(
        "POST",
        "/v1/reply",
        {
            "conversation_id": action["conversation_id"],
            "merchant_id": action["merchant_id"],
            "customer_id": action.get("customer_id"),
            "from_role": "merchant",
            "message": "Yes please send the summary and patient WhatsApp.",
            "received_at": "2026-05-01T00:06:00Z",
            "turn_number": 2,
        },
    )
    print(json.dumps(reply, indent=2, ensure_ascii=False))

    print("\nPASS: health -> context -> tick -> reply all worked.")


if __name__ == "__main__":
    main()
