import hashlib
import re
from typing import Any


PERFORMANCE_KINDS = {"perf_dip", "renewal_due", "gbp_unverified", "winback_eligible", "review_theme_emerged"}
GROWTH_KINDS = {"perf_spike", "festival_upcoming", "competitor_opened", "milestone_reached", "category_seasonal"}
CUSTOMER_KINDS = {"recall_due", "customer_lapsed_hard", "chronic_refill_due", "trial_followup", "wedding_package_followup"}


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


def money(value: Any) -> str:
    text = safe_text(value)
    if not text:
        return ""
    return text if "Rs" in text or "₹" in text else f"Rs {text}"


def first_name(merchant: dict[str, Any], category: dict[str, Any] | None = None) -> str:
    identity = merchant.get("identity", {})
    owner = safe_text(identity.get("owner_first_name"))
    if owner:
        base = owner
    else:
        name = safe_text(identity.get("name"), "there")
        name = re.sub(r"^(dr\.?|mr\.?|mrs\.?|ms\.?)\s+", "", name, flags=re.I)
        base = name.split()[0] if name.split() else "there"
    if (category or {}).get("slug") == "dentists" and not base.lower().startswith("dr"):
        return f"Dr. {base}"
    return base


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
        if title and safe_text(offer.get("type")) != "percentage_discount":
            return title
    return "one service-price offer"


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


def strategy_for(trigger: dict[str, Any], customer: dict[str, Any] | None = None) -> str:
    kind = trigger.get("kind", "")
    if kind in PERFORMANCE_KINDS:
        return "Performance Alert"
    if kind in GROWTH_KINDS:
        return "Growth Opportunity"
    if customer or kind in CUSTOMER_KINDS:
        return "Missed Customer Engagement"
    return "Smart Recommendation"


def tone_for(strategy: str, trigger: dict[str, Any]) -> str:
    urgency = int(trigger.get("urgency") or 1)
    if urgency >= 4 or strategy == "Performance Alert":
        return "urgent"
    if strategy == "Growth Opportunity":
        return "opportunity"
    if strategy == "Missed Customer Engagement":
        return "warm"
    return "curious"


def impact_score(candidate: dict[str, Any]) -> int:
    score = 0
    score += int(candidate.get("revenue", 0)) * 4
    score += int(candidate.get("engagement", 0)) * 3
    score += int(candidate.get("urgency", 0)) * 2
    score += int(candidate.get("confidence", 0)) * 2
    if re.search(r"\d", candidate.get("insight", "")):
        score += 5
    if candidate.get("benchmark"):
        score += 4
    if candidate.get("customer_fit"):
        score += 3
    return score


def insight_candidate(
    kind: str,
    insight: str,
    action: str,
    benchmark: str = "",
    revenue: int = 1,
    engagement: int = 1,
    urgency: int = 1,
    confidence: int = 1,
    customer_fit: bool = False,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "insight": insight,
        "benchmark": benchmark,
        "action": action,
        "revenue": revenue,
        "engagement": engagement,
        "urgency": urgency,
        "confidence": confidence,
        "customer_fit": customer_fit,
    }


def generate_insights(
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    kind = trigger.get("kind", "")
    payload = trigger.get("payload", {})
    perf = merchant.get("performance", {})
    peer = category.get("peer_stats", {})
    agg = merchant.get("customer_aggregate", {})
    offer = best_offer(category, merchant)
    insights: list[dict[str, Any]] = []

    if customer:
        cname = safe_text(customer.get("identity", {}).get("name"), "this customer").split("(")[0].strip()
        if kind == "recall_due":
            slots = [slot.get("label") for slot in payload.get("available_slots", []) if slot.get("label")]
            slot_text = " / ".join(slots[:2]) if slots else "this week"
            insights.append(insight_candidate(
                kind,
                f"{cname}'s {payload.get('service_due', 'follow-up').replace('_', ' ')} is due after the {payload.get('last_service_date')} visit.",
                f"Offer {slot_text} with {offer}",
                benchmark="recall window is open now",
                revenue=3,
                engagement=5,
                urgency=4,
                confidence=5,
                customer_fit=True,
            ))
        elif kind == "customer_lapsed_hard":
            insights.append(insight_candidate(
                kind,
                f"{cname} has been away {payload.get('days_since_last_visit')} days, but the last goal was {safe_text(payload.get('previous_focus')).replace('_', ' ')}.",
                f"Offer a no-pressure restart using {offer}",
                benchmark=f"previous membership ran {payload.get('previous_membership_months')} months",
                revenue=4,
                engagement=5,
                urgency=3,
                confidence=4,
                customer_fit=True,
            ))
        elif kind == "chronic_refill_due":
            meds = ", ".join(payload.get("molecule_list", []))
            insights.append(insight_candidate(
                kind,
                f"{cname}'s {meds} stock runs out on {safe_text(payload.get('stock_runs_out_iso'))[:10]}.",
                "Confirm same-dose dispatch to the saved address",
                benchmark="refill timing is the conversion window",
                revenue=5,
                engagement=4,
                urgency=5,
                confidence=5,
                customer_fit=True,
            ))
        else:
            insights.append(insight_candidate(
                kind,
                f"{cname} has a live follow-up moment from the last interaction.",
                f"Use {offer} as the next step",
                revenue=3,
                engagement=4,
                urgency=3,
                confidence=3,
                customer_fit=True,
            ))
        return insights

    if kind in {"research_digest", "cde_opportunity", "regulation_change"}:
        item = find_digest_item(category, trigger) or {}
        title = safe_text(item.get("title"), "new category update")
        source = safe_text(item.get("source"), "this week's digest")
        trial = item.get("trial_n")
        high_risk = agg.get("high_risk_adult_count")
        if high_risk:
            insight = f"{source}: {title}; it maps to your {high_risk} high-risk adult patients."
        elif trial:
            insight = f"{source}: {title}; the study size is {trial:,} patients."
        else:
            insight = f"{source}: {title}."
        insights.append(insight_candidate(
            kind,
            insight,
            "Turn it into a 2-min owner summary + patient WhatsApp draft",
            benchmark=safe_text(item.get("actionable")),
            revenue=3,
            engagement=4,
            urgency=int(trigger.get("urgency") or 2),
            confidence=5,
            customer_fit=bool(high_risk),
        ))

    if kind in {"perf_dip", "perf_spike"}:
        metric = safe_text(payload.get("metric"), "performance")
        delta = pct(payload.get("delta_pct"), signed=True)
        current = perf.get(metric) or perf.get("calls") or perf.get("views")
        peer_value = peer.get(f"avg_{metric}_30d") or peer.get("avg_ctr")
        direction = "up" if kind == "perf_spike" else "down"
        insights.append(insight_candidate(
            kind,
            f"{metric} is {direction} {delta} in {payload.get('window', '7d')} (current {current}; peer marker {peer_value}).",
            f"Use {offer} as the single hook in a fresh Google post",
            benchmark=f"peer marker {peer_value}",
            revenue=4,
            engagement=4,
            urgency=int(trigger.get("urgency") or 3),
            confidence=5,
        ))

    if kind == "renewal_due":
        insights.append(insight_candidate(
            kind,
            f"Renewal is in {payload.get('days_remaining')} days; last 30 days brought {perf.get('views')} views, {perf.get('calls')} calls, {perf.get('directions')} direction taps.",
            "Send a one-page ROI note before renewal",
            benchmark=f"renewal amount {money(payload.get('renewal_amount'))}",
            revenue=5,
            engagement=3,
            urgency=4,
            confidence=5,
        ))

    if kind == "review_theme_emerged":
        theme = safe_text(payload.get("theme")).replace("_", " ")
        insights.append(insight_candidate(
            kind,
            f"{payload.get('occurrences_30d')} reviews now mention {theme}; one quote says '{safe_text(payload.get('common_quote'))}'.",
            "Draft one calm public reply and one ops note",
            benchmark="review theme is repeated enough to affect trust",
            revenue=3,
            engagement=4,
            urgency=3,
            confidence=5,
        ))

    if kind == "competitor_opened":
        insights.append(insight_candidate(
            kind,
            f"{payload.get('competitor_name')} opened {payload.get('distance_km')} km away with {payload.get('their_offer')}.",
            f"Counter-position {offer} without starting a price war",
            benchmark=f"opened on {payload.get('opened_date')}",
            revenue=4,
            engagement=4,
            urgency=3,
            confidence=4,
        ))

    if kind == "category_seasonal":
        trends = ", ".join(safe_text(t).replace("_", " ") for t in payload.get("trends", [])[:4])
        insights.append(insight_candidate(
            kind,
            f"Seasonal demand is shifting now: {trends}.",
            "Move high-demand items to counter visibility and send one customer WhatsApp",
            benchmark="seasonal shelf action recommended",
            revenue=4,
            engagement=4,
            urgency=3,
            confidence=5,
        ))

    if kind == "milestone_reached":
        now = payload.get("value_now")
        target = payload.get("milestone_value")
        try:
            gap = int(target) - int(now)
        except Exception:
            gap = "few"
        insights.append(insight_candidate(
            kind,
            f"You are at {now} {safe_text(payload.get('metric')).replace('_', ' ')} - just {gap} away from {target}.",
            "Post a short thank-you nudge to unlock the next reviews",
            benchmark=f"milestone target {target}",
            revenue=2,
            engagement=4,
            urgency=2,
            confidence=5,
        ))

    if kind == "winback_eligible":
        insights.append(insight_candidate(
            kind,
            f"Plan expired {payload.get('days_since_expiry')} days ago; performance is down {pct(payload.get('perf_dip_pct'))} and {payload.get('lapsed_customers_added_since_expiry')} more customers lapsed.",
            f"Restart with {offer} and two WhatsApp lines",
            benchmark="post-expiry dip is already visible",
            revenue=5,
            engagement=3,
            urgency=3,
            confidence=5,
        ))

    if not insights:
        payload_facts = [f"{k}: {v}" for k, v in payload.items() if isinstance(v, (str, int, float, bool))]
        fact = "; ".join(payload_facts[:2]) or f"{kind.replace('_', ' ')} is active now"
        insights.append(insight_candidate(
            kind,
            fact,
            f"Turn it into one practical draft using {offer}",
            revenue=2,
            engagement=3,
            urgency=int(trigger.get("urgency") or 1),
            confidence=2,
        ))

    return insights


def select_best_insight(insights: list[dict[str, Any]]) -> dict[str, Any]:
    return max(insights, key=impact_score)


def stable_variant(*parts: Any, modulo: int = 3) -> int:
    raw = "|".join(safe_text(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % modulo


def hook_for(tone: str, salutation: str, insight: dict[str, Any], variant: int) -> str:
    templates = {
        "urgent": [
            "{sal}, this needs attention now:",
            "{sal}, quick alert before this leaks more value:",
            "{sal}, one issue is showing up clearly:",
        ],
        "opportunity": [
            "{sal}, there is a useful opening here:",
            "{sal}, quick upside I would not ignore:",
            "{sal}, this is a good moment to move:",
        ],
        "warm": [
            "{sal}, one customer moment is ready to act on:",
            "{sal}, this is a low-friction follow-up:",
            "{sal}, there is an easy customer win here:",
        ],
        "curious": [
            "{sal}, one thing stood out to me:",
            "{sal}, quick insight from the data:",
            "{sal}, worth a look:",
        ],
    }
    selected = templates.get(tone, templates["curious"])[variant % 3]
    return selected.format(sal=salutation)


def natural_cta(strategy: str, tone: str, variant: int) -> str:
    ctas = {
        "urgent": [
            "Want me to draft it now?",
            "Should I prepare the fix in one message?",
            "Want the ready-to-send version?",
        ],
        "opportunity": [
            "Want me to turn this into the first draft?",
            "Should I package this into a post you can approve?",
            "Want the ready version?",
        ],
        "warm": [
            "Want me to send the draft for approval?",
            "Should I prepare the customer note?",
            "Want me to hold this as a ready reply?",
        ],
        "curious": [
            "Want me to pull the draft together?",
            "Should I make the 2-min version?",
            "Want me to turn this into a usable message?",
        ],
    }
    return ctas.get(tone, ctas["curious"])[variant % 3]


def render_message(
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None,
    insight: dict[str, Any],
) -> str:
    strategy = strategy_for(trigger, customer)
    tone = tone_for(strategy, trigger)
    salutation = first_name(merchant, category)
    variant = stable_variant(merchant.get("merchant_id"), trigger.get("id"), insight.get("insight"))
    hook = hook_for(tone, salutation, insight, variant)
    benchmark = safe_text(insight.get("benchmark"))
    insight_line = insight["insight"] if not benchmark else f"{insight['insight']} ({benchmark})"
    cta = natural_cta(strategy, tone, variant)
    return "\n".join([
        hook,
        insight_line,
        insight["action"] + ".",
        cta,
    ])


def recent_memory(merchant: dict[str, Any]) -> str:
    history = merchant.get("conversation_history", [])
    for turn in reversed(history[-4:]):
        if safe_text(turn.get("from")).lower() == "merchant":
            body = safe_text(turn.get("body"))
            if body:
                return body[:90]
    return ""


def memory_is_relevant(memory: str, insight: dict[str, Any]) -> bool:
    if not memory:
        return False
    combined = f"{insight.get('insight', '')} {insight.get('action', '')}".lower()
    words = {
        word
        for word in re.findall(r"[a-zA-Z]{4,}", memory.lower())
        if word not in {"please", "focus", "good", "idea", "what", "would", "look", "like", "send"}
    }
    return any(word in combined for word in words)


def surprise_implication(insight: dict[str, Any], merchant: dict[str, Any], category: dict[str, Any]) -> str:
    text = safe_text(insight.get("insight"))
    if "%" in text:
        if "down" in text.lower() or "-" in text:
            return "That usually means demand is leaking before customers even call."
        return "That means demand is already warm; waiting makes the spike harder to convert."

    people_match = re.search(
        r"\b(\d{2,}(?:,\d{3})*)\s+(?:high-risk\s+adult\s+|chronic-rx\s+|active\s+)?(?:patients|customers|members|reviews)\b",
        text,
        flags=re.I,
    )
    if people_match:
        number = people_match.group(1)
        noun = people_match.group(0).replace(number, "").strip()
        return f"{number} {noun} is enough for a focused follow-up, not a generic promo."

    action_match = re.search(r"\b(\d{2,}(?:,\d{3})*)\s+(?:views|calls|direction taps|directions)\b", text, flags=re.I)
    if action_match:
        number = action_match.group(1)
        noun = action_match.group(0).replace(number, "").strip()
        return f"{number} {noun} is enough signal to test one sharper CTA this week."

    peer_ctr = category.get("peer_stats", {}).get("avg_ctr")
    merchant_ctr = merchant.get("performance", {}).get("ctr")
    if peer_ctr and merchant_ctr and merchant_ctr < peer_ctr:
        return f"Your CTR is below the {peer_ctr:.1%} peer marker, so better copy can unlock the same traffic."
    return ""


def decision_justification(insight: dict[str, Any], strategy: str) -> str:
    if strategy == "Performance Alert":
        return "This matters because it hits incoming leads directly."
    if strategy == "Growth Opportunity":
        return "This matters because timing can turn attention into bookings."
    if strategy == "Missed Customer Engagement":
        return "This matters because the customer timing is already warm."
    if "patient" in safe_text(insight.get("insight")).lower() or "customer" in safe_text(insight.get("insight")).lower():
        return "This matters because it gives you a relevant reason to re-engage."
    return "This matters because it turns insight into one clear next action."


def confidence_signal(strategy: str) -> str:
    if strategy == "Performance Alert":
        return "This tends to recover performance fastest."
    if strategy == "Growth Opportunity":
        return "This usually converts better than a broad promo."
    if strategy == "Missed Customer Engagement":
        return "This works best while the reason to reply is fresh."
    return "This usually works better than sending a generic update."


def urgency_signal(trigger: dict[str, Any]) -> str:
    urgency = int(trigger.get("urgency") or 1)
    if urgency >= 4:
        return "Acting this week matters."
    if urgency >= 2:
        return "Early action gives better results."
    return ""


def outcome_visualization(insight: dict[str, Any], strategy: str) -> str:
    text = safe_text(insight.get("insight")).lower()
    if strategy == "Performance Alert":
        return "Goal: recover the lost response path before it compounds."
    if strategy == "Growth Opportunity":
        return "Goal: convert the current attention into one visible offer."
    if strategy == "Missed Customer Engagement":
        return "Goal: make the next reply feel obvious, not promotional."
    if "patient" in text or "customer" in text:
        return "Goal: turn the list into replies, not just awareness."
    return "Goal: make it useful enough for the merchant to approve quickly."


def strongest_number_line(line: str, implication: str) -> str:
    if not implication:
        return line
    if len(line) > 145:
        source = line.split(":", 1)[0] if ":" in line else ""
        if "maps to your" in line.lower() and source:
            return f"{source}: {implication}"
        return implication
    return f"{line} {implication}"


def compact_reason_line(insight: dict[str, Any], strategy: str, trigger: dict[str, Any]) -> str:
    if strategy == "Performance Alert":
        line = "This matters because it hits incoming leads; this tends to recover performance fastest."
    elif strategy == "Growth Opportunity":
        line = "This matters because timing can turn attention into bookings."
    elif strategy == "Missed Customer Engagement":
        line = "This matters because the customer timing is already warm."
    else:
        line = "This matters because it gives you a relevant reason to re-engage."
    urgency = urgency_signal(trigger)
    if urgency:
        line += f" {urgency}"
    return line


def final_message_polish(
    message: str,
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None,
    insight: dict[str, Any],
) -> str:
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return message

    strategy = strategy_for(trigger, customer)
    tone = tone_for(strategy, trigger)
    salutation = first_name(merchant, category)
    memory = recent_memory(merchant)
    implication = surprise_implication(insight, merchant, category)
    variant = stable_variant("polish", merchant.get("merchant_id"), trigger.get("id"), insight.get("insight"))

    hook_bank = {
        "urgent": [
            f"{salutation}, this is the number I would act on today:",
            f"{salutation}, quick alert - this can quietly cost you leads:",
            f"{salutation}, one metric needs attention now:",
        ],
        "opportunity": [
            f"{salutation}, there is a small window to capture here:",
            f"{salutation}, this is the upside I would move on:",
            f"{salutation}, one opportunity is already showing up:",
        ],
        "warm": [
            f"{salutation}, one customer follow-up is ready now:",
            f"{salutation}, this is a timely customer moment:",
            f"{salutation}, one easy customer win is sitting open:",
        ],
        "curious": [
            f"{salutation}, this stood out because it is actionable:",
            f"{salutation}, quick insight - this is not just trivia:",
            f"{salutation}, one useful signal from the data:",
        ],
    }
    hook = hook_bank.get(tone, hook_bank["curious"])[variant % 3]

    memory_line = ""
    if memory and len(memory) <= 90 and memory_is_relevant(memory, insight):
        memory_line = f"Last time you said: \"{memory}\" - this connects directly."

    insight_line = lines[1] if len(lines) > 1 else lines[0]
    benchmark = safe_text(insight.get("benchmark"))
    if benchmark and benchmark in insight_line:
        insight_line = insight_line.replace(f" ({benchmark})", "")
    insight_line = strongest_number_line(insight_line, implication)
    action_line = safe_text(insight.get("action")) or (lines[2] if len(lines) > 2 else "")
    outcome = outcome_visualization(insight, strategy)
    cta = natural_cta(strategy, tone, variant).replace("Should I", "Want me to")

    if memory_line:
        final_lines = [hook, memory_line, insight_line, f"{action_line}. {cta}"]
    else:
        reason = compact_reason_line(insight, strategy, trigger)
        final_lines = [hook, insight_line, reason, f"{action_line}. {outcome} {cta}"]

    cleaned = []
    seen = set()
    for line in final_lines:
        line = re.sub(r"\s+", " ", line).strip()
        line = line.replace("..", ".")
        if line and line not in seen:
            cleaned.append(line)
            seen.add(line)
    return "\n".join(cleaned[:4])


GENERIC_PATTERNS = [
    "improve your business",
    "grow your business",
    "increase sales",
    "boost visibility",
    "dear merchant",
]


def quality_issues(message: str) -> list[str]:
    issues: list[str] = []
    lower = message.lower()
    lines = [line for line in message.splitlines() if line.strip()]
    if not re.search(r"\d", message):
        issues.append("missing_number")
    if any(pattern in lower for pattern in GENERIC_PATTERNS):
        issues.append("generic_phrase")
    if len(lines) > 4:
        issues.append("too_many_lines")
    if not re.search(r"\b(want|should|reply|confirm|draft|prepare|approve)\b", lower):
        issues.append("weak_cta")
    if message.count("?") > 1:
        issues.append("multiple_questions")
    return issues


def improve_message(message: str, insight: dict[str, Any], strategy: str) -> str:
    lines = [line.strip() for line in message.splitlines() if line.strip()][:4]
    if not re.search(r"\d", "\n".join(lines)) and insight.get("benchmark"):
        lines.insert(1, safe_text(insight["benchmark"]))
    if not any(re.search(r"\b(want|should|reply|confirm|draft|prepare|approve)\b", line.lower()) for line in lines):
        tone = "urgent" if strategy == "Performance Alert" else "opportunity"
        lines[-1:] = [natural_cta(strategy, tone, 0)]
    return "\n".join(lines[:4])


def intelligent_message(
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    insights = generate_insights(category, merchant, trigger, customer)
    ranked = sorted(insights, key=impact_score, reverse=True)
    best = ranked[0]
    message = render_message(category, merchant, trigger, customer, best)
    message = final_message_polish(message, category, merchant, trigger, customer, best)
    strategy = strategy_for(trigger, customer)
    issues = quality_issues(message)
    if issues:
        message = improve_message(message, best, strategy)
        issues = quality_issues(message)
    metadata = {
        "strategy": strategy,
        "tone": tone_for(strategy, trigger),
        "insight_kind": best.get("kind"),
        "insight_score": impact_score(best),
        "quality_issues": issues,
        "candidate_count": len(ranked),
    }
    return message, metadata
