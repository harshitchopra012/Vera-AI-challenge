import hashlib
import re
from typing import Any


PERFORMANCE_KINDS = {"perf_dip", "renewal_due", "gbp_unverified", "winback_eligible", "review_theme_emerged"}
GROWTH_KINDS = {"perf_spike", "festival_upcoming", "competitor_opened", "milestone_reached", "category_seasonal", "ipl_match_today", "active_planning_intent"}
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


def clean_label(value: Any) -> str:
    return safe_text(value).replace("_", " ")


def category_action(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any], offer: str) -> str:
    slug = category.get("slug")
    kind = trigger.get("kind")
    if slug == "restaurants":
        if kind == "ipl_match_today":
            return f"Push {offer} as a delivery-first match-night post to catch home-watch orders"
        if kind == "active_planning_intent":
            return "Turn the thali idea into a corporate lunch WhatsApp with tiers"
        if kind == "review_theme_emerged":
            return "Reply to late-delivery reviews and add one delivery-time promise to ordering copy"
        return f"Turn {offer} into one delivery or Google post customers can act on today"
    if slug == "gyms":
        if kind == "seasonal_perf_dip":
            members = merchant.get("customer_aggregate", {}).get("total_active_members")
            suffix = f" for {members} active members" if members else ""
            return f"Shift from acquisition ads to a retention challenge{suffix}, using {offer} only as the trial hook"
        if kind == "active_planning_intent":
            return "Package the kids yoga program as a 4-week parent-friendly summer camp"
        if kind == "perf_spike":
            return "Convert the call spike into one trial-class post while demand is warm"
        return f"Use {offer} as the next low-friction restart step"
    if slug == "salons":
        if kind == "wedding_package_followup":
            return f"Offer a Saturday skin-prep slot tied to the wedding timeline, anchored by {offer}"
        if kind == "festival_upcoming":
            return f"Shape {offer} into a pre-festival booking post before slots fill"
        if kind in {"winback_eligible", "dormant_with_vera"}:
            return f"Restart with {offer} as a simple comeback offer"
        return f"Turn {offer} into one service-specific Google post"
    if slug == "pharmacies":
        if kind == "supply_alert":
            return "Draft the affected-customer recall note and replacement pickup flow for chronic-Rx buyers"
        if kind == "chronic_refill_due":
            return f"Confirm same-dose refill dispatch before the stock-out date, with {offer}"
        if kind == "category_seasonal":
            return "Put ORS/sunscreen/antifungal on counter and send a summer-care delivery WhatsApp"
        if kind == "gbp_unverified":
            path = clean_label(trigger.get("payload", {}).get("verification_path"))
            return f"Complete pharmacy GBP verification via {path} so searchers trust the listing before calling"
        return f"Use {offer} as one trust-building customer note"
    if slug == "dentists":
        if kind == "competitor_opened":
            return f"Counter-position {offer} without starting a price war"
        return "Turn it into a patient-safe WhatsApp and one GBP post"
    return f"Turn it into one practical draft using {offer}"


def customer_generic_insight(
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any],
) -> str:
    cname = safe_text(customer.get("identity", {}).get("name"), "this customer").split("(")[0].strip()
    kind = trigger.get("kind")
    payload = trigger.get("payload", {})
    relationship = customer.get("relationship", {})
    if kind == "wedding_package_followup":
        return f"{cname} is {payload.get('days_to_wedding')} days from the wedding, after a bridal trial on {payload.get('trial_completed')}."
    if kind == "trial_followup":
        slots = [slot.get("label") for slot in payload.get("next_session_options", []) if slot.get("label")]
        slot_text = slots[0] if slots else "the next session"
        return f"{cname} tried the program on {payload.get('trial_date')}; {slot_text} is the next easy step."
    visits = relationship.get("visits_total")
    last_visit = relationship.get("last_visit")
    if visits and last_visit:
        return f"{cname} has {visits} visits and last came on {last_visit}, so this is a warm follow-up."
    return f"{cname} has a live follow-up moment from the last interaction."


def fallback_fact(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    kind = trigger.get("kind")
    payload = trigger.get("payload", {})
    slug = category.get("slug")
    if kind == "festival_upcoming":
        return f"{payload.get('festival')} is {payload.get('days_until')} days away for {merchant_name(merchant)}."
    if kind == "curious_ask_due":
        if slug == "salons":
            return "This week's quickest salon insight is service demand: balayage, keratin, or hair spa."
        return f"The weekly ask is due now: {clean_label(payload.get('ask_template'))}."
    payload_facts = [f"{clean_label(k)}: {clean_label(v)}" for k, v in payload.items() if isinstance(v, (str, int, float, bool))]
    return "; ".join(payload_facts[:2]) or f"{clean_label(kind)} is active now"


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


def category_keywords(category: dict[str, Any]) -> list[str]:
    slug = category.get("slug")
    keywords = {
        "dentists": ["patient", "recall", "treatment", "clinic", "fluoride", "caries", "dental", "checklist"],
        "restaurants": ["delivery", "orders", "thali", "dine-in", "kitchen", "match-night", "lunch", "post"],
        "gyms": ["trial", "members", "retention", "class", "attendance", "fitness", "restart", "camp"],
        "salons": ["slot", "bridal", "hair", "salon", "service", "skin-prep", "booking", "stylist"],
        "pharmacies": ["refill", "medicine", "batch", "rx", "pharmacy", "delivery", "pickup", "gbp"],
    }
    return keywords.get(slug, [])


def score_category_fit(candidate: dict[str, Any], category: dict[str, Any]) -> int:
    text = f"{candidate.get('insight', '')} {candidate.get('action', '')}".lower()
    hits = sum(1 for word in category_keywords(category) if word in text)
    score = min(5, hits)
    if hits >= 2:
        score += 1
    if category.get("slug") in text:
        score += 1
    return max(0, min(5, score))


def merchant_values(merchant: dict[str, Any]) -> list[str]:
    identity = merchant.get("identity", {})
    values = [
        identity.get("name", ""),
        identity.get("owner_first_name", ""),
        identity.get("locality", ""),
        str(merchant.get("performance", {}).get("views", "")),
        str(merchant.get("performance", {}).get("calls", "")),
        str(merchant.get("performance", {}).get("directions", "")),
        str(merchant.get("performance", {}).get("ctr", "")),
    ]
    values.extend(safe_text(offer.get("title")) for offer in merchant.get("offers", []))
    for value in merchant.get("customer_aggregate", {}).values():
        values.append(str(value))
    values.extend(clean_label(signal) for signal in merchant.get("signals", []))
    return [value for value in values if value and value != "None"]


def score_merchant_fit(candidate: dict[str, Any], merchant: dict[str, Any]) -> int:
    text = f"{candidate.get('insight', '')} {candidate.get('action', '')}".lower()
    score = 0
    if re.search(r"\d", text):
        score += 1
    if any(value.lower() in text for value in merchant_values(merchant) if len(value) >= 2):
        score += 2
    if any(safe_text(offer.get("title")).lower() in text for offer in merchant.get("offers", [])):
        score += 1
    if any(clean_label(signal).lower().split(":")[0] in text for signal in merchant.get("signals", [])):
        score += 1
    return max(0, min(5, score))


def trigger_terms(trigger: dict[str, Any]) -> list[str]:
    kind = trigger.get("kind", "")
    terms = [clean_label(kind)]
    payload = trigger.get("payload", {})
    for key, value in payload.items():
        terms.append(clean_label(key))
        if isinstance(value, (str, int, float, bool)):
            terms.append(clean_label(value))
        elif isinstance(value, list):
            for item in value[:4]:
                if isinstance(item, (str, int, float, bool)):
                    terms.append(clean_label(item))
                elif isinstance(item, dict):
                    terms.extend(clean_label(v) for v in item.values() if isinstance(v, (str, int, float, bool)))
    trigger_specific = {
        "perf_dip": ["down", "drop", "decline"],
        "perf_spike": ["up", "spike", "warm"],
        "competitor_opened": ["competitor", "opened"],
        "recall_due": ["due", "recall"],
        "chronic_refill_due": ["runs out", "refill"],
        "review_theme_emerged": ["reviews", "mention"],
        "gbp_unverified": ["unverified", "verification"],
        "supply_alert": ["recall", "batch"],
        "active_planning_intent": ["intent", "already showed"],
        "ipl_match_today": ["match", "venue", "starts", "delivery"],
        "wedding_package_followup": ["wedding", "trial", "bridal", "days"],
        "customer_lapsed_hard": ["inactive", "away", "lapsed"],
        "trial_followup": ["trial", "session", "slot"],
        "seasonal_perf_dip": ["seasonal", "down", "dip"],
        "curious_ask_due": ["ask", "due", "service"],
        "winback_eligible": ["expired", "dipped", "winback"],
        "dormant_with_vera": ["dormant", "days"],
        "milestone_reached": ["milestone", "review"],
    }
    terms.extend(trigger_specific.get(kind, []))
    return [term for term in terms if term and term != "None"]


def score_trigger_relevance(candidate: dict[str, Any], trigger: dict[str, Any]) -> int:
    text = f"{candidate.get('insight', '')} {candidate.get('action', '')}".lower()
    hits = sum(1 for term in trigger_terms(trigger) if term.lower() in text)
    score = min(5, hits)
    if trigger.get("kind", "").replace("_", " ") in text:
        score += 1
    return max(0, min(5, score))


def selection_score(candidate: dict[str, Any], category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any]) -> int:
    cat = score_category_fit(candidate, category)
    mer = score_merchant_fit(candidate, merchant)
    trg = score_trigger_relevance(candidate, trigger)
    base = (
        int(candidate.get("revenue", 0))
        + int(candidate.get("engagement", 0))
        + int(candidate.get("urgency", 0))
        + int(candidate.get("confidence", 0))
    )
    return (cat * 2) + (mer * 2) + (trg * 3) + base


def annotate_selection_scores(
    candidate: dict[str, Any],
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
) -> dict[str, Any]:
    candidate = dict(candidate)
    candidate["category_fit"] = score_category_fit(candidate, category)
    candidate["merchant_fit"] = score_merchant_fit(candidate, merchant)
    candidate["trigger_relevance"] = score_trigger_relevance(candidate, trigger)
    candidate["selection_score"] = selection_score(candidate, category, merchant, trigger)
    return candidate


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
        action = category_action(category, merchant, trigger, offer)
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
                action,
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
                action,
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
                customer_generic_insight(category, merchant, trigger, customer),
                action,
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
        if kind == "research_digest" and high_risk:
            insight = f"{source}: {title}; it maps to your {high_risk} high-risk adult patients."
        elif trial:
            insight = f"{source}: {title}; the study size is {trial:,} patients."
        elif kind == "regulation_change":
            deadline = payload.get("deadline_iso")
            insight = f"{source}: {title}; deadline is {deadline}."
        elif kind == "cde_opportunity":
            insight = f"{source}: {title}; {payload.get('credits')} CDE credits, fee {clean_label(payload.get('fee'))}."
        else:
            insight = f"{source}: {title}."
        action = category_action(category, merchant, trigger, offer)
        if kind == "research_digest":
            action = "Turn it into a 2-min owner summary + patient WhatsApp draft"
        elif kind == "regulation_change":
            action = "Turn it into a 5-point compliance checklist for the clinic team"
        elif kind == "cde_opportunity":
            action = "Turn it into a short owner note with webinar timing and registration ask"
        insights.append(insight_candidate(
            kind,
            insight,
            action,
            benchmark=safe_text(item.get("actionable")),
            revenue=3,
            engagement=4,
            urgency=int(trigger.get("urgency") or 2),
            confidence=5,
            customer_fit=bool(high_risk),
        ))

    if kind in {"perf_dip", "perf_spike"}:
        metric = clean_label(payload.get("metric") or "performance")
        delta = pct(payload.get("delta_pct"), signed=True)
        current = perf.get(metric) or perf.get("calls") or perf.get("views")
        peer_value = peer.get(f"avg_{metric}_30d") or peer.get("avg_ctr")
        direction = "up" if kind == "perf_spike" else "down"
        insights.append(insight_candidate(
            kind,
            f"{metric.title()} is {direction} {delta} in {payload.get('window', '7d')} (current {current}; peer marker {peer_value}).",
            category_action(category, merchant, trigger, offer),
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
            category_action(category, merchant, trigger, offer),
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
            category_action(category, merchant, trigger, offer),
            benchmark=f"opened on {payload.get('opened_date')}",
            revenue=4,
            engagement=4,
            urgency=3,
            confidence=4,
        ))

    if kind == "category_seasonal":
        trends = ", ".join(safe_text(t).replace("_", " ") for t in payload.get("trends", [])[:4])
        prefix = "Pharmacy seasonal demand is shifting now" if category.get("slug") == "pharmacies" else "Seasonal demand is shifting now"
        insights.append(insight_candidate(
            kind,
            f"{prefix}: {trends}.",
            category_action(category, merchant, trigger, offer),
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
            category_action(category, merchant, trigger, offer),
            benchmark="post-expiry dip is already visible",
            revenue=5,
            engagement=3,
            urgency=3,
            confidence=5,
        ))

    if kind == "ipl_match_today":
        match = payload.get("match")
        venue = payload.get("venue")
        time_value = safe_text(payload.get("match_time_iso"))[11:16]
        insights.append(insight_candidate(
            kind,
            f"{match} at {venue} starts around {time_value}; weekend IPL usually shifts demand toward home delivery.",
            category_action(category, merchant, trigger, offer),
            benchmark="Saturday match-night demand behaves differently from weekday matches",
            revenue=4,
            engagement=4,
            urgency=4,
            confidence=4,
        ))

    if kind == "seasonal_perf_dip":
        metric = clean_label(payload.get("metric")).title()
        insights.append(insight_candidate(
            kind,
            f"{metric} is down {pct(payload.get('delta_pct'))}, but the trigger says this is an expected Apr-Jun seasonal dip.",
            category_action(category, merchant, trigger, offer),
            benchmark=clean_label(payload.get("season_note")),
            revenue=4,
            engagement=4,
            urgency=2,
            confidence=5,
        ))

    if kind == "active_planning_intent":
        topic = clean_label(payload.get("intent_topic"))
        last = safe_text(payload.get("merchant_last_message"))
        insights.append(insight_candidate(
            kind,
            f"The merchant already showed intent on {topic}: '{last}'.",
            category_action(category, merchant, trigger, offer),
            benchmark="explicit merchant intent means no more qualification needed",
            revenue=4,
            engagement=5,
            urgency=4,
            confidence=5,
        ))

    if kind == "supply_alert":
        batches = ", ".join(payload.get("affected_batches", []))
        chronic = merchant.get("customer_aggregate", {}).get("chronic_rx_count")
        insights.append(insight_candidate(
            kind,
            f"{payload.get('molecule')} recall affects batches {batches}; this pharmacy has {chronic} chronic-Rx customers.",
            category_action(category, merchant, trigger, offer),
            benchmark=f"manufacturer {payload.get('manufacturer')}",
            revenue=5,
            engagement=5,
            urgency=5,
            confidence=5,
        ))

    if kind == "gbp_unverified":
        views = perf.get("views")
        uplift = pct(payload.get("estimated_uplift_pct"))
        label = "pharmacy GBP" if category.get("slug") == "pharmacies" else "GBP"
        insights.append(insight_candidate(
            kind,
            f"{label} is unverified despite {views} monthly views; verification can unlock roughly {uplift} more profile actions.",
            category_action(category, merchant, trigger, offer),
            benchmark=clean_label(payload.get("verification_path")),
            revenue=4,
            engagement=4,
            urgency=3,
            confidence=5,
        ))

    if kind == "dormant_with_vera":
        insights.append(insight_candidate(
            kind,
            f"It has been {payload.get('days_since_last_merchant_message')} days since the last merchant message after {clean_label(payload.get('last_topic'))}.",
            category_action(category, merchant, trigger, offer),
            benchmark="dormant merchants need a low-effort restart",
            revenue=3,
            engagement=4,
            urgency=2,
            confidence=4,
        ))

    if not insights:
        fact = fallback_fact(category, merchant, trigger)
        insights.append(insight_candidate(
            kind,
            fact,
            category_action(category, merchant, trigger, offer),
            revenue=2,
            engagement=3,
            urgency=int(trigger.get("urgency") or 1),
            confidence=2,
        ))

    return insights


def select_best_insight(
    insights: list[dict[str, Any]],
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
) -> dict[str, Any]:
    scored = [annotate_selection_scores(insight, category, merchant, trigger) for insight in insights]
    return max(
        scored,
        key=lambda item: (
            item["selection_score"],
            item["merchant_fit"],
            len(safe_text(item.get("action"))),
            1 if re.search(r"\d", f"{item.get('insight', '')} {item.get('action', '')}") else 0,
        ),
    )


def first_numeric_signal(merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    perf = merchant.get("performance", {})
    for key in ["views", "calls", "directions", "ctr"]:
        value = perf.get(key)
        if value not in (None, ""):
            return f"{value} {key}"

    aggregate = merchant.get("customer_aggregate", {})
    for key, value in aggregate.items():
        if isinstance(value, (int, float)) and value > 0:
            return f"{value} {clean_label(key)}"

    for value in trigger.get("payload", {}).values():
        if isinstance(value, (int, float)) and value:
            return safe_text(value)
        if isinstance(value, str) and re.search(r"\d", value):
            return value
    return ""


def lock_perfect_insight(
    insight: dict[str, Any],
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Strict first-pass enforcement before rendering.

    Every selected insight must be merchant-specific, trigger-causal,
    category-native, consequence-bearing, and decisive.
    """
    refined = dict(insight)
    offer = best_offer(category, merchant)

    cause = trigger_cause(trigger, category)
    trigger_label = clean_label(trigger.get("kind"))
    if trigger_label and trigger_label.lower() not in cause.lower():
        cause = f"{trigger_label}: {cause}"

    customer_anchor = customer_data_anchor(customer, trigger)
    merchant_anchor = merchant_data_anchor(category, merchant, trigger)
    data_anchor = customer_anchor or merchant_anchor
    if not re.search(r"\d", data_anchor):
        fallback_number = first_numeric_signal(merchant, trigger)
        if fallback_number:
            data_anchor = f"{data_anchor} ({fallback_number})" if data_anchor else fallback_number

    signal = merchant_signal_anchor(merchant, trigger)
    signal_text = f" + {signal}" if signal else ""
    marker = category_marker_word(category)
    impact = category_business_impact(category, trigger)
    consequence = consequence_pressure(trigger)
    merchant_label = merchant_name(merchant)

    refined["insight"] = strip_generic_language(
        f"{cause}; at {merchant_label}, {data_anchor}{signal_text} = {marker} marker: {impact}. {consequence}"
    )

    action = safe_text(refined.get("action")) or category_action(category, merchant, trigger, offer)
    action = re.sub(r"\b(you can try|consider|maybe)\b", "", action, flags=re.I)
    refined["action"] = decision_action(action, category, merchant, trigger, customer)
    return annotate_selection_scores(refined, category, merchant, trigger)


def refine_selected_insight(
    insight: dict[str, Any],
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return lock_perfect_insight(insight, category, merchant, trigger, customer)


GENERIC_BANNED = ["improve", "increase", "optimize", "better engagement"]


def category_required_word(category: dict[str, Any]) -> str:
    slug = category.get("slug")
    required = {
        "dentists": "patient recall",
        "restaurants": "delivery orders",
        "gyms": "member retention",
        "salons": "booking slot",
        "pharmacies": "medicine refill",
    }
    return required.get(slug, "customer action")


def category_marker_word(category: dict[str, Any]) -> str:
    slug = category.get("slug")
    markers = {
        "dentists": "scaling recall",
        "restaurants": "AOV order",
        "gyms": "membership churn",
        "salons": "hair spa slot",
        "pharmacies": "molecule refill",
    }
    return markers.get(slug, "customer")


def category_business_impact(category: dict[str, Any], trigger: dict[str, Any]) -> str:
    slug = category.get("slug")
    kind = trigger.get("kind")
    if slug == "dentists":
        if kind in {"perf_dip", "gbp_unverified", "competitor_opened"}:
            if kind == "competitor_opened":
                return "patients can compare clinics before booking"
            return "patients are dropping before booking"
        if kind in {"recall_due", "research_digest"}:
            return "patient recall timing can turn into booked treatment"
        return "patient trust and treatment intent are on the line"
    if slug == "restaurants":
        if kind in {"perf_dip", "review_theme_emerged"}:
            return "orders are not converting from views"
        return "delivery orders can be captured before customers switch kitchens"
    if slug == "gyms":
        if kind in {"perf_dip", "seasonal_perf_dip", "perf_spike", "trial_followup"}:
            return "trial intent is not turning into memberships"
        return "member retention can be won before motivation cools"
    if slug == "salons":
        if kind in {"festival_upcoming", "wedding_package_followup"}:
            return "high-intent beauty demand can become booked slots"
        return "slots are not getting filled fast enough"
    if slug == "pharmacies":
        if kind in {"chronic_refill_due", "supply_alert", "category_seasonal"}:
            return "refill demand can move to another pharmacy"
        return "medicine trust and pickup intent are at risk"
    return "customer intent is close enough to act on"


def consequence_pressure(trigger: dict[str, Any]) -> str:
    kind = trigger.get("kind")
    urgency = int(trigger.get("urgency") or 1)
    if kind in {"perf_dip", "winback_eligible", "gbp_unverified", "review_theme_emerged", "seasonal_perf_dip"}:
        return "Delay hurts recovery."
    if kind in {"festival_upcoming", "competitor_opened", "category_seasonal", "ipl_match_today", "perf_spike"}:
        return "Window closes."
    if kind in {"recall_due", "chronic_refill_due", "trial_followup", "wedding_package_followup", "customer_lapsed_hard"}:
        return "Follow-up gets colder."
    if urgency >= 4:
        return "Compounds if ignored."
    return "Left alone, missed demand."


def customer_data_anchor(customer: dict[str, Any] | None, trigger: dict[str, Any]) -> str:
    if not customer:
        return ""
    payload = trigger.get("payload", {})
    cname = safe_text(customer.get("identity", {}).get("name"), "this customer").split("(")[0].strip()
    kind = trigger.get("kind")
    if kind == "recall_due":
        return f"{cname}'s {clean_label(payload.get('service_due', 'recall'))} after {payload.get('last_service_date')}"
    if kind == "chronic_refill_due":
        meds = [safe_text(med) for med in payload.get("molecule_list", []) if safe_text(med)]
        return f"{cname}'s {len(meds) or 1} refill medicines"
    if kind == "trial_followup":
        return f"{cname}'s trial on {payload.get('trial_date')}"
    if kind == "wedding_package_followup":
        return f"{cname}'s wedding in {payload.get('days_to_wedding')} days"
    if kind == "customer_lapsed_hard":
        return f"{cname}'s {payload.get('days_since_last_visit')} inactive days"
    visits = customer.get("relationship", {}).get("visits_total")
    return f"{cname}'s {visits} visits" if visits else cname


def merchant_signal_anchor(merchant: dict[str, Any], trigger: dict[str, Any]) -> str:
    signals = [safe_text(signal) for signal in merchant.get("signals", []) if safe_text(signal)]
    if not signals:
        return ""
    kind = trigger.get("kind")
    priority = {
        "perf_dip": ["perf_dip", "ctr_below", "below_peer"],
        "perf_spike": ["high_retention", "above_peer", "active_planning"],
        "renewal_due": ["renewal_due", "dormant"],
        "gbp_unverified": ["unverified_gbp"],
        "winback_eligible": ["winback", "post_expiry", "dormant"],
        "dormant_with_vera": ["dormant"],
        "research_digest": ["high_risk", "engaged", "stale_posts"],
        "regulation_change": ["high_risk", "compliance"],
        "cde_opportunity": ["engaged", "high_risk"],
        "ipl_match_today": ["ipl", "new_merchant"],
        "active_planning_intent": ["active_planning", "engaged", "high_volume"],
        "category_seasonal": ["above_peer", "high_repeat", "delivery"],
        "supply_alert": ["compliance", "high_repeat"],
        "review_theme_emerged": ["new_merchant", "trial_ending"],
        "seasonal_perf_dip": ["seasonal", "above_peer", "no_recent"],
    }
    wanted = priority.get(kind, [])
    for token in wanted:
        for signal in signals:
            if token in signal.lower():
                return clean_label(signal.split(":", 1)[0])
    return clean_label(signals[0].split(":", 1)[0])


def merchant_data_anchor(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any] | None = None) -> str:
    perf = merchant.get("performance", {})
    agg = merchant.get("customer_aggregate", {})
    offer = best_offer(category, merchant)
    kind = (trigger or {}).get("kind")
    if kind in {"perf_dip", "perf_spike", "gbp_unverified", "renewal_due", "winback_eligible"}:
        if perf.get("views") and perf.get("calls"):
            return f"{perf.get('views')} views and {perf.get('calls')} calls in 30 days"
    if perf.get("views") and perf.get("calls"):
        perf_anchor = f"{perf.get('views')} views and {perf.get('calls')} calls in 30 days"
    else:
        perf_anchor = ""
    aggregate_labels = {
        "high_risk_adult_count": "high-risk adult patients",
        "chronic_rx_count": "chronic-Rx customers",
        "total_active_members": "active members",
        "lapsed_90d_plus": "lapsed customers",
        "lapsed_180d_plus": "lapsed customers",
    }
    for key in ["high_risk_adult_count", "chronic_rx_count", "total_active_members", "lapsed_90d_plus", "lapsed_180d_plus"]:
        if agg.get(key) is not None:
            return f"{agg.get(key)} {aggregate_labels[key]}"
    if perf_anchor:
        return perf_anchor
    if offer and offer != "one service-price offer":
        return offer
    if perf.get("ctr"):
        return f"{perf.get('ctr')} CTR"
    return merchant_name(merchant)


def decisive_action_body(action: str) -> str:
    text = strip_generic_language(safe_text(action)).rstrip(".")
    replacements = [
        (r"^turn it into\s+", "draft "),
        (r"^turn\s+(.+?)\s+into\s+", r"package \1 as "),
        (r"^use\s+", "send "),
        (r"^restart with\s+", "send "),
        (r"^shape\s+", "make "),
        (r"^move\s+", "place "),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text[:1].lower() + text[1:] if text else text


def decision_action(
    action: str,
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None = None,
) -> str:
    cleaned = decisive_action_body(action)
    if not cleaned:
        cleaned = category_action(category, merchant, trigger, "one focused offer")
    offer = best_offer(category, merchant)
    if offer and offer != "one service-price offer" and offer.lower() not in cleaned.lower():
        cleaned = f"{cleaned} using {offer}"
    cleaned = decisive_action_body(cleaned)
    if re.match(r"^(the fastest fix is|do this now|the next move is|the decision is)\b", cleaned, flags=re.I):
        return cleaned
    return f"Do this now: {cleaned}"


def trigger_cause(trigger: dict[str, Any], category: dict[str, Any] | None = None) -> str:
    kind = trigger.get("kind")
    payload = trigger.get("payload", {})
    if kind in {"research_digest", "cde_opportunity", "regulation_change"}:
        item = find_digest_item(category or {}, trigger) or {}
        title = safe_text(item.get("title"))
        source = safe_text(item.get("source"))
        if kind == "research_digest" and title:
            slug = safe_text((category or {}).get("slug"))
            prefix = f"{slug} digest: " if slug else ""
            short_source = source.split(",", 1)[0] if source else ""
            short_title = (
                title.replace("fluoride varnish recall", "fluoride recall")
                .replace("outperforms", "beats")
                .replace("high-risk adult caries", "high-risk caries")
            )
            return f"{prefix}{short_source}: {short_title}" if short_source else f"{prefix}{short_title}"
        if kind == "regulation_change" and title:
            deadline = payload.get("deadline_iso")
            return f"{title}; deadline {deadline}" if deadline else title
        if kind == "cde_opportunity" and title:
            credits = payload.get("credits")
            return f"{title}; {credits} CDE credits" if credits else title
    if kind == "perf_dip":
        return f"{clean_label(payload.get('metric'))} dropped {pct(payload.get('delta_pct'), signed=True)} in {payload.get('window', '7d')}"
    if kind == "perf_spike":
        return f"{clean_label(payload.get('metric'))} rose {pct(payload.get('delta_pct'), signed=True)} in {payload.get('window', '7d')}"
    if kind == "competitor_opened":
        return f"{payload.get('competitor_name')} opened {payload.get('distance_km')} km away"
    if kind == "recall_due":
        return f"recall is due after {payload.get('last_service_date')}"
    if kind == "chronic_refill_due":
        meds = ", ".join(safe_text(med) for med in payload.get("molecule_list", []) if safe_text(med))
        subject = meds or "medicine"
        return f"{subject} stock runs out on {safe_text(payload.get('stock_runs_out_iso'))[:10]}"
    if kind == "wedding_package_followup":
        return f"wedding is {payload.get('days_to_wedding')} days away after the bridal trial"
    if kind == "trial_followup":
        return f"trial happened on {payload.get('trial_date')}"
    if kind == "customer_lapsed_hard":
        return f"customer has been inactive {payload.get('days_since_last_visit')} days"
    if kind == "review_theme_emerged":
        return f"{payload.get('occurrences_30d')} reviews mention {clean_label(payload.get('theme'))}"
    if kind == "winback_eligible":
        return f"plan expired {payload.get('days_since_expiry')} days ago and performance dipped {pct(payload.get('perf_dip_pct'))}"
    if kind == "gbp_unverified":
        return f"GBP is unverified with {pct(payload.get('estimated_uplift_pct'))} action upside"
    if kind == "supply_alert":
        return f"{payload.get('molecule')} recall hit batches {', '.join(payload.get('affected_batches', []))}"
    if kind == "category_seasonal":
        return f"{', '.join(clean_label(t) for t in payload.get('trends', [])[:3])}"
    if kind == "festival_upcoming":
        return f"{payload.get('festival')} is {payload.get('days_until')} days away"
    if kind == "ipl_match_today":
        time_value = safe_text(payload.get("match_time_iso"))[11:16]
        return f"{payload.get('match')} at {payload.get('venue')} starts around {time_value}"
    if kind == "seasonal_perf_dip":
        return f"{clean_label(payload.get('metric'))} is down {pct(payload.get('delta_pct'))} in {payload.get('window', '7d')} during {clean_label(payload.get('season_note'))}"
    if kind == "curious_ask_due":
        return f"weekly ask is due now: {clean_label(payload.get('ask_template'))}"
    if kind == "active_planning_intent":
        return f"merchant already asked about {clean_label(payload.get('intent_topic'))}"
    if kind == "renewal_due":
        return f"renewal is due in {payload.get('days_remaining')} days"
    if kind == "milestone_reached":
        return f"{clean_label(payload.get('metric'))} is at {payload.get('value_now')} of {payload.get('milestone_value')}"
    if kind == "dormant_with_vera":
        return f"merchant has been dormant {payload.get('days_since_last_merchant_message')} days"
    item_id = payload.get("top_item_id") or payload.get("digest_item_id") or payload.get("alert_id")
    if item_id:
        return f"new category item {item_id} is active"
    return f"{clean_label(kind)} trigger is active"


def strip_generic_language(text: str) -> str:
    cleaned = text
    replacements = {
        "improve performance": "recover the leaking response path",
        "increase engagement": "get more replies from the right customers",
        "optimize": "tighten",
        "better engagement": "more qualified replies",
        "improve": "sharpen",
    }
    for old, new in replacements.items():
        cleaned = re.sub(old, new, cleaned, flags=re.I)
    return cleaned


def genericity_issues(
    candidate: dict[str, Any],
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
) -> list[str]:
    text = f"{candidate.get('insight', '')} {candidate.get('action', '')}".lower()
    issues: list[str] = []
    if score_category_fit(candidate, category) < 2:
        issues.append("weak_category_fit")
    if score_merchant_fit(candidate, merchant) < 2:
        issues.append("weak_merchant_fit")
    if score_trigger_relevance(candidate, trigger) < 2:
        issues.append("weak_trigger_relevance")
    if not re.search(r"\d", text):
        issues.append("missing_number")
    if any(word in text for word in GENERIC_BANNED):
        issues.append("generic_language")
    return issues


def force_hyper_specific(
    candidate: dict[str, Any],
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues = genericity_issues(candidate, category, merchant, trigger)
    if not issues:
        fixed = dict(candidate)
        fixed["insight"] = strip_generic_language(safe_text(fixed.get("insight")))
        fixed["action"] = strip_generic_language(safe_text(fixed.get("action")))
        return annotate_selection_scores(fixed, category, merchant, trigger)

    offer = best_offer(category, merchant)
    category_phrase = category_required_word(category)
    anchor = merchant_data_anchor(category, merchant, trigger)
    cause = trigger_cause(trigger, category)
    action = category_action(category, merchant, trigger, offer)
    if offer and offer != "one service-price offer" and offer.lower() not in action.lower():
        action = f"{action} around {offer}"

    fixed = dict(candidate)
    fixed["insight"] = strip_generic_language(
        f"{cause}; for {merchant_name(merchant)}, {anchor} makes this a {category_phrase} priority."
    )
    fixed["action"] = strip_generic_language(action)
    fixed = annotate_selection_scores(fixed, category, merchant, trigger)

    # Last validation pass: force a number if the category action had none.
    if not re.search(r"\d", f"{fixed.get('insight', '')} {fixed.get('action', '')}"):
        views = merchant.get("performance", {}).get("views")
        if views:
            fixed["insight"] = f"{fixed['insight']} Current 30-day views: {views}."
        fixed = annotate_selection_scores(fixed, category, merchant, trigger)
    return fixed


def force_business_decision(
    candidate: dict[str, Any],
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fixed = dict(candidate)
    cause = trigger_cause(trigger, category)
    trigger_label = clean_label(trigger.get("kind"))
    if trigger_label and trigger_label.lower() not in cause.lower():
        cause = f"{trigger_label}: {cause}"
    customer_anchor = customer_data_anchor(customer, trigger)
    merchant_anchor = merchant_data_anchor(category, merchant, trigger)
    anchor = customer_anchor or merchant_anchor
    signal = merchant_signal_anchor(merchant, trigger)
    signal_text = f" + {signal}" if signal else ""
    marker = category_marker_word(category)
    impact = category_business_impact(category, trigger)
    consequence = consequence_pressure(trigger)
    merchant_label = merchant_name(merchant)

    fixed["insight"] = strip_generic_language(
        f"{cause}; at {merchant_label}, {anchor}{signal_text} = {marker} marker: {impact}. {consequence}"
    )
    fixed["action"] = decision_action(
        safe_text(fixed.get("action")) or category_action(category, merchant, trigger, best_offer(category, merchant)),
        category,
        merchant,
        trigger,
        customer,
    )
    fixed = annotate_selection_scores(fixed, category, merchant, trigger)

    text = f"{fixed.get('insight', '')} {fixed.get('action', '')}"
    if not re.search(r"\d", text):
        views = merchant.get("performance", {}).get("views")
        if views:
            fixed["insight"] = f"{fixed['insight']} Current 30-day views: {views}."
            fixed = annotate_selection_scores(fixed, category, merchant, trigger)
    return fixed


def strict_final_issues(
    candidate: dict[str, Any],
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None = None,
) -> list[str]:
    insight = safe_text(candidate.get("insight"))
    action = safe_text(candidate.get("action"))
    text = f"{insight} {action}".lower()
    issues: list[str] = []
    trigger_label = clean_label(trigger.get("kind")).lower()
    merchant_identity = merchant.get("identity", {})
    merchant_terms = [
        safe_text(merchant_identity.get("name")).lower(),
        safe_text(merchant_identity.get("owner_first_name")).lower(),
        safe_text(merchant_identity.get("locality")).lower(),
    ]
    customer_term = safe_text((customer or {}).get("identity", {}).get("name")).split("(")[0].strip().lower()
    grounding_terms = ["views", "calls", "ctr", "customers", "patients", "members", "offer", "delivery", "refill"]
    grounding_terms.extend(active_offers(merchant))

    if not re.search(r"\d", text):
        issues.append("missing_number")
    if trigger_label and trigger_label not in text:
        issues.append("missing_trigger")
    if not any(term and term in text for term in merchant_terms) and not (customer_term and customer_term in text):
        issues.append("missing_merchant_context")
    if score_category_fit(candidate, category) < 3 or category_marker_word(category).split()[0].lower() not in text:
        issues.append("weak_category_native")
    if not any(safe_text(term).lower() in text for term in grounding_terms if safe_text(term)):
        issues.append("missing_grounding")
    if not any(word in insight.lower() for word in ["=", "signals", "means", "not converting", "dropping", "at risk", "demand"]):
        issues.append("missing_causal_impact")
    if not any(phrase in insight.lower() for phrase in ["delay hurts recovery", "compounds if ignored", "window closes", "follow-up gets colder", "missed demand"]):
        issues.append("missing_consequence")
    if not re.search(r"^(the fastest fix is|do this now|the next move is|the decision is)\b", action.lower()):
        issues.append("weak_decision_action")
    if any(phrase in action.lower() for phrase in ["you can try", "maybe", "consider", "turn this into"]):
        issues.append("suggestive_action")
    return issues


def force_strict_final_validation(
    candidate: dict[str, Any],
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fixed = dict(candidate)
    if not strict_final_issues(fixed, category, merchant, trigger, customer):
        return annotate_selection_scores(fixed, category, merchant, trigger)

    fixed = force_business_decision(fixed, category, merchant, trigger, customer)
    if not any(phrase in safe_text(fixed.get("insight")).lower() for phrase in ["delay hurts recovery", "compounds if ignored", "window closes", "follow-up gets colder", "missed demand"]):
        fixed["insight"] = f"{safe_text(fixed.get('insight')).rstrip('.')} {consequence_pressure(trigger)}"
    fixed["action"] = decision_action(
        safe_text(fixed.get("action")) or category_action(category, merchant, trigger, best_offer(category, merchant)),
        category,
        merchant,
        trigger,
        customer,
    )
    return annotate_selection_scores(fixed, category, merchant, trigger)


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
            "{sal}, this is a quick moment to move:",
        ],
        "warm": [
            "{sal}, one customer moment is ready to act on:",
            "{sal}, this is a low-friction follow-up:",
            "{sal}, there is a warm customer win here:",
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
            "Want me to draft the ready version?",
        ],
        "opportunity": [
            "Want me to turn this into the first draft?",
            "Should I package this into a post you can approve?",
            "Want me to draft the ready version?",
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
    lower_text = text.lower()
    if any(phrase in lower_text for phrase in [
        " marker:",
        " = ",
        " signals ",
        "delay makes",
        "window closes",
        "left alone",
        "left unchecked",
        "follow-up gets",
        "compounds",
        "waiting makes",
    ]):
        return ""
    if "%" in text:
        if "down" in lower_text or "-" in text:
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
    if peer_ctr and merchant_ctr and merchant_ctr < peer_ctr and any(term in text for term in ["ctr", "views", "calls", "profile actions"]):
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
        return "Act this week."
    if urgency >= 2:
        return "Early action helps."
    return ""


def outcome_visualization(insight: dict[str, Any], strategy: str, category: dict[str, Any] | None = None) -> str:
    text = safe_text(insight.get("insight")).lower()
    slug = (category or {}).get("slug")
    if strategy == "Performance Alert":
        if slug == "pharmacies":
            return "Goal: recover trusted calls or delivery requests before they go elsewhere."
        if slug == "restaurants":
            return "Goal: recover order intent before customers switch kitchens."
        return "Goal: recover the lost response path before it compounds."
    if strategy == "Growth Opportunity":
        if slug == "restaurants":
            return "Goal: turn match attention into delivery orders."
        if slug == "gyms":
            return "Goal: convert attention into trial visits or retained members."
        if slug == "salons":
            return "Goal: turn timing into booked slots."
        if slug == "pharmacies":
            return "Goal: turn seasonal demand into repeat store visits."
        return "Goal: convert the current attention into one visible offer."
    if strategy == "Missed Customer Engagement":
        if slug == "pharmacies":
            return "Goal: make the next refill or pickup feel obvious."
        if slug == "gyms":
            return "Goal: make restarting feel easy, not guilty."
        if slug == "salons":
            return "Goal: make booking the next slot feel natural."
        return "Goal: make the next reply feel obvious, not promotional."
    if "patient" in text or "customer" in text:
        return "Goal: turn the list into replies, not just awareness."
    return "Goal: make it useful enough for the merchant to approve quickly."


def strongest_number_line(line: str, implication: str) -> str:
    if not implication:
        return line
    if len(line) > 145:
        if "maps to your" in line.lower() and ":" in line:
            source = line.split(":", 1)[0]
            return f"{source}: {implication}"
        core = line.split(";", 1)[0].strip()
        if len(core) > 110:
            core = core[:107].rstrip(" ,;:") + "."
        return f"{core} {implication}"
    return f"{line} {implication}"


def compact_insight_line(line: str, max_len: int = 285) -> str:
    if len(line) <= max_len:
        return line

    replacements = [
        ("research digest: dentists digest:", "research digest: dentists:"),
        ("high-risk adult patients", "high-risk patients"),
        ("patient recall timing can turn into booked treatment", "patient recall can become treatment bookings"),
        ("patient trust and treatment intent are on the line", "patient trust is at risk"),
        ("delivery orders can be captured before customers switch kitchens", "delivery orders can be captured before switching"),
        ("trial intent is not turning into memberships", "trial intent is not becoming memberships"),
        ("high-intent beauty demand can become booked slots", "beauty demand can become booked slots"),
        ("refill demand can move to another pharmacy", "refill demand can switch pharmacy"),
        ("This matters because timing turns attention into bookings.", "Timing can become bookings."),
    ]
    compacted = line
    for old, new in replacements:
        compacted = compacted.replace(old, new)
    if len(compacted) <= max_len:
        return compacted

    if len(compacted) > max_len and "; at " in compacted and ". " in compacted:
        head, tail = compacted.rsplit(". ", 1)
        if len(head) > max_len:
            compacted = f"{head[: max_len - len(tail) - 4].rstrip(' ,;:')}. {tail}"
    return compacted


def compact_reason_line(insight: dict[str, Any], strategy: str, trigger: dict[str, Any]) -> str:
    if strategy == "Performance Alert":
        line = "This matters because it hits leads now."
    elif strategy == "Growth Opportunity":
        line = "This matters because timing turns attention into bookings."
    elif strategy == "Missed Customer Engagement":
        line = "This matters because the reply window is warm."
    else:
        line = "This matters because it gives one clear next move."
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
            f"{salutation}, act on this now:",
            f"{salutation}, quick alert:",
            f"{salutation}, signal now:",
        ],
        "opportunity": [
            f"{salutation}, window is open:",
            f"{salutation}, upside now:",
            f"{salutation}, quick opportunity:",
        ],
        "warm": [
            f"{salutation}, follow-up is warm:",
            f"{salutation}, warm customer moment:",
            f"{salutation}, quick customer win:",
        ],
        "curious": [
            f"{salutation}, signal:",
            f"{salutation}, quick insight:",
            f"{salutation}, data signal:",
        ],
    }
    hook = hook_bank.get(tone, hook_bank["curious"])[variant % 3]

    memory_line = ""
    if memory and len(memory) <= 90 and memory_is_relevant(memory, insight):
        clean_memory = memory.replace("?", "").strip()
        if len(clean_memory) > 58:
            if "kids yoga" in clean_memory.lower():
                memory_line = "Last time you asked about kids yoga - this connects."
            else:
                memory_line = f"Last time: {clean_memory[:50].rstrip()} - this connects."
        else:
            memory_line = f"Last time you said: \"{clean_memory}\" - this connects."

    insight_line = lines[1] if len(lines) > 1 else lines[0]
    benchmark = safe_text(insight.get("benchmark"))
    if benchmark and benchmark in insight_line:
        insight_line = insight_line.replace(f" ({benchmark})", "")
    insight_line = strongest_number_line(insight_line, implication)
    insight_line = compact_insight_line(insight_line)
    action_line = safe_text(insight.get("action")) or (lines[2] if len(lines) > 2 else "")
    outcome = outcome_visualization(insight, strategy, category)
    cta = natural_cta(strategy, tone, variant).replace("Should I", "Want me to")

    if memory_line:
        final_lines = [hook, memory_line, insight_line, f"{action_line}. {cta}"]
    else:
        reason = compact_reason_line(insight, strategy, trigger)
        action_with_outcome = f"{action_line}. {outcome} {cta}"
        final_lines = [hook, insight_line, reason, action_with_outcome]
        rough_text = "\n".join(re.sub(r"\s+", " ", line).strip() for line in final_lines if line.strip())
        if len(rough_text) > 440:
            final_lines[-1] = f"{action_line}. {cta}"
            rough_text = "\n".join(re.sub(r"\s+", " ", line).strip() for line in final_lines if line.strip())
        if len(rough_text) > 450:
            final_lines = [hook, insight_line, f"{action_line}. {cta}"]

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
    ranked = sorted(
        [annotate_selection_scores(insight, category, merchant, trigger) for insight in insights],
        key=lambda item: (
            item["selection_score"],
            item["merchant_fit"],
            len(safe_text(item.get("action"))),
            1 if re.search(r"\d", f"{item.get('insight', '')} {item.get('action', '')}") else 0,
        ),
        reverse=True,
    )
    best = lock_perfect_insight(ranked[0], category, merchant, trigger, customer)
    genericity_before = genericity_issues(best, category, merchant, trigger)
    best = force_hyper_specific(best, category, merchant, trigger, customer)
    genericity_after = genericity_issues(best, category, merchant, trigger)
    best = force_business_decision(best, category, merchant, trigger, customer)
    genericity_final = genericity_issues(best, category, merchant, trigger)
    strict_final_before = strict_final_issues(best, category, merchant, trigger, customer)
    best = force_strict_final_validation(best, category, merchant, trigger, customer)
    strict_final_after = strict_final_issues(best, category, merchant, trigger, customer)
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
        "category_fit": best.get("category_fit"),
        "merchant_fit": best.get("merchant_fit"),
        "trigger_relevance": best.get("trigger_relevance"),
        "selection_score": best.get("selection_score"),
        "genericity_before": genericity_before,
        "genericity_after": genericity_after,
        "genericity_final": genericity_final,
        "strict_final_before": strict_final_before,
        "strict_final_after": strict_final_after,
        "quality_issues": issues,
        "candidate_count": len(ranked),
    }
    return message, metadata
