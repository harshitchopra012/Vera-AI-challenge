import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from message_intelligence import intelligent_message

try:
    from fastapi import FastAPI, Response
    from pydantic import BaseModel
except Exception:  # pragma: no cover - stdlib fallback is used when FastAPI is absent.
    FastAPI = None
    Response = None
    BaseModel = object


START_TIME = time.time()
TEAM_NAME = "ContextCraft Vera"
VERSION = "1.5.0"

SCOPES = {"category", "merchant", "customer", "trigger"}
contexts: dict[tuple[str, str], dict[str, Any]] = {}
conversations: dict[str, dict[str, Any]] = {}
suppressed: set[str] = set()
merchant_suppressed: set[str] = set()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_context(scope: str, context_id: str | None) -> dict[str, Any] | None:
    if not context_id:
        return None
    stored = contexts.get((scope, context_id))
    return stored["payload"] if stored else None


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def pct(value: Any, signed: bool = False) -> str:
    try:
        number = float(value)
    except Exception:
        return safe_text(value)
    shown = round(number * 100)
    return f"{shown:+d}%" if signed else f"{abs(shown)}%"


def first_name(merchant: dict[str, Any]) -> str:
    identity = merchant.get("identity", {})
    owner = safe_text(identity.get("owner_first_name"))
    if owner:
        return owner
    name = safe_text(identity.get("name"), "there")
    name = re.sub(r"^(dr\.?|mr\.?|mrs\.?|ms\.?)\s+", "", name, flags=re.I)
    return name.split()[0] if name.split() else "there"


def merchant_salutation(category: dict[str, Any], merchant: dict[str, Any]) -> str:
    identity = merchant.get("identity", {})
    category_slug = category.get("slug") or merchant.get("category_slug")
    owner = first_name(merchant)
    if category_slug == "dentists":
        return f"Dr. {owner}" if not owner.lower().startswith("dr") else owner
    return owner


def merchant_name(merchant: dict[str, Any]) -> str:
    return safe_text(merchant.get("identity", {}).get("name"), "your business")


def active_offers(merchant: dict[str, Any]) -> list[str]:
    return [
        safe_text(offer.get("title"))
        for offer in merchant.get("offers", [])
        if safe_text(offer.get("status")).lower() == "active" and safe_text(offer.get("title"))
    ]


def best_offer(category: dict[str, Any], merchant: dict[str, Any]) -> str:
    offers = active_offers(merchant)
    if offers:
        return offers[0]
    for offer in category.get("offer_catalog", []):
        title = safe_text(offer.get("title"))
        offer_type = safe_text(offer.get("type"))
        if title and offer_type != "percentage_discount":
            return title
    return "a specific service offer"


def find_digest_item(category: dict[str, Any], trigger: dict[str, Any]) -> dict[str, Any] | None:
    payload = trigger.get("payload", {})
    wanted = payload.get("top_item_id") or payload.get("digest_item_id") or payload.get("alert_id")
    if wanted:
        for item in category.get("digest", []):
            if item.get("id") == wanted:
                return item
    kind = safe_text(trigger.get("kind")).lower()
    for item in category.get("digest", []):
        item_kind = safe_text(item.get("kind")).lower()
        if kind in item_kind or item_kind in kind:
            return item
    return category.get("digest", [None])[0]


def recent_history_signal(merchant: dict[str, Any]) -> str:
    history = merchant.get("conversation_history", [])
    if not history:
        return ""
    last = history[-1]
    body = safe_text(last.get("body"))
    if body:
        return body[:90]
    return safe_text(last.get("engagement"))


def customer_name(customer: dict[str, Any] | None) -> str:
    if not customer:
        return "there"
    name = safe_text(customer.get("identity", {}).get("name"), "there")
    return name.split("(")[0].strip() or name


def send_as(trigger: dict[str, Any], customer: dict[str, Any] | None) -> str:
    return "merchant_on_behalf" if customer or trigger.get("scope") == "customer" else "vera"


def cta_for(kind: str, customer: dict[str, Any] | None = None) -> str:
    if customer and kind in {"recall_due", "chronic_refill_due", "trial_followup", "customer_lapsed_hard", "wedding_package_followup"}:
        return "multi_choice_slot" if kind == "recall_due" else "binary_yes_no"
    if kind in {"perf_dip", "renewal_due", "gbp_unverified", "winback_eligible", "supply_alert", "regulation_change"}:
        return "binary_yes_no"
    if kind in {"active_planning_intent"}:
        return "binary_confirm_cancel"
    return "open_ended"


def message_strategy(trigger: dict[str, Any], merchant: dict[str, Any], customer: dict[str, Any] | None = None) -> str:
    kind = trigger.get("kind", "")
    if kind in {"perf_dip", "renewal_due", "gbp_unverified", "winback_eligible", "review_theme_emerged"}:
        return "Performance Alert"
    if kind in {"perf_spike", "festival_upcoming", "competitor_opened", "milestone_reached", "category_seasonal"}:
        return "Growth Opportunity"
    if customer or kind in {"recall_due", "customer_lapsed_hard", "chronic_refill_due", "trial_followup", "wedding_package_followup"}:
        return "Missed Customer Engagement"
    return "Smart Recommendation"


def rationale(kind: str, category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any], customer: dict[str, Any] | None) -> str:
    scope = "customer-scoped" if customer else "merchant-scoped"
    strategy = message_strategy(trigger, merchant, customer)
    signals = ", ".join(merchant.get("signals", [])[:2])
    basis = f"{scope} {kind} trigger; strategy={strategy}"
    if signals:
        basis += f"; anchored on merchant signals ({signals})"
    if category.get("voice", {}).get("tone"):
        basis += f"; voice={category['voice']['tone']}"
    return basis[:280]


def wa(*lines: str) -> str:
    return "\n".join(line.strip() for line in lines if line and line.strip())


def compose_research(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    item = find_digest_item(category, trigger) or {}
    sal = merchant_salutation(category, merchant)
    title = safe_text(item.get("title"), "a new category update")
    source = safe_text(item.get("source"), "this week's category digest")
    trial = item.get("trial_n")
    segment = safe_text(item.get("patient_segment")).replace("_", " ")
    agg = merchant.get("customer_aggregate", {})
    high_risk = agg.get("high_risk_adult_count")
    action = safe_text(item.get("actionable"), "I can turn it into a short customer WhatsApp")
    if trial:
        fact = f"{trial:,}-patient study: {title}"
    else:
        fact = title
    if high_risk:
        fit = f"You have {high_risk} high-risk adult patients, so this is directly usable."
    elif segment:
        fit = f"This is relevant for {segment}."
    else:
        fit = action
    return wa(
        f"{sal}, one sharp item from {source}: {fact}.",
        fit,
        "Want me to pull the 2-min summary and draft a patient WhatsApp from it?",
    )


def compose_compliance(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    item = find_digest_item(category, trigger) or {}
    sal = merchant_salutation(category, merchant)
    deadline = trigger.get("payload", {}).get("deadline_iso")
    deadline_text = f" before {deadline}" if deadline else ""
    title = safe_text(item.get("title"), "new compliance update")
    source = safe_text(item.get("source"), "official circular")
    action = safe_text(item.get("actionable"), "I can draft the audit checklist")
    return wa(
        f"{sal}, compliance heads-up: {title}.",
        f"{source}{deadline_text}; {action}.",
        "Want me to make a 5-point checklist for your team?",
    )


def compose_perf(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    payload = trigger.get("payload", {})
    perf = merchant.get("performance", {})
    metric = safe_text(payload.get("metric"), "performance")
    delta = pct(payload.get("delta_pct"), signed=True)
    current = perf.get(metric) or perf.get("calls") or perf.get("views")
    peer = category.get("peer_stats", {}).get(f"avg_{metric}_30d") or category.get("peer_stats", {}).get("avg_ctr")
    offer = best_offer(category, merchant)
    if trigger.get("kind") == "perf_spike":
        return wa(
            f"{sal}, quick win: {metric} is up {delta} in {payload.get('window', '7d')} (now {current}).",
            f"Demand is warm; {offer} is the cleanest hook to capture it today.",
            "Reply YES and I'll draft the Google post.",
        )
    return wa(
        f"{sal}, your {metric} is down {delta} in {payload.get('window', '7d')} (current {current}; peer marker {peer}).",
        f"Fastest fix is not a flat discount; use {offer} with one fresh GBP post.",
        "Reply YES and I'll draft it.",
    )


def compose_renewal(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    payload = trigger.get("payload", {})
    perf = merchant.get("performance", {})
    days = payload.get("days_remaining") or merchant.get("subscription", {}).get("days_remaining")
    amount = payload.get("renewal_amount")
    amount_text = f" for Rs {amount}" if amount else ""
    return wa(
        f"{sal}, your {payload.get('plan', 'Pro')} plan renews in {days} days{amount_text}.",
        f"Last 30 days: {perf.get('views')} views, {perf.get('calls')} calls, {perf.get('directions')} direction taps.",
        "Want me to make a quick ROI note before you renew?",
    )


def compose_festival(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    payload = trigger.get("payload", {})
    festival = payload.get("festival", "festival")
    days = payload.get("days_until")
    offer = best_offer(category, merchant)
    return wa(
        f"{sal}, {festival} is {days} days away.",
        f"Early prep beats last-week discounting; {offer} can become a local WhatsApp + Google post plan.",
        "Want the first draft?",
    )


def compose_curious(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    biz = merchant_name(merchant)
    if merchant.get("category_slug") == "salons":
        guess = "balayage, keratin, or Hair Spa"
    elif merchant.get("category_slug") == "restaurants":
        guess = "thali, delivery combo, or party order"
    else:
        guess = "the service customers ask about most"
    return wa(
        f"Hi {sal}, quick check for {biz}: what got asked most this week - {guess}?",
        "One answer is enough; I'll turn it into a Google post + 4-line WhatsApp reply.",
        "Takes 5 min. Want to try?",
    )


def compose_review_theme(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    payload = trigger.get("payload", {})
    theme = safe_text(payload.get("theme"), "a review theme").replace("_", " ")
    count = payload.get("occurrences_30d")
    quote = safe_text(payload.get("common_quote"))
    quote_text = f'One customer said: "{quote}".' if quote else f"{theme} is now visible enough to act on."
    return wa(
        f"{sal}, review pattern spotted: {count} mentions of {theme} in 30 days.",
        quote_text,
        "Want me to draft a calm reply template + one ops note for the team?",
    )


def compose_planning(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    topic = safe_text(trigger.get("payload", {}).get("intent_topic")).replace("_", " ")
    if "thali" in topic:
        return wa(
            f"{sal}, here's a starter corporate thali package: 10 @ Rs 125, 25 @ Rs 115, 50+ @ Rs 105.",
            "Order previous day by 5pm; delivery 12:30-1pm keeps lunch ops predictable.",
            "Want me to draft the 3-line office WhatsApp now?",
        )
    if "kids_yoga" in topic or "kids yoga" in topic:
        return wa(
            f"{sal}, kids yoga camp draft: 4 weeks, 3 classes/week, age 7-12.",
            "Sat trial at 8am + intro price Rs 2,499 gives parents a simple first step.",
            "Reply CONFIRM and I'll turn this into your GBP post + parent WhatsApp.",
        )
    return wa(
        f"{sal}, yes - moving to action for {topic}.",
        "I can format one clean Google post plus WhatsApp copy.",
        "Reply CONFIRM and I'll prepare the first usable draft.",
    )


def compose_seasonal_gym(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    payload = trigger.get("payload", {})
    agg = merchant.get("customer_aggregate", {})
    members = agg.get("total_active_members")
    return wa(
        f"{sal}, views are down {pct(payload.get('delta_pct'))} this week, but this matches the Apr-Jun gym lull.",
        f"Better move: pause acquisition push and protect retention for your {members} active members.",
        "Want me to draft a summer attendance challenge?",
    )


def compose_supply_alert(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    payload = trigger.get("payload", {})
    batches = ", ".join(payload.get("affected_batches", []))
    molecule = payload.get("molecule", "medicine")
    chronic = merchant.get("customer_aggregate", {}).get("chronic_rx_count")
    return wa(
        f"{sal}, urgent but manageable: {molecule} recall on batches {batches} by {payload.get('manufacturer')}.",
        f"You have {chronic} chronic-Rx customers; this needs a precise replacement workflow.",
        "Reply YES and I'll draft the customer WhatsApp + pickup steps.",
    )


def compose_winback(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    payload = trigger.get("payload", {})
    days = payload.get("days_since_expiry") or merchant.get("subscription", {}).get("days_since_expiry")
    dip = pct(payload.get("perf_dip_pct"))
    lapsed = payload.get("lapsed_customers_added_since_expiry") or merchant.get("customer_aggregate", {}).get("lapsed_90d_plus")
    return wa(
        f"{sal}, plan expired {days} days ago; performance is down {dip}.",
        f"{lapsed} more customers have moved into lapsed status since then.",
        "Reply YES and I'll make a winback plan with one service-price offer + 2 WhatsApp lines.",
    )


def compose_dormant(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    payload = trigger.get("payload", {})
    days = payload.get("days_since_last_merchant_message")
    last_topic = safe_text(payload.get("last_topic"), "the last topic").replace("_", " ")
    offer = best_offer(category, merchant)
    return wa(
        f"Hi {sal}, it's been {days} days since we spoke after {last_topic}.",
        f"One low-effort restart: {offer} as a fresh Google post.",
        "Want me to draft it in 4 lines?",
    )


def compose_competitor(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    payload = trigger.get("payload", {})
    competitor = payload.get("competitor_name", "a competitor")
    distance = payload.get("distance_km")
    their_offer = payload.get("their_offer")
    opened = payload.get("opened_date")
    ours = best_offer(category, merchant)
    return wa(
        f"{sal}, new competitor alert: {competitor} opened {distance} km away on {opened}.",
        f"They're pushing {their_offer}; your stronger anchor is {ours}.",
        "Want me to draft a calm counter-post without starting a price war?",
    )


def compose_category_seasonal(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    payload = trigger.get("payload", {})
    trends = [safe_text(t).replace("_", " ") for t in payload.get("trends", [])]
    trend_text = ", ".join(trends[:4])
    return wa(
        f"{sal}, summer shelf shift is already visible: {trend_text}.",
        "Move high-demand items to counter visibility and push cold/cough back.",
        "Want me to draft the customer WhatsApp + shelf checklist?",
    )


def compose_milestone(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    payload = trigger.get("payload", {})
    now = payload.get("value_now")
    target = payload.get("milestone_value")
    metric = safe_text(payload.get("metric"), "milestone").replace("_", " ")
    return wa(
        f"{sal}, you're at {now} {metric} - just {int(target) - int(now)} away from {target}.",
        "A short thank-you post now can nudge the next few reviews naturally.",
        "Want me to draft it?",
    )


def compose_gbp(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    uplift = pct(trigger.get("payload", {}).get("estimated_uplift_pct"))
    path = safe_text(trigger.get("payload", {}).get("verification_path"), "verification").replace("_", " ")
    perf = merchant.get("performance", {})
    return wa(
        f"{sal}, your Google profile is still unverified.",
        f"With {perf.get('views')} views in 30 days, verification can unlock roughly {uplift} more profile actions.",
        f"Reply YES and I'll prep the {path} steps.",
    )


def compose_customer(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any], customer: dict[str, Any]) -> str:
    kind = trigger.get("kind")
    payload = trigger.get("payload", {})
    cname = customer_name(customer)
    mname = merchant_name(merchant)
    owner = first_name(merchant)
    offer = best_offer(category, merchant)
    if kind == "recall_due":
        slots = [s.get("label") for s in payload.get("available_slots", []) if s.get("label")]
        slot_text = " ya ".join(slots[:2]) if slots else "this week"
        return wa(
            f"Hi {cname}, {mname} here.",
            f"Your {payload.get('service_due', 'follow-up').replace('_', ' ')} is due from last visit on {payload.get('last_service_date')}.",
            f"Slots ready: {slot_text}. {offer}. Reply 1/2, or share a better time.",
        )
    if kind == "wedding_package_followup":
        days = payload.get("days_to_wedding")
        return wa(
            f"Hi {cname}, {owner} from {mname} here.",
            f"{days} days to your wedding - ideal window for the 30-day skin-prep plan after your trial.",
            f"{offer}. Want me to block your preferred Saturday slot next week?",
        )
    if kind == "customer_lapsed_hard":
        days = payload.get("days_since_last_visit")
        focus = safe_text(payload.get("previous_focus"), "your routine").replace("_", " ")
        return wa(
            f"Hi {cname}, {owner} from {mname} here.",
            f"It's been {days} days - no judgment. A 45-min evening {focus} restart is enough.",
            f"{offer}. Reply YES and I'll hold a free trial spot.",
        )
    if kind == "trial_followup":
        slots = [s.get("label") for s in payload.get("next_session_options", []) if s.get("label")]
        return wa(
            f"Hi {cname}, {mname} here.",
            f"Hope the trial on {payload.get('trial_date')} felt good; next beginner-friendly slot is {slots[0] if slots else 'this week'}.",
            "Want me to reserve it? Reply YES.",
        )
    if kind == "chronic_refill_due":
        meds = ", ".join(payload.get("molecule_list", []))
        delivery = " Free home delivery to saved address" if payload.get("delivery_address_saved") else ""
        senior = " Senior discount applied." if customer.get("identity", {}).get("senior_citizen") else ""
        return wa(
            f"Namaste - {mname} here.",
            f"{cname}'s monthly medicines ({meds}) run out on {payload.get('stock_runs_out_iso', '')[:10]}.",
            f"Same dose pack ready.{senior}{delivery}. Reply CONFIRM to dispatch, or tell us if dosage changed.",
        )
    return wa(
        f"Hi {cname}, {mname} here.",
        f"A quick update from your last visit: {best_offer(category, merchant)} is available this week.",
        "Reply YES if you want us to hold a slot.",
    )


def compose_generic(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    sal = merchant_salutation(category, merchant)
    kind = safe_text(trigger.get("kind"), "update").replace("_", " ")
    payload_bits = []
    for key, value in trigger.get("payload", {}).items():
        if isinstance(value, (str, int, float, bool)):
            payload_bits.append(f"{key}: {value}")
    facts = "; ".join(payload_bits[:3])
    fact_text = f" ({facts})" if facts else ""
    return wa(
        f"{sal}, quick update: {kind}{fact_text}.",
        "The opportunity is to turn this into one concrete Google post or WhatsApp draft.",
        "Want me to make the first draft?",
    )


def compose_body(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any], customer: dict[str, Any] | None = None) -> str:
    if customer or trigger.get("scope") == "customer":
        return compose_customer(category, merchant, trigger, customer or {})

    kind = trigger.get("kind")
    dispatch = {
        "research_digest": compose_research,
        "cde_opportunity": compose_research,
        "regulation_change": compose_compliance,
        "perf_dip": compose_perf,
        "perf_spike": compose_perf,
        "renewal_due": compose_renewal,
        "festival_upcoming": compose_festival,
        "curious_ask_due": compose_curious,
        "review_theme_emerged": compose_review_theme,
        "active_planning_intent": compose_planning,
        "seasonal_perf_dip": compose_seasonal_gym,
        "supply_alert": compose_supply_alert,
        "gbp_unverified": compose_gbp,
        "winback_eligible": compose_winback,
        "dormant_with_vera": compose_dormant,
        "competitor_opened": compose_competitor,
        "category_seasonal": compose_category_seasonal,
        "milestone_reached": compose_milestone,
    }
    fn = dispatch.get(kind, compose_generic)
    return fn(category, merchant, trigger)


def template_name_for(trigger: dict[str, Any], customer: dict[str, Any] | None) -> str:
    kind = trigger.get("kind", "generic")
    if customer or trigger.get("scope") == "customer":
        return f"merchant_{kind}_v1"
    return f"vera_{kind}_v1"


def make_conversation_id(merchant_id: str, trigger_id: str, customer_id: str | None) -> str:
    raw = f"{merchant_id}:{trigger_id}:{customer_id or 'merchant'}"
    suffix = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    stem = re.sub(r"[^a-zA-Z0-9]+", "_", f"conv_{merchant_id}_{trigger_id}")[:80]
    return f"{stem}_{suffix}"


def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None) -> dict:
    kind = trigger.get("kind", "generic")
    body, intelligence = intelligent_message(category, merchant, trigger, customer)
    if intelligence.get("quality_issues"):
        body = compose_body(category, merchant, trigger, customer)
    result = {
        "body": body,
        "cta": cta_for(kind, customer),
        "send_as": send_as(trigger, customer),
        "suppression_key": trigger.get("suppression_key", ""),
        "rationale": f"{rationale(kind, category, merchant, trigger, customer)}; insight_score={intelligence.get('insight_score')}; candidates={intelligence.get('candidate_count')}",
    }
    return result


def build_action(trigger_id: str) -> dict[str, Any] | None:
    trigger = get_context("trigger", trigger_id)
    if not trigger:
        return None
    merchant_id = trigger.get("merchant_id")
    if merchant_id in merchant_suppressed:
        return None
    suppression_key = trigger.get("suppression_key", trigger_id)
    if suppression_key in suppressed:
        return None
    merchant = get_context("merchant", merchant_id)
    if not merchant:
        return None
    category = get_context("category", merchant.get("category_slug") or trigger.get("payload", {}).get("category"))
    if not category:
        return None
    customer = get_context("customer", trigger.get("customer_id")) if trigger.get("customer_id") else None
    if trigger.get("scope") == "customer" and not customer:
        return None

    composed = compose(category, merchant, trigger, customer)
    conversation_id = make_conversation_id(merchant_id, trigger_id, trigger.get("customer_id"))
    action = {
        "conversation_id": conversation_id,
        "merchant_id": merchant_id,
        "customer_id": trigger.get("customer_id"),
        "send_as": composed["send_as"],
        "trigger_id": trigger_id,
        "template_name": template_name_for(trigger, customer),
        "template_params": [merchant_name(merchant), trigger.get("kind", "update"), composed["body"][:250]],
        **composed,
    }
    conversations[conversation_id] = {
        "merchant_id": merchant_id,
        "customer_id": trigger.get("customer_id"),
        "trigger_id": trigger_id,
        "sent_bodies": [composed["body"]],
        "messages": [{"from": "bot", "body": composed["body"], "ts": utc_now()}],
        "auto_count": 0,
        "ended": False,
    }
    suppressed.add(suppression_key)
    return action


AUTO_PATTERNS = [
    r"thank you for contacting",
    r"team will respond",
    r"automated assistant",
    r"business hours",
    r"we will get back",
    r"your message is important",
]
STOP_PATTERNS = [r"\bstop\b", r"not interested", r"don't message", r"dont message", r"spam", r"useless", r"bothering"]
YES_PATTERNS = [r"\byes\b", r"\bok\b", r"let'?s do", r"go ahead", r"confirm", r"send", r"please", r"start", r"kar do", r"chalo"]
OUT_OF_SCOPE = [r"\bgst\b", r"tax filing", r"income tax", r"loan", r"legal notice"]


def is_auto_reply(message: str) -> bool:
    text = message.lower()
    return any(re.search(pattern, text) for pattern in AUTO_PATTERNS)


def has_stop(message: str) -> bool:
    text = message.lower()
    return any(re.search(pattern, text) for pattern in STOP_PATTERNS)


def has_yes(message: str) -> bool:
    text = message.lower()
    return any(re.search(pattern, text) for pattern in YES_PATTERNS)


def is_out_of_scope(message: str) -> bool:
    text = message.lower()
    return any(re.search(pattern, text) for pattern in OUT_OF_SCOPE)


def action_reply(body: str, cta: str, rationale_text: str) -> dict[str, Any]:
    return {"action": "send", "body": body, "cta": cta, "rationale": rationale_text}


def reply_logic(conversation_id: str, merchant_id: str | None, customer_id: str | None, message: str, from_role: str) -> dict[str, Any]:
    state = conversations.setdefault(
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
    state["messages"].append({"from": from_role, "body": message, "ts": utc_now()})
    merchant_id = merchant_id or state.get("merchant_id")

    if has_stop(message):
        if merchant_id:
            merchant_suppressed.add(merchant_id)
        state["ended"] = True
        return {"action": "end", "rationale": "Merchant/customer explicitly opted out or showed hostility; ending and suppressing further outreach."}

    if is_auto_reply(message):
        state["auto_count"] = int(state.get("auto_count", 0)) + 1
        if state["auto_count"] == 1:
            if state.get("sent_bodies"):
                return action_reply(
                    "Looks like an auto-reply. When the owner sees this, they can just reply YES and I will handle the draft.",
                    "binary_yes_no",
                    "Detected canned WhatsApp Business phrasing; leaving one owner-facing instruction.",
                )
            return {"action": "wait", "wait_seconds": 14400, "rationale": "Detected canned WhatsApp Business phrasing; backing off for 4 hours."}
        if state["auto_count"] == 2:
            return {"action": "wait", "wait_seconds": 86400, "rationale": "Same auto-reply pattern repeated; waiting 24h for a real owner response."}
        state["ended"] = True
        return {"action": "end", "rationale": "Auto-reply repeated three times; closing to avoid wasting turns."}

    state["auto_count"] = 0
    merchant = get_context("merchant", merchant_id)
    trigger = get_context("trigger", state.get("trigger_id")) if state.get("trigger_id") else None
    category = get_context("category", merchant.get("category_slug")) if merchant else None
    sal = merchant_salutation(category or {}, merchant or {"identity": {}}) if merchant else "Great"

    if is_out_of_scope(message):
        return action_reply(
            "That part is outside Vera's lane, so your CA or specialist should handle it. Coming back to this growth task: want me to draft the message first?",
            "binary_yes_no",
            "Politely declined out-of-scope request and returned to the active engagement task.",
        )

    if has_yes(message):
        kind = trigger.get("kind") if trigger else ""
        if kind == "active_planning_intent":
            body = f"{sal}, done. I am formatting the plan now with pricing, timing, and WhatsApp copy. Reply CONFIRM and I will use the current draft as the final version."
        elif kind in {"research_digest", "cde_opportunity", "regulation_change"}:
            body = f"{sal}, sending the short summary now. I also drafted a customer-safe WhatsApp version in plain language; reply CONFIRM and I will package it as a Google post too."
        elif kind in {"perf_dip", "perf_spike", "gbp_unverified", "renewal_due"}:
            body = f"{sal}, great. I will make the first draft from your current numbers, not a generic promo. Reply CONFIRM and I will keep it to one Google post plus one WhatsApp line."
        else:
            body = f"{sal}, great. I am moving from suggestion to action now. Reply CONFIRM and I will prepare the first usable draft."
        return action_reply(body, "binary_confirm_cancel", "Detected explicit commitment; switched to action mode instead of further qualification.")

    if "price" in message.lower() or "cost" in message.lower() or "kitna" in message.lower():
        offer = best_offer(category or {}, merchant or {})
        return action_reply(
            f"For this draft, I would anchor on {offer} because service+price beats flat discounts. Want me to write it in a sharper local style?",
            "binary_yes_no",
            "Answered pricing concern using the merchant/category offer context.",
        )

    return action_reply(
        "Got it. I can keep this very light: one specific draft, one CTA, and you approve before anything goes out. Want me to prepare that first draft?",
        "binary_yes_no",
        "Acknowledged ambiguous reply and moved toward a low-friction next step.",
    )


def healthz_payload() -> dict[str, Any]:
    counts = {scope: 0 for scope in SCOPES}
    for scope, _ in contexts:
        counts[scope] = counts.get(scope, 0) + 1
    return {"status": "ok", "uptime_seconds": int(time.time() - START_TIME), "contexts_loaded": counts}


def metadata_payload() -> dict[str, Any]:
    return {
        "team_name": TEAM_NAME,
        "team_members": ["Harsh"],
        "model": "deterministic-context-composer",
        "approach": "stateful message engine with insight ranking, conversion polish, quality filtering, suppression, and replay handlers",
        "contact_email": "not-provided@example.com",
        "version": VERSION,
        "submitted_at": "2026-05-01T00:00:00Z",
    }


def push_context_payload(body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    scope = body.get("scope")
    context_id = body.get("context_id")
    version = body.get("version")
    payload = body.get("payload")
    if scope not in SCOPES:
        return {"accepted": False, "reason": "invalid_scope", "details": f"scope must be one of {sorted(SCOPES)}"}, 400
    if not context_id or not isinstance(version, int) or not isinstance(payload, dict):
        return {"accepted": False, "reason": "malformed_context"}, 400
    key = (scope, context_id)
    current = contexts.get(key)
    if current and current["version"] >= version:
        return {"accepted": False, "reason": "stale_version", "current_version": current["version"]}, 409
    contexts[key] = {"version": version, "payload": payload, "stored_at": utc_now()}
    return {"accepted": True, "ack_id": f"ack_{context_id}_v{version}", "stored_at": contexts[key]["stored_at"]}, 200


def tick_payload(body: dict[str, Any]) -> dict[str, Any]:
    actions = []
    for trigger_id in body.get("available_triggers", [])[:20]:
        action = build_action(trigger_id)
        if action:
            actions.append(action)
    return {"actions": actions}


def reply_payload(body: dict[str, Any]) -> dict[str, Any]:
    return reply_logic(
        safe_text(body.get("conversation_id"), "conv_unknown"),
        body.get("merchant_id"),
        body.get("customer_id"),
        safe_text(body.get("message")),
        safe_text(body.get("from_role"), "merchant"),
    )


if FastAPI:
    app = FastAPI(title="ContextCraft Vera", version=VERSION)

    def model_to_dict(model: Any) -> dict[str, Any]:
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return model.dict()

    class ContextBody(BaseModel):
        scope: str
        context_id: str
        version: int
        payload: dict[str, Any]
        delivered_at: str | None = None

    class TickBody(BaseModel):
        now: str | None = None
        available_triggers: list[str] = []

    class ReplyBody(BaseModel):
        conversation_id: str
        merchant_id: str | None = None
        customer_id: str | None = None
        from_role: str = "merchant"
        message: str
        received_at: str | None = None
        turn_number: int | None = None

    @app.get("/v1/healthz")
    async def healthz():
        return healthz_payload()

    @app.get("/v1/metadata")
    async def metadata():
        return metadata_payload()

    @app.post("/v1/context")
    async def push_context(body: ContextBody, response: Response):
        payload, status = push_context_payload(model_to_dict(body))
        response.status_code = status
        return payload

    @app.post("/v1/tick")
    async def tick(body: TickBody):
        return tick_payload(model_to_dict(body))

    @app.post("/v1/reply")
    async def reply(body: ReplyBody):
        return reply_payload(model_to_dict(body))

    @app.post("/v1/teardown")
    async def teardown():
        contexts.clear()
        conversations.clear()
        suppressed.clear()
        merchant_suppressed.clear()
        return {"accepted": True, "wiped_at": utc_now()}


class StdlibHandler(BaseHTTPRequestHandler):
    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/healthz":
            self._json(healthz_payload())
        elif self.path == "/v1/metadata":
            self._json(metadata_payload())
        else:
            self._json({"error": "not_found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._read_body()
            if self.path == "/v1/context":
                payload, status = push_context_payload(body)
                self._json(payload, status)
            elif self.path == "/v1/tick":
                self._json(tick_payload(body))
            elif self.path == "/v1/reply":
                self._json(reply_payload(body))
            elif self.path == "/v1/teardown":
                contexts.clear()
                conversations.clear()
                suppressed.clear()
                merchant_suppressed.clear()
                self._json({"accepted": True, "wiped_at": utc_now()})
            else:
                self._json({"error": "not_found"}, 404)
        except Exception as exc:
            self._json({"error": "server_error", "details": str(exc)}, 500)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    server = ThreadingHTTPServer((host, port), StdlibHandler)
    print(f"ContextCraft Vera listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server(port=int(os.environ.get("PORT", "8080")))
