import json
from pathlib import Path
from typing import Any

import bot


class MessageEngine:
    """Small end-to-end engine for one Vera conversation flow.

    Flow:
    1. Push category/merchant/customer/trigger contexts.
    2. Compose the outbound WhatsApp for one trigger.
    3. Receive the merchant/customer reply.
    4. Return the next send/wait/end action.
    """

    def __init__(self) -> None:
        self.contexts: dict[tuple[str, str], dict[str, Any]] = {}
        self.conversations: dict[str, dict[str, Any]] = {}
        self.suppressed: set[str] = set()
        self.merchant_suppressed: set[str] = set()

    def push_context(self, scope: str, context_id: str, version: int, payload: dict[str, Any]) -> dict[str, Any]:
        if scope not in bot.SCOPES:
            return {"accepted": False, "reason": "invalid_scope"}

        key = (scope, context_id)
        current = self.contexts.get(key)
        if current and current["version"] >= version:
            return {"accepted": False, "reason": "stale_version", "current_version": current["version"]}

        self.contexts[key] = {"version": version, "payload": payload, "stored_at": bot.utc_now()}
        return {"accepted": True, "ack_id": f"ack_{context_id}_v{version}", "stored_at": self.contexts[key]["stored_at"]}

    def get_context(self, scope: str, context_id: str | None) -> dict[str, Any] | None:
        if not context_id:
            return None
        stored = self.contexts.get((scope, context_id))
        return stored["payload"] if stored else None

    def compose_for_trigger(self, trigger_id: str) -> dict[str, Any] | None:
        trigger = self.get_context("trigger", trigger_id)
        if not trigger:
            return None

        merchant_id = trigger.get("merchant_id")
        if merchant_id in self.merchant_suppressed:
            return None

        suppression_key = trigger.get("suppression_key", trigger_id)
        if suppression_key in self.suppressed:
            return None

        merchant = self.get_context("merchant", merchant_id)
        if not merchant:
            return None

        category_id = merchant.get("category_slug") or trigger.get("payload", {}).get("category")
        category = self.get_context("category", category_id)
        if not category:
            return None

        customer = self.get_context("customer", trigger.get("customer_id")) if trigger.get("customer_id") else None
        if trigger.get("scope") == "customer" and not customer:
            return None

        composed = bot.compose(category, merchant, trigger, customer)
        conversation_id = bot.make_conversation_id(merchant_id, trigger_id, trigger.get("customer_id"))
        action = {
            "conversation_id": conversation_id,
            "merchant_id": merchant_id,
            "customer_id": trigger.get("customer_id"),
            "send_as": composed["send_as"],
            "trigger_id": trigger_id,
            "template_name": bot.template_name_for(trigger, customer),
            "template_params": [bot.merchant_name(merchant), trigger.get("kind", "update"), composed["body"][:250]],
            **composed,
        }

        self.conversations[conversation_id] = {
            "merchant_id": merchant_id,
            "customer_id": trigger.get("customer_id"),
            "trigger_id": trigger_id,
            "sent_bodies": [composed["body"]],
            "messages": [{"from": "bot", "body": composed["body"], "ts": bot.utc_now()}],
            "auto_count": 0,
            "ended": False,
        }
        self.suppressed.add(suppression_key)
        return action

    def receive_reply(
        self,
        conversation_id: str,
        message: str,
        from_role: str = "merchant",
        merchant_id: str | None = None,
        customer_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.conversations.setdefault(
            conversation_id,
            {
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "trigger_id": None,
                "sent_bodies": [],
                "messages": [],
                "auto_count": 0,
                "ended": False,
            },
        )
        state["messages"].append({"from": from_role, "body": message, "ts": bot.utc_now()})
        merchant_id = merchant_id or state.get("merchant_id")

        if bot.has_stop(message):
            if merchant_id:
                self.merchant_suppressed.add(merchant_id)
            state["ended"] = True
            return {"action": "end", "rationale": "Merchant opted out or showed hostility; stop the flow."}

        if bot.is_auto_reply(message):
            state["auto_count"] = int(state.get("auto_count", 0)) + 1
            if state["auto_count"] == 1:
                return {
                    "action": "wait",
                    "wait_seconds": 14400,
                    "rationale": "Detected WhatsApp Business auto-reply; wait for a real owner response.",
                }
            if state["auto_count"] == 2:
                return {"action": "wait", "wait_seconds": 86400, "rationale": "Auto-reply repeated; wait 24h."}
            state["ended"] = True
            return {"action": "end", "rationale": "Auto-reply repeated three times; close the flow."}

        state["auto_count"] = 0
        merchant = self.get_context("merchant", merchant_id)
        trigger = self.get_context("trigger", state.get("trigger_id")) if state.get("trigger_id") else None
        category = self.get_context("category", merchant.get("category_slug")) if merchant else None
        salutation = bot.merchant_salutation(category or {}, merchant or {"identity": {}}) if merchant else "Great"

        if bot.is_out_of_scope(message):
            return bot.action_reply(
                "That sits outside Vera's lane, so your specialist should handle it.\nComing back to growth: want me to draft the message first?",
                "binary_yes_no",
                "Redirected from out-of-scope ask to the current growth flow.",
            )

        if bot.has_yes(message):
            kind = trigger.get("kind") if trigger else ""
            if kind in {"research_digest", "cde_opportunity", "regulation_change"}:
                body = (
                    f"{salutation}, perfect - moving to action.\n"
                    "I'll make the 2-min summary and a customer-safe WhatsApp draft.\n"
                    "Reply CONFIRM and I'll package it as the final draft."
                )
            else:
                body = (
                    f"{salutation}, perfect - moving to action.\n"
                    "I'll turn this into one usable draft with one CTA.\n"
                    "Reply CONFIRM and I'll finalize it."
                )
            return bot.action_reply(body, "binary_confirm_cancel", "Detected intent; advanced to action mode.")

        return bot.action_reply(
            "Got it.\nI can keep this to one specific draft, one CTA, and you approve before anything goes out.\nWant me to prepare that first draft?",
            "binary_yes_no",
            "Acknowledged reply and offered a low-friction next step.",
        )


def build_demo_engine() -> MessageEngine:
    dataset_dir = Path(__file__).parent / "dataset"
    engine = MessageEngine()

    category = json.loads((dataset_dir / "categories" / "dentists.json").read_text(encoding="utf-8"))
    merchants = json.loads((dataset_dir / "merchants_seed.json").read_text(encoding="utf-8"))["merchants"]
    triggers = json.loads((dataset_dir / "triggers_seed.json").read_text(encoding="utf-8"))["triggers"]

    merchant = next(item for item in merchants if item["merchant_id"] == "m_001_drmeera_dentist_delhi")
    trigger = next(item for item in triggers if item["id"] == "trg_001_research_digest_dentists")

    engine.push_context("category", category["slug"], 1, category)
    engine.push_context("merchant", merchant["merchant_id"], 1, merchant)
    engine.push_context("trigger", trigger["id"], 1, trigger)
    return engine
