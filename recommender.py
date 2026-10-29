"""Easy-to-follow forward and backward chaining recommendation functions."""

from knowledge_base import DESTINATIONS


def check_preference_rules(destination, preferences):
    """Check three IF-THEN rules and return a plain-English result for each."""
    budget = preferences["budget"]
    trip_days = preferences["trip_days"]
    destination_type = preferences["destination_type"]

    checks = [
        {
            "name": "Budget rule",
            "matched": budget >= destination["budget_min"],
            "matched_text": (
                f"IF your budget is at least ₹{destination['budget_min']:,} "
                f"THEN {destination['name']} fits the starting-cost rule."
            ),
            "missed_text": (
                f"IF your budget is at least ₹{destination['budget_min']:,} "
                f"THEN {destination['name']} fits the starting-cost rule "
                "(your budget is below this estimate)."
            ),
        },
        {
            "name": "Duration rule",
            "matched": destination["days_min"] <= trip_days <= destination["days_max"],
            "matched_text": (
                f"IF your trip is {destination['days_min']}–{destination['days_max']} days "
                f"THEN {destination['name']} fits the suggested trip length."
            ),
            "missed_text": (
                f"IF your trip is {destination['days_min']}–{destination['days_max']} days "
                f"THEN {destination['name']} fits the suggested trip length "
                "(your duration is outside this range)."
            ),
        },
        {
            "name": "Destination-type rule",
            "matched": destination_type in destination["tags"],
            "matched_text": (
                f"IF you prefer {destination_type} and {destination['name']} includes "
                f"{' and '.join(destination['tags'])} "
                "THEN the destination-type rule matches."
            ),
            "missed_text": (
                f"IF you prefer {destination_type} and {destination['name']} includes "
                f"{' and '.join(destination['tags'])} "
                "THEN the destination-type rule matches (this preference did not match)."
            ),
        },
    ]
    return checks


def forward_chain(preferences):
    """Start with the user's facts, apply rules, then return the best three places."""
    candidates = []

    for destination in DESTINATIONS:
        checks = check_preference_rules(destination, preferences)
        matched_count = sum(1 for check in checks if check["matched"])
        trip_midpoint = (destination["days_min"] + destination["days_max"]) / 2
        candidates.append(
            {
                **destination,
                "checks": checks,
                "matched_count": matched_count,
                "matched_rules": [
                    check["matched_text"] for check in checks if check["matched"]
                ],
                "missed_rules": [
                    check["missed_text"] for check in checks if not check["matched"]
                ],
                "trip_length_difference": abs(
                    preferences["trip_days"] - trip_midpoint
                ),
            }
        )

    # More matching rules rank first; nearby trip lengths break ties.
    candidates.sort(
        key=lambda place: (
            -place["matched_count"],
            place["trip_length_difference"],
            place["budget_min"],
        )
    )
    return candidates[:3]


def backward_chain_recommendation(destination, preferences, rank):
    """Start at a recommendation goal and trace back to the facts that support it."""
    # Backward chaining asks whether a rule can prove a goal, then checks its
    # conditions. Here the goal is: "Why is this destination in the top three?"
    checks = check_preference_rules(destination, preferences)
    matched_count = sum(1 for check in checks if check["matched"])

    if matched_count >= 2:
        conclusion = (
            f"Strong match: {matched_count} of your 3 preference rules matched."
        )
        applied_rule = (
            "IF at least two preference rules match, THEN this is a strong recommendation."
        )
        is_strong_match = True
    else:
        conclusion = (
            f"Additional option: {matched_count} of your 3 preference rules matched; "
            f"this destination ranked #{rank} in the full list."
        )
        applied_rule = (
            "IF a destination ranks in the top three after comparing all places, "
            "THEN include it as an additional option."
        )
        is_strong_match = False

    return {
        "goal": f"Explain why {destination['name']} appears in the top three.",
        "applied_rule": applied_rule,
        "conclusion": conclusion,
        "is_strong_match": is_strong_match,
        "checks": checks,
    }
