# ContextCraft Vera

This submission uses a deterministic, stateful composer instead of a live LLM call. The goal is to score well on the judge dimensions while staying fast, private, and reliable under replay.

## Approach

- Store all pushed category, merchant, customer, and trigger contexts by version.
- Route each trigger kind to a category-aware composer.
- Internally classify every trigger into one strategy: Performance Alert, Growth Opportunity, Missed Customer Engagement, or Smart Recommendation.
- Generate and rank multiple insight candidates before writing the message.
- Anchor every message on available context facts: merchant metrics, peer stats, active offers, digest sources, customer preferences, slots, and suppression keys.
- Apply final-message polish: sharper hook, hidden implication behind the number, decision justification, confidence signal, urgency, outcome visualization, natural memory reference, and non-robotic CTA.
- Use service-plus-price offers where available instead of generic percentage discounts.
- Keep outbound bodies WhatsApp-native: 3-5 short lines, one strong insight, one immediate action, one soft CTA.
- Run a quality filter that rejects missing numbers, generic language, weak CTAs, and scattered multi-idea copy.
- Handle replay turns with explicit auto-reply detection, opt-out/hostility exits, out-of-scope redirects, and immediate action mode when the merchant says yes.

## Tradeoffs

The bot avoids external API calls and therefore cannot generate arbitrarily novel copy. The upside is deterministic output under 30 seconds and no risk of leaking synthetic merchant/customer context outside the test environment.

## What Would Help Most

The most valuable extra context would be actual available appointment slots for every customer-facing trigger, a normalized offer source of truth, and reliable locality-level peer benchmarks for social proof.

Run locally:

```bash
python bot.py
```

Or with FastAPI/uvicorn if installed:

```bash
uvicorn bot:app --host 0.0.0.0 --port 8080
```

Run the first end-to-end message-engine flow on Windows:

```powershell
.\run_flow.ps1
```

That demo loads Dr. Meera's dentist context, composes the research-digest WhatsApp, simulates a positive merchant reply, and shows Vera's next action.

Create a temporary public endpoint for submission:

```powershell
.\run_public_tunnel.ps1
```

Submit the printed `https://...` URL as the base URL. Keep the tunnel window open while the judge runs.
