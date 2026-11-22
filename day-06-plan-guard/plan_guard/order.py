"""적용 순서 — configuration 의 참조로 의존 그래프를 만든다.

terraform 은 알아서 순서를 잡지만, 사람이 '무엇이 먼저 사라지는지'를 보려면
그래프가 필요하다. 특히 **지우는 리소스를 다른 리소스가 참조하고 있으면**
apply 는 실패하거나(보호 중) 참조가 깨진다. 그 관계를 여기서 보여 준다.

그래프는 plan JSON 의 `configuration.root_module.resources[].expressions[].references`
만 쓴다(변수·local 은 노드가 아니므로 건너뛴다). plan 에만 있고 설정에는 없는
리소스(삭제되는 것)는 나가는 간선이 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .plan import Change, Plan


@dataclass
class Graph:
    nodes: list[str] = field(default_factory=list)
    edges: dict[str, set[str]] = field(default_factory=dict)      # A -> A 가 의존하는 B
    dependents: dict[str, set[str]] = field(default_factory=dict)  # B -> B 를 참조하는 A
    cycles: list[list[str]] = field(default_factory=list)

    def add_edge(self, dependent: str, dependency: str) -> None:
        if dependent == dependency:
            return
        self.edges.setdefault(dependent, set()).add(dependency)
        self.dependents.setdefault(dependency, set()).add(dependent)


def _resolve(reference: str, addresses: set[str]) -> str | None:
    """'aws_security_group.api.id' → 'aws_security_group.api' (가장 긴 일치)."""
    best: str | None = None
    for address in addresses:
        if reference == address or reference.startswith(address + ".") or reference.startswith(address + "["):
            if best is None or len(address) > len(best):
                best = address
    return best


def _config_resources(configuration: dict | None) -> list[dict]:
    if not isinstance(configuration, dict):
        return []
    root = configuration.get("root_module") or {}
    out: list[dict] = []
    for item in root.get("resources") or []:
        if isinstance(item, dict):
            out.append(item)
    for call in (root.get("module_calls") or {}).values():
        module = (call or {}).get("module") or {}
        for item in module.get("resources") or []:
            if isinstance(item, dict):
                out.append(item)
    return out


def build(plan: Plan) -> Graph:
    addresses = {c.address for c in plan.changes}
    graph = Graph(nodes=sorted(addresses))

    for item in _config_resources(plan.configuration):
        address = str(item.get("address") or "")
        if address not in addresses:
            continue
        for expression in (item.get("expressions") or {}).values():
            for reference in (expression or {}).get("references") or []:
                target = _resolve(str(reference), addresses)
                if target:
                    graph.add_edge(address, target)

    graph.cycles = _cycles(graph)
    return graph


def _cycles(graph: Graph) -> list[list[str]]:
    """남아 있는 노드가 있으면 순환이다 (terraform 은 순환을 거부하지만, 손으로 만든 plan 도 본다)."""
    indegree = {node: 0 for node in graph.nodes}
    for node, deps in graph.edges.items():
        for dep in deps:
            if dep in indegree:
                indegree[node] = indegree.get(node, 0) + 1
    queue = sorted(n for n, deg in indegree.items() if deg == 0)
    seen = 0
    while queue:
        node = queue.pop(0)
        seen += 1
        for dependent in sorted(graph.dependents.get(node, ())):
            if dependent in indegree:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)
    leftover = sorted(n for n, deg in indegree.items() if deg > 0)
    return [leftover] if leftover else []


def _topo(graph: Graph, subset: set[str], reverse: bool = False) -> list[str]:
    """subset 안에서 의존성 먼저(reverse=False) 또는 나중(reverse=True) 순서."""
    local = {n: {d for d in graph.edges.get(n, ()) if d in subset} for n in subset}
    order: list[str] = []
    remaining = dict(local)
    while remaining:
        ready = sorted(n for n, deps in remaining.items() if not deps)
        if not ready:
            order.extend(sorted(remaining))
            break
        for node in ready:
            order.append(node)
            remaining.pop(node, None)
        for deps in remaining.values():
            deps.difference_update(ready)
    return list(reversed(order)) if reverse else order


def create_order(plan: Plan) -> list[Change]:
    graph = build(plan)
    creating = {c.address for c in plan.changes if c.writes}
    order = _topo(graph, creating)
    index = {c.address: c for c in plan.changes}
    return [index[a] for a in order if a in index]


def destroy_order(plan: Plan) -> list[Change]:
    graph = build(plan)
    deleting = {c.address for c in plan.changes if c.deletes}
    order = _topo(graph, deleting, reverse=True)
    index = {c.address: c for c in plan.changes}
    return [index[a] for a in order if a in index]


def blocked(plan: Plan) -> list[tuple[Change, list[str]]]:
    """지우는데 아직 살아 있는 리소스가 참조하는 것 — apply 가 막히거나 깨진다."""
    graph = build(plan)
    index = {c.address: c for c in plan.changes}
    out: list[tuple[Change, list[str]]] = []
    for change in plan.changes:
        if not change.deletes or change.kind == "replace":
            continue
        refs = sorted(r for r in graph.dependents.get(change.address, ()) if r in index)
        alive = [r for r in refs if not index[r].deletes]
        if alive:
            out.append((change, alive))
    return out


def describe(plan: Plan, reverse: bool = False) -> list[str]:
    lines: list[str] = []
    graph = build(plan)
    creating = create_order(plan)
    if creating and not reverse:
        lines.append("쓰는 순서 (의존하는 것 먼저):")
        for step, change in enumerate(creating, 1):
            deps = sorted(d for d in graph.edges.get(change.address, ()) if d in {c.address for c in plan.changes})
            tail = f"  ← {', '.join(deps[:3])}" if deps else ""
            lines.append(f"  {step}. {change.address} [{change.kind_label}]{tail}")
    deleting = destroy_order(plan)
    if deleting:
        lines.append("")
        lines.append("지우는 순서 (참조하는 것 먼저):")
        for step, change in enumerate(deleting, 1):
            lines.append(f"  {step}. {change.address} [{change.kind_label}]")
    blockers = blocked(plan)
    if blockers:
        lines.append("")
        lines.append("apply 가 막히거나 참조가 깨질 수 있는 곳:")
        for change, alive in blockers:
            lines.append(f"  - {change.address} 를 지우려는데 {', '.join(alive[:3])} 가 아직 참조합니다")
    if graph.cycles:
        lines.append("")
        lines.append("순환 참조: " + ", ".join(graph.cycles[0][:6]) + " (terraform 은 이런 설정을 거부합니다)")
    if not lines:
        lines.append("만들거나 지우는 리소스가 없습니다.")
    return lines
