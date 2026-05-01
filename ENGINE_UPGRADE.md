# Message Engine Upgrade

## 1. Improved Modular Design

The engine now has two layers:

1. `bot.py` keeps the judge contract: context storage, `/v1/tick`, `/v1/reply`, suppression, and fallback composers.
2. `message_intelligence.py` chooses the best business insight before writing the WhatsApp body.

Flow:

```text
contexts -> generate insight candidates -> score/rank -> choose one strategy
         -> vary hook/tone -> render 4-line WhatsApp -> quality filter
         -> fallback composer if needed -> API response
```

Strategies:

- `Performance Alert`: low metrics, review issues, unverified GBP, renewal risk.
- `Growth Opportunity`: spike, milestone, competitor, seasonal demand shift.
- `Missed Customer Engagement`: recall, refill, lapsed customer, trial follow-up.
- `Smart Recommendation`: digest, compliance, curious asks, planning.

## 2. Pseudocode

### Insight Ranking

```python
def generate_insights(category, merchant, trigger, customer):
    candidates = []
    candidates += insights_from_trigger_payload(trigger)
    candidates += insights_from_merchant_performance(merchant, category.peer_stats)
    candidates += insights_from_customer_state(customer)
    candidates += insights_from_active_offers(merchant.offers)
    return candidates

def score(candidate):
    return (
        candidate.revenue * 4
        + candidate.engagement * 3
        + candidate.urgency * 2
        + candidate.confidence * 2
        + has_number(candidate.insight) * 5
        + has_benchmark(candidate) * 4
    )

best = max(candidates, key=score)
```

### Message Enhancement

```python
strategy = classify(trigger.kind)
tone = tone_for(strategy, trigger.urgency)
hook = hook_variant(tone, merchant, trigger)

message = [
    hook,
    insight_with_number_or_benchmark(best),
    one_specific_action(best),
    natural_cta(tone),
]
```

### Output Filtering

```python
def quality_issues(message):
    reject_if_no_number()
    reject_if_generic_phrase()
    reject_if_more_than_4_lines()
    reject_if_weak_cta()
    reject_if_multiple_questions()

if quality_issues(message):
    message = improve_or_fallback(message)
```

## 3. Before vs After

### Research Digest

Before:

```text
Dr. Meera, JIDA Oct 2026 has one useful item...
```

After:

```text
Dr. Meera, one thing stood out to me:
JIDA Oct 2026: 3-month fluoride recall maps to your 124 high-risk adult patients.
Turn it into a 2-min owner summary + patient WhatsApp draft.
Want me to pull the draft together?
```

### Performance Dip

Before:

```text
Bharat, your calls dropped -50% in 7d. Reply YES and I'll draft it.
```

After:

```text
Bharat, one issue is showing up clearly:
Calls are down -50% in 7d, while the peer marker is 12.
Use Dental Cleaning @ Rs 299 as the single hook in a fresh Google post.
Want the ready-to-send version?
```

### Customer Recall

Before:

```text
Hi Priya, your 6 month cleaning is due. Reply 1/2.
```

After:

```text
Dr. Meera, one customer moment is ready to act on:
Priya's 6-month cleaning is due after the 2026-05-12 visit.
Offer Wed 5 Nov, 6pm / Thu 6 Nov, 5pm with Dental Cleaning @ Rs 299.
Want me to send the draft for approval?
```

## 4. Integration Notes

- Keep `compose_*` functions as deterministic fallbacks.
- Use `intelligent_message(...)` first for all triggers.
- Add new insight extractors by trigger family, not by writing more full templates.
- Treat `rationale` as audit metadata: include strategy, insight score, and candidate count.
- Keep quality filters strict: a weak message should fall back rather than ship.
