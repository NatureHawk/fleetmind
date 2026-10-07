"""Fleet-level coordination.

The manager ticks every agent in a fixed order (determinism) and is the subscriber that
turns shared-world changes into per-agent notifications: when a closure or congestion is
broadcast, only robots whose *remaining* route is affected are asked to replan or
re-evaluate. Everyone else simply benefits from the updated world model next time they
plan.
"""

from __future__ import annotations

from app.agents.communication import WorldChange
from app.agents.context import AgentContext
from app.agents.robot import RobotAgent, RobotStatus
from app.core.event_bus import Topics
from app.simulation.timeline import Category, Severity


class AgentManager:
    def __init__(self, robots: list[RobotAgent], ctx: AgentContext) -> None:
        self.robots = robots
        self.by_id = {r.id: r for r in robots}
        self.ctx = ctx
        ctx.bus.subscribe(Topics.WORLD_CHANGED, self._on_world_changed)

    def get(self, robot_id: str) -> RobotAgent | None:
        return self.by_id.get(robot_id)

    def tick(self) -> None:
        self.ctx.charging.promote(self.ctx.now)
        for robot in self.robots:
            robot.tick(self.ctx)

    def active(self) -> list[RobotAgent]:
        return [r for r in self.robots if r.status != RobotStatus.OFFLINE]

    def _on_world_changed(self, change: WorldChange) -> None:
        roads = set(change.road_ids)
        env = self.ctx.env
        names = [env.roads[r].name for r in change.road_ids[:3]]
        if len(change.road_ids) > 3:
            names.append(f"+{len(change.road_ids) - 3} more")
        road_txt = ", ".join(names)
        affected: list[str] = []
        listeners = 0
        for robot in self.robots:
            if robot.status == RobotStatus.OFFLINE:
                continue
            listeners += 1
            if not robot.route_uses(roads):
                continue
            if change.kind == "blocked":
                robot.request_replan("ROAD_BLOCKED", f"{road_txt} reported closed by {change.sender}")
                affected.append(robot.id)
            elif change.kind == "traffic":
                worse = [r for r in roads if r in change.levels and change.levels[r][1] > change.levels[r][0]]
                if worse and any(r in worse for r in robot.remaining_roads()):
                    level = change.levels[worse[0]][1].label
                    robot.request_reevaluate(f"traffic on {env.roads[worse[0]].name} rose to {level}")
                    affected.append(robot.id)

        if change.kind == "blocked":
            msg = (f"{change.sender} → fleet: ROAD_BLOCKED {road_txt}. World model updated for {listeners} agents; "
                   f"{len(affected)} route(s) invalidated")
            severity = Severity.WARNING
        elif change.kind == "traffic":
            levels = {lvl[1].label for lvl in change.levels.values()}
            if levels == {"low"}:
                msg = f"{change.sender} → fleet: traffic cleared on {road_txt}; planners see free-flow costs again"
            else:
                msg = (f"{change.sender} → fleet: traffic {'/'.join(sorted(levels))} on {road_txt}. "
                       f"{len(affected)} robot(s) re-evaluating routes")
            severity = Severity.NOTICE if affected else Severity.INFO
        else:
            msg = f"{change.sender} → fleet: {road_txt} reopened and available to planners"
            severity = Severity.INFO
        self.ctx.timeline.add(Category.COORDINATION, f"BROADCAST_{change.kind.upper()}", msg, severity=severity,
                              road_id=change.road_ids[0] if change.road_ids else None,
                              data={"sender": change.sender, "roads": change.road_ids, "affected": affected,
                                    "listeners": listeners, "message_seq": change.message_seq})
