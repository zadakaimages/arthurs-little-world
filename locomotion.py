"""Continuous, collision-aware movement over a coarse navigation grid.

Coordinates are tile centers: integer (x, y) is the center of a grid cell.
The grid chooses a route; actors move along its length at a continuous speed.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Callable

Point = tuple[float, float]
Passable = Callable[[int, int], bool]
BODY_RADIUS = 0.18


def length(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def clear_at(x: float, y: float, passable: Passable, radius: float = BODY_RADIUS) -> bool:
    """Circle against occupied tile rectangles, including map boundaries."""
    if not math.isfinite(x) or not math.isfinite(y):
        return False
    left, right = math.floor(x - radius + .5), math.floor(x + radius + .5)
    top, bottom = math.floor(y - radius + .5), math.floor(y + radius + .5)
    for gy in range(top, bottom + 1):
        for gx in range(left, right + 1):
            if passable(gx, gy):
                continue
            near_x = max(gx - .5, min(x, gx + .5))
            near_y = max(gy - .5, min(y, gy + .5))
            if (near_x - x) ** 2 + (near_y - y) ** 2 < (radius + .001) ** 2:
                return False
    return True


def clear_segment(a: Point, b: Point, passable: Passable, radius: float = BODY_RADIUS) -> bool:
    count = max(1, math.ceil(length(a, b) / .075))
    for i in range(count + 1):
        t = i / count
        if not clear_at(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, passable, radius):
            return False
    return True


def nearest_clear(point: Point, passable: Passable, max_radius: int = 50) -> Point:
    if clear_at(*point, passable):
        return float(point[0]), float(point[1])
    cx, cy = math.floor(point[0] + .5), math.floor(point[1] + .5)
    for radius in range(max_radius + 1):
        candidates = [(x, y) for x in range(cx - radius, cx + radius + 1)
                      for y in range(cy - radius, cy + radius + 1)
                      if max(abs(x - cx), abs(y - cy)) == radius]
        candidates.sort(key=lambda p: length(point, p))
        for candidate in candidates:
            if clear_at(*candidate, passable):
                return float(candidate[0]), float(candidate[1])
    raise ValueError("No clear ground near saved position")


def _round_corners(points: list[Point], passable: Passable) -> list[Point]:
    if len(points) < 3:
        return points
    rounded = [points[0]]
    for i in range(1, len(points) - 1):
        before, corner, after = points[i - 1:i + 2]
        a, b = length(before, corner), length(corner, after)
        if min(a, b) < .05:
            rounded.append(corner)
            continue
        radius = min(.65, a * .23, b * .23)
        entry = (corner[0] + (before[0] - corner[0]) * radius / a,
                 corner[1] + (before[1] - corner[1]) * radius / a)
        leave = (corner[0] + (after[0] - corner[0]) * radius / b,
                 corner[1] + (after[1] - corner[1]) * radius / b)
        curve = [entry]
        for j in range(1, 11):
            t = j / 10
            curve.append(((1-t)**2 * entry[0] + 2*(1-t)*t*corner[0] + t*t*leave[0],
                          (1-t)**2 * entry[1] + 2*(1-t)*t*corner[1] + t*t*leave[1]))
        trial = [rounded[-1], *curve, after]
        if all(clear_segment(p, q, passable) for p, q in zip(trial, trial[1:])):
            rounded.extend(curve)
        else:
            rounded.append(corner)
    rounded.append(points[-1])
    return [p for i, p in enumerate(rounded) if i == 0 or length(rounded[i-1], p) > 1e-5]


def find_route(start: Point, destination: Point, passable: Passable) -> list[Point] | None:
    """A* plus visibility pruning and collision-checked curved corners."""
    start = (float(start[0]), float(start[1]))
    destination = (float(destination[0]), float(destination[1]))
    if not clear_at(*start, passable) or not clear_at(*destination, passable):
        return None
    if clear_segment(start, destination, passable):
        return [start, destination]
    origin = (math.floor(start[0] + .5), math.floor(start[1] + .5))
    goal = (math.floor(destination[0] + .5), math.floor(destination[1] + .5))
    frontier = [(length(origin, goal), 0., origin)]
    cost = {origin: 0.}
    previous = {origin: None}
    directions = [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]
    while frontier:
        _, distance, point = heapq.heappop(frontier)
        if distance > cost[point] + 1e-6:
            continue
        if point == goal:
            break
        for dx, dy in directions:
            nxt = (point[0] + dx, point[1] + dy)
            if not passable(*nxt):
                continue
            if dx and dy and (not passable(point[0] + dx, point[1]) or not passable(point[0], point[1] + dy)):
                continue
            if not clear_segment(point, nxt, passable):
                continue
            candidate = distance + math.hypot(dx, dy)
            if candidate + 1e-8 < cost.get(nxt, float('inf')):
                cost[nxt] = candidate
                previous[nxt] = point
                heapq.heappush(frontier, (candidate + length(nxt, goal), candidate, nxt))
    if goal not in previous:
        return None
    route = [destination]
    cursor = goal
    while cursor is not None:
        route.append((float(cursor[0]), float(cursor[1])))
        cursor = previous[cursor]
    route.append(start)
    route.reverse()
    simplified = [start]
    i = 0
    while i < len(route) - 1:
        j = len(route) - 1
        while j > i + 1 and not clear_segment(simplified[-1], route[j], passable):
            j -= 1
        if not clear_segment(simplified[-1], route[j], passable):
            return None
        if length(simplified[-1], route[j]) > 1e-6:
            simplified.append(route[j])
        i = j
    return _round_corners(simplified, passable)


@dataclass
class Mover:
    x: float
    y: float
    passable: Passable
    cruise: float = 1.35
    acceleration: float = 3.4
    braking: float = 4.0
    speed: float = 0.
    heading: float = math.pi / 2
    distance: float = 0.
    path: list[Point] = field(default_factory=list)
    index: int = 0
    destination: Point | None = None
    vx: float = 0.
    vy: float = 0.

    @property
    def active(self) -> bool:
        return self.index < len(self.path)

    @property
    def facing(self) -> str:
        dx, dy = math.cos(self.heading), math.sin(self.heading)
        return ('right' if dx > 0 else 'left') if abs(dx) > abs(dy) else ('down' if dy > 0 else 'up')

    def set_target(self, target: Point) -> bool:
        route = find_route((self.x, self.y), target, self.passable)
        if route is None:
            return False
        self.path = route[1:]
        self.index = 0
        self.destination = (float(target[0]), float(target[1]))
        return True

    def brake_to_stop(self) -> None:
        """End the current route at its physical stopping distance, without a snap."""
        if not self.active or self.speed < 1e-5:
            self.stop()
            return
        remaining = self.speed**2 / (2*self.braking) + 1e-6
        short_path = []
        anchor = (self.x, self.y)
        for end in self.path[self.index:]:
            segment = length(anchor, end)
            if segment < 1e-9:
                continue
            if remaining <= segment:
                short_path.append((anchor[0]+(end[0]-anchor[0])*remaining/segment,
                                   anchor[1]+(end[1]-anchor[1])*remaining/segment))
                break
            short_path.append(end)
            remaining -= segment
            anchor = end
        if not short_path:
            self.stop()
            return
        self.path = short_path
        self.index = 0
        self.destination = short_path[-1]

    def stop(self) -> None:
        self.path = []
        self.index = 0
        self.destination = None
        self.speed = self.vx = self.vy = 0.

    def remaining(self) -> float:
        if not self.active:
            return 0.
        return length((self.x, self.y), self.path[self.index]) + sum(
            length(a, b) for a, b in zip(self.path[self.index:], self.path[self.index+1:]))

    def _advance(self, dt: float) -> bool:
        if not self.active:
            self.speed = self.vx = self.vy = 0.
            return False
        current = (self.x, self.y)
        remaining = self.remaining()
        if remaining < .0001:
            self.distance += remaining
            self.x, self.y = self.path[-1]
            self.index = len(self.path)
            self.speed = self.vx = self.vy = 0.
            return True
        # Brake for the final stop only. Intermediate navigation nodes never pause.
        # Discrete braking bound includes this substep's travel. This avoids a
        # final snap from a nonzero speed after reaching the stopping point.
        b = self.braking
        discriminant = (b*dt)**2 - 4*b*dt*self.speed + 8*b*remaining
        stop_speed = max(0., (math.sqrt(max(0., discriminant)) - b*dt) * .5)
        desired = min(self.cruise, stop_speed)
        nxt = self.path[self.index]
        angle = math.atan2(nxt[1] - self.y, nxt[0] - self.x)
        change = (angle - self.heading + math.pi) % (2*math.pi) - math.pi
        if abs(change) > .45:
            desired = min(desired, max(.65, self.cruise * (1. - min(1., abs(change)/math.pi) * .55)))
        # Anticipate a bend before entering it, without stopping at path nodes.
        ahead = .75
        anchor = (self.x, self.y)
        future_angle = angle
        for point in self.path[self.index:]:
            segment = length(anchor, point)
            if segment > 1e-7:
                future_angle = math.atan2(point[1]-anchor[1], point[0]-anchor[0])
                ahead -= segment
                if ahead <= 0:break
            anchor = point
        bend = abs((future_angle-angle+math.pi) % (2*math.pi)-math.pi)
        desired = min(desired, self.cruise * (1. - .45*min(1., bend/(math.pi/2))))
        delta = desired - self.speed
        rate = self.acceleration if delta >= 0 else self.braking
        new_speed = self.speed + max(-rate * dt, min(rate * dt, delta))
        travel = (self.speed + new_speed) * .5 * dt
        if new_speed <= 1e-9 and self.speed > 0:
            travel = self.speed**2/(2*self.braking)
        self.speed = new_speed
        travel = min(travel, remaining)
        old_x, old_y = self.x, self.y
        consumed = 0.
        while travel > 1e-9 and self.active:
            end = self.path[self.index]
            dist = length((self.x, self.y), end)
            if dist <= 1e-9:
                self.index += 1
                continue
            part = min(travel, dist)
            self.x += (end[0] - self.x) * part / dist
            self.y += (end[1] - self.y) * part / dist
            consumed += part
            travel -= part
            if part >= dist - 1e-8:
                self.x, self.y = end
                self.index += 1
        self.distance += consumed
        self.vx, self.vy = (self.x - old_x)/dt, (self.y - old_y)/dt
        if consumed > 1e-7:
            actual = math.atan2(self.vy, self.vx)
            delta = (actual - self.heading + math.pi) % (2*math.pi) - math.pi
            self.heading += max(-7.0*dt, min(7.0*dt, delta))
            self.heading = math.atan2(math.sin(self.heading), math.cos(self.heading))
        arrived = not self.active
        if arrived:
            self.speed = self.vx = self.vy = 0.
        return arrived

    def update(self, dt: float) -> bool:
        """Elapsed-time integration; fixed substeps keep 20/30/60 Hz equivalent."""
        remaining = max(0., min(float(dt), .25))
        arrived = False
        while remaining > 1e-9:
            step = min(.0125, remaining)
            arrived = self._advance(step) or arrived
            remaining -= step
        return arrived

    def fields(self) -> dict:
        return {'x': self.x, 'y': self.y, 'vx': self.vx, 'vy': self.vy,
                'speed': self.speed, 'distance': self.distance, 'heading': self.heading,
                'facing': self.facing, 'moving': self.active and self.speed > .02}
