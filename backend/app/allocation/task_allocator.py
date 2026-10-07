"""Task allocation: which robot serves which order, and why.

Dispatch policy
---------------
* Pending orders are considered in priority order (CRITICAL first), then earliest deadline.
* Each round looks at the most urgent ``max_orders_per_round`` orders (bounded cost).
* For each order every robot is scored (see :mod:`app.allocation.scoring`); the lowest
  eligible score wins. Commitments are updated immediately, so two orders in the same
  round never double-book a robot, and the order book is the single source of truth, so
  an order can never be assigned twice.
* **Preemption** — if a CRITICAL order cannot be served on time by any free robot, the
  allocator may take a robot that is still driving to pick up a LOW/NORMAL order. That
  order goes back to the queue. The decision and its justification are logged.
"""

from __future__ import annotations

from collections import Counter

from app.agents.context import AgentContext
from app.agents.robot import RobotAgent, RobotStatus, StopKind
from app.allocation.scoring import CandidateEvaluation, Commitment, eligibility, evaluate, robot_commitment
from app.core.event_bus import Topics
from app.core.formatting import fmt_duration
from app.simulation.orders import Order, OrderStatus, Priority
from app.simulation.timeline import Category, Severity

PREEMPTION_MIN_GAIN_S = 60.0
WAIT_NOTE_INTERVAL_S = 300.0


class TaskAllocator:
    def __init__(self, *, preemption: bool = True, max_orders_per_round: int = 24) -> None:
        self.preemption = preemption
        self.max_orders_per_round = max_orders_per_round
        self.assignments = 0
        self.preemptions = 0
        self._waiting_notes: dict[str, tuple[str, float]] = {}

    def allocate(self, ctx: AgentContext, robots: list[RobotAgent], now: float) -> int:
        pending = ctx.orders.pending()
        if not pending:
            return 0
        commitments: dict[str, Commitment] = {}

        def commitment(robot: RobotAgent) -> Commitment:
            if robot.id not in commitments:
                commitments[robot.id] = robot_commitment(robot, ctx)
            return commitments[robot.id]

        assigned = 0
        for order in pending[: self.max_orders_per_round]:
            has_free = any(r.available_for_work and not r.low_battery_mode for r in robots)
            if not has_free and order.priority != Priority.CRITICAL:
                break
            # Ineligible robots are rejected before their (more expensive) commitment is computed.
            evals = [evaluate(r, order, ctx, now, commitment(r) if eligibility(r) is None else None)
                     for r in robots]
            eligible = sorted((e for e in evals if e.eligible), key=lambda e: (e.score, e.robot_id))
            best = eligible[0] if eligible else None

            if order.priority == Priority.CRITICAL and self.preemption and (best is None or best.lateness > 0):
                if self._try_preempt(order, ctx, robots, now, best):
                    commitments.clear()
                    assigned += 1
                    continue

            if best is None:
                self._note_waiting(order, evals, ctx)
                continue
            robot = next(r for r in robots if r.id == best.robot_id)
            self._commit(order, robot, best, eligible, evals, ctx, now, preempted=None)
            commitments.pop(robot.id, None)
            assigned += 1
        return assigned

    # ------------------------------------------------------------------------------------
    def _commit(self, order: Order, robot: RobotAgent, best: CandidateEvaluation,
                eligible: list[CandidateEvaluation], evals: list[CandidateEvaluation], ctx: AgentContext,
                now: float, preempted: Order | None) -> None:
        robot.assign(order, ctx, front=order.priority == Priority.CRITICAL)
        order.status = OrderStatus.ASSIGNED
        order.assigned_robot = robot.id
        order.assigned_at = now
        order.assignment_count += 1
        order.log(now, f"assigned to {robot.id}")
        self.assignments += 1
        self._waiting_notes.pop(order.id, None)

        reasons = self._reasons(best, eligible, robot, order, now)
        runner_up = eligible[1] if len(eligible) > 1 else None
        rejected = Counter((e.rejection or "").split(" (")[0] for e in evals if not e.eligible)
        explanation = {
            "robot_id": robot.id,
            "score": round(best.score, 1),
            "components": {k: round(v, 1) for k, v in best.components.items()},
            "reasons": reasons,
            "runner_up": runner_up.as_dict() if runner_up else None,
            "candidates": [e.as_dict() for e in eligible[:5]],
            "rejected": [{"reason": k, "count": v} for k, v in rejected.most_common()],
            "rejected_detail": [e.as_dict() for e in evals if not e.eligible][:12],
            "eligible_count": len(eligible),
            "policy": "min weighted score (travel + workload + battery + deadline)",
            "preempted_order": preempted.id if preempted else None,
            "t": round(now, 1),
        }
        order.explanation = explanation
        env = ctx.env
        ctx.timeline.add(
            Category.ALLOCATION, "ORDER_ASSIGNED",
            f"{order.id} ({order.priority.label}) {env.nodes[order.source].name} → "
            f"{env.nodes[order.destination].name} assigned to {robot.id} · score {best.score:.0f} "
            f"vs {runner_up.robot_id + ' ' + format(runner_up.score, '.0f') if runner_up else 'no alternative'}",
            severity=Severity.NOTICE if order.priority >= Priority.HIGH else Severity.INFO,
            robot_id=robot.id, order_id=order.id, data=explanation)
        ctx.bus.publish(Topics.ORDER_ASSIGNED, order)

    def _reasons(self, best: CandidateEvaluation, eligible: list[CandidateEvaluation], robot: RobotAgent,
                 order: Order, now: float) -> list[str]:
        reasons = []
        closest = min(eligible, key=lambda e: e.pickup_eta)
        if closest.robot_id == best.robot_id:
            reasons.append(f"closest available robot — pickup ETA {fmt_duration(best.pickup_eta)}")
        else:
            reasons.append(f"pickup ETA {fmt_duration(best.pickup_eta)}; {closest.robot_id} is closer "
                           f"({fmt_duration(closest.pickup_eta)}) but scores worse ({closest.score:.0f})")
        reasons.append(f"sufficient battery — {best.battery_now_pct:.0f}% now, ≈{best.battery_after_pct:.0f}% "
                       f"after delivery")
        if best.queued_orders == 0:
            reasons.append("no conflicting delivery — robot is idle" if best.idle
                           else "no conflicting delivery queued")
        else:
            reasons.append(f"{best.queued_orders} order(s) already queued "
                           f"(+{best.components['workload']:.0f}s workload penalty)")
        if best.lateness <= 0:
            slack = order.deadline - (now + best.delivery_eta)
            reasons.append(f"estimated arrival within deadline ({fmt_duration(slack)} slack)")
        else:
            reasons.append(f"deadline at risk — est. {fmt_duration(best.lateness)} late; best available option")
        reasons.append(f"capacity {len(robot.active_orders)}/{robot.capacity} after assignment")
        return reasons

    def _note_waiting(self, order: Order, evals: list[CandidateEvaluation], ctx: AgentContext) -> None:
        counts = Counter((e.rejection or "").split(" (")[0] for e in evals)
        summary = ", ".join(f"{n} {reason}" for reason, n in counts.most_common())
        previous = self._waiting_notes.get(order.id)
        # Explain why an order waits once, then at most every WAIT_NOTE_INTERVAL_S.
        if previous is not None and (previous[0] == summary or ctx.now - previous[1] < WAIT_NOTE_INTERVAL_S):
            return
        self._waiting_notes[order.id] = (summary, ctx.now)
        ctx.timeline.add(Category.ALLOCATION, "NO_ELIGIBLE_ROBOT",
                         f"{order.id} ({order.priority.label}) queued — no eligible robot: {summary}",
                         severity=Severity.WARNING if order.priority >= Priority.HIGH else Severity.INFO,
                         order_id=order.id,
                         data={"rejected": [{"reason": k, "count": v} for k, v in counts.most_common()]})

    def _try_preempt(self, order: Order, ctx: AgentContext, robots: list[RobotAgent], now: float,
                     best: CandidateEvaluation | None) -> bool:
        options: list[tuple[CandidateEvaluation, RobotAgent, Order]] = []
        for robot in robots:
            if robot.status not in (RobotStatus.EN_ROUTE, RobotStatus.PLANNING, RobotStatus.ASSIGNED,
                                    RobotStatus.REPLANNING):
                continue
            if robot.low_battery_mode or not robot.stops or robot.stops[0].kind != StopKind.PICKUP:
                continue
            victim = ctx.orders.get(robot.stops[0].order_id or "")
            if victim is None or victim.priority >= Priority.HIGH:
                continue
            if len(robot.active_orders) > robot.capacity:  # victim frees one slot
                continue
            hypothetical = Commitment(robot.anchor, 0.0, 0.0, len(robot.carrying))
            saved_orders = robot.active_orders
            robot.active_orders = [o for o in saved_orders if o != victim.id]
            try:
                ev = evaluate(robot, order, ctx, now, hypothetical)
            finally:
                robot.active_orders = saved_orders
            if ev.eligible:
                options.append((ev, robot, victim))
        if not options:
            return False
        options.sort(key=lambda o: (o[0].score, o[1].id))
        ev, robot, victim = options[0]
        baseline = best.delivery_eta if best else float("inf")
        if ev.delivery_eta + PREEMPTION_MIN_GAIN_S >= baseline:
            return False

        robot.release(victim.id, ctx, f"preempted by CRITICAL {order.id}")
        victim.status = OrderStatus.PENDING
        victim.assigned_robot = None
        victim.log(now, f"preempted from {robot.id} by {order.id}")
        self.preemptions += 1
        gain = "no free robot could serve it" if best is None else \
            f"{fmt_duration(baseline - ev.delivery_eta)} sooner than best free robot ({best.robot_id})"
        ctx.timeline.add(Category.ALLOCATION, "PREEMPTION",
                         f"{robot.id} preempted: {victim.id} ({victim.priority.label}) returned to queue to serve "
                         f"CRITICAL {order.id} — {gain}",
                         severity=Severity.WARNING, robot_id=robot.id, order_id=order.id,
                         data={"victim": victim.id, "delivery_eta": round(ev.delivery_eta, 1),
                               "baseline_eta": None if best is None else round(baseline, 1)})
        self._commit(order, robot, ev, [ev] + ([best] if best else []), [ev], ctx, now, preempted=victim)
        return True
