"""plan-guard — terraform plan JSON 을 apply 전에 읽는다.

    from plan_guard import load_plan, risks
    plan = load_plan("plan.json")
    print(risks.verdict_line(risks.findings(plan)))
"""

from .plan import Change, Plan, PlanError, load_plan

__all__ = ["Change", "Plan", "PlanError", "load_plan"]
__version__ = "0.1.0"
