from message_engine import build_demo_engine


def main() -> None:
    engine = build_demo_engine()
    outbound = engine.compose_for_trigger("trg_001_research_digest_dentists")
    if not outbound:
        raise SystemExit("Could not compose outbound message")

    print("=== Vera outbound ===")
    print(outbound["body"])

    merchant_reply = "Yes please send the summary and patient WhatsApp."
    print("\n=== Merchant reply ===")
    print(merchant_reply)

    next_action = engine.receive_reply(
        conversation_id=outbound["conversation_id"],
        merchant_id=outbound["merchant_id"],
        message=merchant_reply,
    )

    print("\n=== Vera next action ===")
    print(next_action["action"])
    if next_action["action"] == "send":
        print(next_action["body"])
    else:
        print(next_action["rationale"])


if __name__ == "__main__":
    main()
