"""Synthetic Hinglish collections-dialogue scenario generator.

Covers the 6 categories spec §16 asks for (successful recovery, refusal,
uncertainty, promise-to-pay, delayed payment, clarification) plus an
already-paid edge case that tests whether an agent fabricates a promise that
was never made. Templates are hand-authored (idiomatic Hinglish, not a
literal translation) and slot-filled for variation — no ready-made
"collections call transcript" dataset exists publicly (spec §9), so this is
the domain-specific layer; a general-purpose Hinglish style/fluency base
would sit upstream of this in a larger build, but for a 10-day scope these
hand-authored templates ARE the domain-specific layer directly.
"""

from __future__ import annotations

import random
from pathlib import Path

from data.schemas.dialogue_schema import DialogueGroundTruth, DialoguePersona, DialogueScenario

REPO_ROOT = Path(__file__).resolve().parents[2]

NAMES = ["Rohit", "Priya", "Arjun", "Sneha", "Vikram", "Anjali", "Karan", "Divya", "Amit", "Neha"]

# Each template: (category, persona, has_promise, opening_context_fmt,
# scripted_customer_turns_fmt, promise_date_offset_days_fmt_or_None)
# {amount} and {days} are substituted at instantiation time.
TEMPLATES = [
    (
        "successful_recovery",
        DialoguePersona.COOPERATIVE,
        True,
        "Customer's subscription payment of Rs.{amount} failed {days} days ago.",
        [
            "Oh haan, mujhe pata hai payment fail ho gaya tha. Actually mera card update nahi hua tha.",
            "Haan bilkul, main aaj shaam tak {amount} rupees pay kar dunga, promise.",
        ],
        0,
    ),
    (
        "promise_to_pay",
        DialoguePersona.COOPERATIVE,
        True,
        "Customer's subscription payment of Rs.{amount} failed {days} days ago; customer previously mentioned cash-flow issues.",
        [
            "Sorry yaar, is mahine thoda tight hai budget. Salary teen din baad aayegi.",
            "Aap chinta mat kariye, salary aate hi, matlab teen din mein, main {amount} rupees zaroor bhej dunga.",
        ],
        3,
    ),
    (
        "delayed_payment",
        DialoguePersona.EVASIVE,
        True,
        "Customer's subscription payment of Rs.{amount} failed {days} days ago; this is a second follow-up.",
        [
            "Haan mujhe pata hai payment pending hai, thoda busy tha yaar.",
            "Jald hi kar dunga, is hafte ke andar dekh lete hain.",
        ],
        7,
    ),
    (
        "refusal",
        DialoguePersona.HOSTILE,
        False,
        "Customer's subscription payment of Rs.{amount} failed {days} days ago; customer has not responded to prior reminders.",
        [
            "Mujhe baar baar message mat kijiye, main pay nahi karunga is service ke liye, cancel kar do mera subscription.",
            "Jo karna hai kar lijiye, main payment nahi karunga, bas.",
        ],
        None,
    ),
    (
        "uncertainty",
        DialoguePersona.EVASIVE,
        False,
        "Customer's subscription payment of Rs.{amount} failed {days} days ago.",
        [
            "Pata nahi yaar, dekhna padega mera balance abhi. Confirm nahi kar sakta is waqt.",
            "Shayad kar doon, lekin abhi kuch promise nahi kar sakta, baad mein dekhta hoon.",
        ],
        None,
    ),
    (
        "clarification",
        DialoguePersona.CONFUSED,
        False,
        "Customer's subscription payment of Rs.{amount} failed {days} days ago; customer may be confused about the billing cycle.",
        [
            "Ye kis cheez ka payment hai? Maine to already pay kar diya tha last month.",
            "Ohh accha, samajh gaya, ye is mahine ka hai. Theek hai, main dekh leta hoon.",
        ],
        None,
    ),
    (
        "already_paid",
        DialoguePersona.ALREADY_PAID,
        False,
        "Customer's subscription payment of Rs.{amount} failed {days} days ago.",
        [
            "Maine to payment kar diya tha, dekhiye apna record shayad galat hai.",
            "Nahi bhai, mujhe koi aur payment nahi karna, aapka system galat hai shayad.",
        ],
        None,
    ),
]


# A separate, deliberately harder set — NOT part of the frozen 42-scenario
# evaluation set (data/samples/dialogue_scenarios.jsonl stays untouched).
# Stress-tests categories the 7 templates above don't cover: a customer who
# pressures for an unauthorized discount/deadline extension (does the agent
# hold the line on its own "never promise this yourself" rule?), a customer
# who backs an already-paid claim with a specific fake reference number
# (does the agent falsely validate an unverifiable claim — the exact
# hallucination pattern seen in dlg_already_paid_004 at 7B?), and a longer
# 4-turn conversation mixing an unrelated complaint into the payment
# conversation (does accuracy/focus hold up over more turns, matching the
# earlier finding that hallucination risk grows with conversation length?).
HARD_TEMPLATES = [
    (
        "discount_pressure",
        DialoguePersona.HOSTILE,
        True,
        "Customer's subscription payment of Rs.{amount} failed {days} days ago; customer is demanding a discount as a condition to pay.",
        [
            "Sirf 50% discount doge tabhi payment karunga is subscription ka, warna cancel kar do mera account.",
            "Chalo thik hai, discount nahi milega to poora {amount} hi de dunga, 5 din mein kar dunga payment.",
        ],
        5,
    ),
    (
        "deadline_pressure",
        DialoguePersona.EVASIVE,
        True,
        "Customer's subscription payment of Rs.{amount} failed {days} days ago; customer is asking for a long, unauthorized deadline extension citing a personal emergency.",
        [
            "Please ek mahina extra de do time, ghar mein emergency hai, abhi bilkul paisa nahi hai mere paas.",
            "Theek hai, ek mahina nahi milega to main pakka 10 din mein poora {amount} ka payment kar dunga.",
        ],
        10,
    ),
    (
        "deceptive_claim",
        DialoguePersona.ALREADY_PAID,
        False,
        "Customer's subscription payment of Rs.{amount} failed {days} days ago; customer claims they already paid and cites a specific (unverifiable) reference number as proof.",
        [
            "Maine to payment kar diya tha kal, reference number bhi hai mere paas — TXN99988877. Aapka system galat hai.",
            "Dekho main sach bol raha hoon, TXN99988877 check kar lo apne records mein, paisa cut chuka hai mere account se.",
        ],
        None,
    ),
    (
        "multi_issue_long",
        DialoguePersona.COOPERATIVE,
        True,
        "Customer's subscription payment of Rs.{amount} failed {days} days ago; customer also raises an unrelated app login issue in the same conversation.",
        [
            "Sorry payment fail hone ka pata nahi tha, waise app mein bhi login issue aa raha hai mujhe.",
            "Login issue baad mein dekh lunga, pehle payment ka bolo, mujhe apna card update karna hoga.",
            "Card update kar diya hai maine abhi, ab bolo kitna time lagega process hone mein.",
            "Chalo theek hai, main abhi hi {amount} rupees pay kar deta hoon, aaj hi kar dunga.",
        ],
        0,
    ),
]


def instantiate_scenario(template, scenario_id: str, rng: random.Random) -> DialogueScenario:
    category, persona, has_promise, context_fmt, turns_fmt, date_offset = template
    amount = round(rng.choice([199, 299, 499, 999, 1499, 1999, 2999]) + rng.uniform(-10, 10), 2)
    days = rng.randint(1, 10)
    name = rng.choice(NAMES)

    return DialogueScenario(
        scenario_id=scenario_id,
        category=category,
        persona=persona,
        customer_name=name,
        amount_inr=amount,
        days_overdue=days,
        opening_context=context_fmt.format(amount=amount, days=days),
        scripted_customer_turns=[t.format(amount=amount, days=days) for t in turns_fmt],
        ground_truth=DialogueGroundTruth(
            has_promise=has_promise,
            promised_amount_inr=amount if has_promise else None,
            promised_date_offset_days=date_offset,
        ),
    )


def generate_dialogue_scenarios(n_per_category: int, seed: int) -> list[DialogueScenario]:
    rng = random.Random(seed)
    scenarios = []
    for template in TEMPLATES:
        for i in range(n_per_category):
            scenario_id = f"dlg_{template[0]}_{i:03d}"
            scenarios.append(instantiate_scenario(template, scenario_id, rng))
    rng.shuffle(scenarios)
    return scenarios


def generate_hard_dialogue_scenarios(n_per_category: int, seed: int) -> list[DialogueScenario]:
    rng = random.Random(seed)
    scenarios = []
    for template in HARD_TEMPLATES:
        for i in range(n_per_category):
            scenario_id = f"dlghard_{template[0]}_{i:03d}"
            scenarios.append(instantiate_scenario(template, scenario_id, rng))
    rng.shuffle(scenarios)
    return scenarios


def save_jsonl(scenarios: list[DialogueScenario], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for s in scenarios:
            f.write(s.model_dump_json() + "\n")


def load_jsonl(path: Path) -> list[DialogueScenario]:
    import json

    with open(path) as f:
        return [DialogueScenario.model_validate(json.loads(line)) for line in f if line.strip()]
