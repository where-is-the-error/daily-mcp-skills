"""의존 그래프·적용 순서 — 30개."""

from __future__ import annotations

from conftest import PROPOSAL, plan_dict, resource_change
from plan_guard import order
from plan_guard.plan import from_dict, load_plan


def config(resources: list[dict]) -> dict:
    return {"root_module": {"resources": resources}}


def cfg_resource(address: str, refs: dict | None = None) -> dict:
    rtype, _, name = address.rpartition(".")
    expressions = {
        key: {"references": value} for key, value in (refs or {}).items()
    }
    return {"address": address, "mode": "managed", "type": rtype, "name": name, "expressions": expressions}


def plan_with(changes: list[dict], resources: list[dict]):
    return from_dict(plan_dict(changes, configuration=config(resources)))


SG = cfg_resource("aws_security_group.api")
INSTANCE = cfg_resource("aws_instance.api", {"vpc_security_group_ids": ["aws_security_group.api.id", "aws_security_group.api"]})
DB = cfg_resource("aws_db_instance.main", {"vpc_security_group_ids": ["aws_security_group.api.id"]})


def changes():
    return [
        resource_change("aws_security_group.api", ["update"], {"ingress": []}, {"ingress": []}),
        resource_change("aws_instance.api", ["create"], None, {"id": None}),
        resource_change("aws_db_instance.main", ["create"], None, {"id": None}),
    ]


# ------------------------------------------------------------------ 그래프
def test_edges_from_references() -> None:
    graph = order.build(plan_with(changes(), [SG, INSTANCE, DB]))
    assert graph.edges["aws_instance.api"] == {"aws_security_group.api"}
    assert graph.dependents["aws_security_group.api"] == {"aws_instance.api", "aws_db_instance.main"}


def test_reference_to_unknown_address_is_ignored() -> None:
    resource = cfg_resource("aws_instance.api", {"subnet_id": ["aws_subnet.missing.id"]})
    graph = order.build(plan_with([resource_change("aws_instance.api", ["create"], None, {})], [resource]))
    assert graph.edges.get("aws_instance.api", set()) == set()


def test_self_reference_ignored() -> None:
    resource = cfg_resource("aws_instance.api", {"x": ["aws_instance.api.id"]})
    graph = order.build(plan_with([resource_change("aws_instance.api", ["create"], None, {})], [resource]))
    assert graph.edges.get("aws_instance.api", set()) == set()


def test_no_configuration_is_safe() -> None:
    plan = from_dict({"format_version": "1.2", "resource_changes": [resource_change("aws_instance.a", ["create"], None, {})]})
    graph = order.build(plan)
    assert graph.nodes == ["aws_instance.a"]
    assert graph.edges == {}


# ------------------------------------------------------------------ 순서
def test_create_order_dependency_first() -> None:
    result = [c.address for c in order.create_order(plan_with(changes(), [SG, INSTANCE, DB]))]
    assert result.index("aws_security_group.api") < result.index("aws_instance.api")
    assert result.index("aws_security_group.api") < result.index("aws_db_instance.main")


def test_destroy_order_reverse() -> None:
    plan = plan_with(
        [
            resource_change("aws_security_group.api", ["delete"], {"id": "sg"}, None),
            resource_change("aws_instance.api", ["delete"], {"id": "i"}, None),
        ],
        [INSTANCE],
    )
    result = [c.address for c in order.destroy_order(plan)]
    assert result == ["aws_instance.api", "aws_security_group.api"]


def test_updates_are_in_write_order() -> None:
    plan = load_plan(str(PROPOSAL))
    addresses = [c.address for c in order.create_order(plan)]
    assert addresses.index("aws_security_group.api") < addresses.index("aws_instance.api")


def test_blocked_when_deleted_resource_is_referenced() -> None:
    plan = plan_with(
        [
            resource_change("aws_security_group.api", ["delete"], {"id": "sg"}, None),
            resource_change("aws_instance.api", ["update"], {"a": 1}, {"a": 2}),
        ],
        [INSTANCE],
    )
    blockers = order.blocked(plan)
    assert blockers[0][0].address == "aws_security_group.api"
    assert blockers[0][1] == ["aws_instance.api"]


def test_not_blocked_when_both_disappear() -> None:
    plan = plan_with(
        [
            resource_change("aws_security_group.api", ["delete"], {"id": "sg"}, None),
            resource_change("aws_instance.api", ["delete"], {"id": "i"}, None),
        ],
        [INSTANCE],
    )
    assert order.blocked(plan) == []


def test_replace_is_not_a_blocker() -> None:
    plan = plan_with(
        [
            resource_change("aws_security_group.api", ["delete", "create"], {"id": "sg"}, {"id": None}),
            resource_change("aws_instance.api", ["update"], {"a": 1}, {"a": 2}),
        ],
        [INSTANCE],
    )
    assert order.blocked(plan) == []


def test_cycles_reported() -> None:
    a = cfg_resource("aws_instance.a", {"x": ["aws_instance.b.id"]})
    b = cfg_resource("aws_instance.b", {"x": ["aws_instance.a.id"]})
    plan = plan_with(
        [resource_change("aws_instance.a", ["create"], None, {}), resource_change("aws_instance.b", ["create"], None, {})],
        [a, b],
    )
    graph = order.build(plan)
    assert graph.cycles
    assert set(graph.cycles[0]) == {"aws_instance.a", "aws_instance.b"}


# ------------------------------------------------------------------ 설명
def test_describe_lists_both_directions() -> None:
    text = "\n".join(order.describe(plan_with(changes(), [SG, INSTANCE, DB])))
    assert "쓰는 순서" in text
    assert "← aws_security_group.api" in text


def test_describe_mentions_blocker() -> None:
    plan = plan_with(
        [
            resource_change("aws_security_group.api", ["delete"], {"id": "sg"}, None),
            resource_change("aws_instance.api", ["update"], {"a": 1}, {"a": 2}),
        ],
        [INSTANCE],
    )
    text = "\n".join(order.describe(plan))
    assert "아직 참조합니다" in text


def test_describe_mentions_cycle() -> None:
    a = cfg_resource("aws_instance.a", {"x": ["aws_instance.b.id"]})
    b = cfg_resource("aws_instance.b", {"x": ["aws_instance.a.id"]})
    plan = plan_with(
        [resource_change("aws_instance.a", ["create"], None, {}), resource_change("aws_instance.b", ["create"], None, {})],
        [a, b],
    )
    assert "순환 참조" in "\n".join(order.describe(plan))


def test_describe_empty_plan() -> None:
    plan = from_dict(plan_dict([]))
    assert order.describe(plan) == ["만들거나 지우는 리소스가 없습니다."]


def test_resolve_prefers_longest_address() -> None:
    assert order._resolve("aws_instance.api.id", {"aws_instance.api", "aws_instance"}) == "aws_instance.api"
    assert order._resolve("aws_instance.api[0].id", {"aws_instance.api"}) == "aws_instance.api"
    assert order._resolve("aws_instance.api2.id", {"aws_instance.api"}) is None


def test_module_resources_are_read() -> None:
    configuration = {
        "root_module": {
            "resources": [],
            "module_calls": {
                "net": {
                    "module": {
                        "resources": [
                            cfg_resource("module.net.aws_vpc.main"),
                            cfg_resource("module.net.aws_subnet.a", {"vpc_id": ["module.net.aws_vpc.main"]}),
                        ]
                    }
                }
            },
        }
    }
    plan = from_dict(plan_dict(
        [resource_change("module.net.aws_vpc.main", ["create"], None, {}),
         resource_change("module.net.aws_subnet.a", ["create"], None, {})],
        configuration=configuration,
    ))
    graph = order.build(plan)
    assert graph.edges["module.net.aws_subnet.a"] == {"module.net.aws_vpc.main"}
