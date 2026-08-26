import random

from data.generators.failure_generator import generate_case
from data.schemas.case_schema import SubscriptionState


def make_case(case_id: str = "test_case", seed: int = 1, subscription_state: str | None = None):
    case = generate_case(case_id, random.Random(seed))
    if subscription_state is not None:
        case = case.model_copy(
            update={
                "context": case.context.model_copy(
                    update={"subscription_state": SubscriptionState(subscription_state)}
                )
            }
        )
    return case
