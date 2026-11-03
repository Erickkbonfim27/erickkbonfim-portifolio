# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26", "scipy>=1.11"]
# ///
"""Angular segment analysis (space syntax) of an OpenStreetMap street network.

Fetches the streets within a radius of a point from the Overpass API, builds a
segment map and computes angular integration and angular choice, following the
method implemented in depthmapX (Turner 2001, 2007; Hillier & Iida 2005):

1. **Segments.** OSM ways are split at every junction (a node shared by two or
   more ways, or a way end). Each junction-to-junction chain is simplified with
   Douglas-Peucker (default 1 m) to drop digitising jitter, then split at every
   remaining vertex, so each segment is a straight line.
2. **Graph.** Segments are adjacent when they share an endpoint. Moving from one
   to the next costs the turn angle / 90 degrees: 0 straight on, 1 for a right
   angle, 2 for a U-turn. Each segment is modelled as two directed states (one
   per direction of travel) so a path cannot reverse inside a segment.
3. **Measures.** From every segment, a least-angle (Dijkstra) search gives the
   angular total depth TD and node count NC of every other segment:
   - integration, normalised as NAIN = NC^1.2 / (TD + 2);
   - choice (how many least-angle paths pass through a segment), normalised as
     NACH = log(CH + 1) / log(TD + 3) (Hillier, Yang & Turner 2012).
   Both are computed at radius n (the whole network) and, optionally, at a
   metric radius: only segments within that walking distance (midpoint to
   midpoint, along the shortest metric route) take part in each search. The
   network is analysed over the study radius plus a buffer ring (default: the
   local radius) to limit edge effects, and only the study area is written out.
4. **Output.** A GeoJSON LineString per segment, each measure min-max rescaled
   to 0..1 for direct use as a colour ramp.

Simplifications versus depthmapX: exact angles instead of 1024 angular bins,
shortest-path ties broken arbitrarily (one predecessor per segment), and dual
carriageways kept as two parallel lines as they are mapped in OSM.

Usage:
    uv run tools/space_syntax.py --lat -27.0977 --lon -48.9175 --radius 2500 --out map.geojson
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra

OVERPASS_URLS = (  # main instance first, then public mirrors if it is busy
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
RETRY_CODES = {429, 502, 503, 504}  # Overpass is busy: back off and retry
USER_AGENT = "erickkbonfim-portfolio/space_syntax.py (research; one query per run)"
HIGHWAYS = (
    "motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link"
    "|tertiary|tertiary_link|unclassified|residential|living_street|pedestrian"
)
EARTH_RADIUS = 6_371_008.8
EPS = 1e-9  # keeps zero-cost turns as explicit graph edges


# --------------------------------------------------------------------------- data


def fetch_osm(lat: float, lon: float, radius: float, cache: Path | None) -> dict:
    """Return the Overpass JSON for street ways around a point (cached if asked)."""
    if cache and cache.exists():
        return json.loads(cache.read_text())
    query = (
        f"[out:json][timeout:120];"
        f'way["highway"~"^({HIGHWAYS})$"]["area"!="yes"](around:{radius},{lat},{lon});'
        f"(._;>;);out body qt;"
    )
    body = urllib.parse.urlencode({"data": query}).encode()
    attempts = 6
    for attempt in range(attempts):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        request = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                data = json.load(response)
            break
        except (urllib.error.URLError, TimeoutError) as error:
            busy = not isinstance(error, urllib.error.HTTPError) or error.code in RETRY_CODES
            if not busy or attempt == attempts - 1:
                raise
            wait = 10 * 2**attempt  # exponential backoff, as Overpass asks
            print(f"{url} unavailable ({error}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    if cache:
        cache.write_text(json.dumps(data))
    return data


@dataclass
class Network:
    """Straight street segments, in local metres and in lon/lat."""

    a: np.ndarray  # (N, 2) start point, metres east/north of the centre
    b: np.ndarray  # (N, 2) end point
    a_node: np.ndarray  # (N,) OSM node id at the start
    b_node: np.ndarray  # (N,) OSM node id at the end
    lonlat: np.ndarray  # (N, 2, 2) start and end as lon/lat
    name: np.ndarray  # (N,) street name, "" if unnamed

    @property
    def length(self) -> np.ndarray:
        return np.linalg.norm(self.b - self.a, axis=1)

    def subset(self, keep: np.ndarray) -> Network:
        return Network(*(field[keep] for field in vars(self).values()))


def douglas_peucker(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Indices of the vertices kept by Douglas-Peucker simplification."""
    keep = np.zeros(len(points), dtype=bool)
    keep[[0, -1]] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        start, end = points[i], points[j]
        direction = end - start
        norm = np.hypot(*direction)
        inner = points[i + 1 : j] - start
        if norm == 0:
            dist = np.hypot(inner[:, 0], inner[:, 1])
        else:
            dist = np.abs(direction[0] * inner[:, 1] - direction[1] * inner[:, 0]) / norm
        k = int(np.argmax(dist))
        if dist[k] > tolerance:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return np.flatnonzero(keep)


def build_network(osm: dict, lat: float, lon: float, radius: float, tolerance: float) -> Network:
    """Split OSM ways into straight segments, clipped to the radius."""
    lat0, lon0 = math.radians(lat), math.radians(lon)
    lonlat: dict[int, tuple[float, float]] = {}
    ways = []
    for element in osm["elements"]:
        if element["type"] == "node":
            lonlat[element["id"]] = (element["lon"], element["lat"])
        elif element["type"] == "way":
            ways.append(element)

    def project(node: int) -> tuple[float, float]:
        x, y = lonlat[node]
        return (
            EARTH_RADIUS * math.cos(lat0) * (math.radians(x) - lon0),
            EARTH_RADIUS * (math.radians(y) - lat0),
        )

    # Junctions: nodes used more than once across all ways, plus way ends.
    uses: dict[int, int] = defaultdict(int)
    for way in ways:
        for node in way["nodes"]:
            uses[node] += 1
        uses[way["nodes"][0]] += 1
        uses[way["nodes"][-1]] += 1

    # Each junction-to-junction chain is simplified, then split at its vertices.
    ends: list[tuple[int, int]] = []
    names: list[str] = []
    for way in ways:
        nodes = [n for n in way["nodes"] if n in lonlat]
        name = way.get("tags", {}).get("name", "")
        cuts = [i for i, n in enumerate(nodes) if uses[n] > 1 or i in (0, len(nodes) - 1)]
        for start, end in pairwise(cuts):
            ids = nodes[start : end + 1]
            kept = douglas_peucker(np.array([project(n) for n in ids]), tolerance)
            for p, q in pairwise(kept):
                if lonlat[ids[p]] != lonlat[ids[q]]:
                    ends.append((ids[p], ids[q]))
                    names.append(name)

    a_node, b_node = np.array(ends).T
    a = np.array([project(n) for n in a_node])
    b = np.array([project(n) for n in b_node])
    net = Network(
        a=a,
        b=b,
        a_node=a_node,
        b_node=b_node,
        lonlat=np.array([[lonlat[p], lonlat[q]] for p, q in ends]),
        name=np.array(names, dtype=object),
    )
    midpoint = (a + b) / 2
    return net.subset(np.hypot(midpoint[:, 0], midpoint[:, 1]) <= radius)


# -------------------------------------------------------------------------- graph


def directed_graphs(net: Network) -> tuple[csr_matrix, csr_matrix]:
    """Angular and metric graphs over directed segment states.

    State 2i walks segment i from a to b, state 2i+1 from b to a. An edge links a
    state leaving a node to every state of another segment entering that node.
    """
    n = len(net.a)
    unit = (net.b - net.a) / net.length[:, None]
    half = net.length / 2
    leaving: dict[int, list[tuple[int, np.ndarray]]] = defaultdict(list)
    entering: dict[int, list[tuple[int, np.ndarray]]] = defaultdict(list)
    for i in range(n):
        leaving[net.b_node[i]].append((2 * i, unit[i]))
        entering[net.a_node[i]].append((2 * i, unit[i]))
        leaving[net.a_node[i]].append((2 * i + 1, -unit[i]))
        entering[net.b_node[i]].append((2 * i + 1, -unit[i]))

    rows, cols, turn = [], [], []
    for node, outs in leaving.items():
        for s, heading_out in outs:
            for t, heading_in in entering.get(node, ()):
                if s // 2 != t // 2:
                    rows.append(s)
                    cols.append(t)
                    turn.append(float(np.clip(heading_out @ heading_in, -1.0, 1.0)))
    rows, cols = np.array(rows), np.array(cols)
    angular = np.degrees(np.arccos(turn)) / 90.0 + EPS
    metric = half[rows // 2] + half[cols // 2]
    shape = (2 * n, 2 * n)
    return (
        csr_matrix((angular, (rows, cols)), shape=shape),
        csr_matrix((metric, (rows, cols)), shape=shape),
    )


def largest_component(net: Network) -> Network:
    """Keep only the largest connected piece of the network."""
    nodes, inverse = np.unique(np.concatenate([net.a_node, net.b_node]), return_inverse=True)
    n = len(net.a)
    seg = np.arange(n)
    # Bipartite segment/node graph: segments 0..n-1, nodes n..n+len(nodes)-1.
    rows = np.concatenate([seg, seg])
    cols = n + inverse
    graph = csr_matrix((np.ones(2 * n), (rows, cols)), shape=(n + len(nodes),) * 2)
    _, labels = connected_components(graph, directed=False)
    return net.subset(labels[:n] == np.bincount(labels[:n]).argmax())


# ----------------------------------------------------------------------- analysis


def subtree_sums(parent: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Sum of `weight` over each node's subtree in a shortest-path forest.

    `parent` is Dijkstra's predecessor array (negative for roots and unreached
    nodes). Depths come from pointer jumping, then sums are pushed up level by
    level, deepest first, so every step is a vectorised numpy call.
    """
    n = len(parent)
    root = parent < 0
    parent = np.where(root, np.arange(n), parent)
    depth = (~root).astype(np.int64)
    jump = parent.copy()
    while not np.array_equal(jump, jump[jump]):
        depth, jump = depth + depth[jump], jump[jump]
    total = weight.astype(np.float64).copy()
    order = np.argsort(-depth, kind="stable")
    levels = np.cumsum(np.bincount(depth)[::-1])[:-1]  # boundaries, deepest level first
    for chunk in np.split(order, levels):
        if len(chunk) and depth[chunk[0]] > 0:
            np.add.at(total, parent[chunk], total[chunk])
    return total


def least_angle_run(
    angular: csr_matrix, sources: np.ndarray, n_segments: int, segment_of: np.ndarray
) -> tuple[int, float, np.ndarray]:
    """One search from both states of a segment: NC, TD and choice increments.

    `segment_of` maps each state of `angular` to its segment index (0..n_segments-1).
    """
    dist, pred, _ = dijkstra(angular, indices=sources, min_only=True, return_predecessors=True)
    seg_dist = np.full(n_segments, np.inf)
    np.minimum.at(seg_dist, segment_of, dist)
    reached = np.isfinite(seg_dist)
    origin = segment_of[sources[0]]
    node_count = int(reached.sum()) - 1
    total_depth = float(seg_dist[reached].sum())

    # Each destination segment is reached through its closer state (one per segment).
    best = np.flatnonzero(np.isfinite(dist) & (dist <= seg_dist[segment_of]))
    _, first = np.unique(segment_of[best], return_index=True)
    target = np.zeros(len(dist))
    target[best[first]] = 1.0
    target[segment_of == origin] = 0.0

    through = subtree_sums(pred, target) - target
    through[sources] = 0.0
    choice = np.bincount(segment_of, weights=through, minlength=n_segments)
    return node_count, total_depth, choice


def analyse(
    angular: csr_matrix, metric: csr_matrix, radius: float | None, label: str
) -> tuple[np.ndarray, np.ndarray]:
    """NAIN and NACH per segment at radius n (`radius=None`) or a metric radius."""
    n = angular.shape[0] // 2
    segment_of_all = np.arange(2 * n) // 2
    nc, td, choice = np.zeros(n), np.zeros(n), np.zeros(n)
    started = time.perf_counter()
    for i in range(n):
        sources = np.array([2 * i, 2 * i + 1])
        if radius is None:
            nc[i], td[i], inc = least_angle_run(angular, sources, n, segment_of_all)
            choice += inc
        else:
            reach = dijkstra(metric, indices=sources, min_only=True, limit=radius)
            states = np.flatnonzero(np.isfinite(reach))
            local = angular[states][:, states]
            segments, segment_of = np.unique(states // 2, return_inverse=True)
            local_sources = np.searchsorted(states, sources)
            nc[i], td[i], inc = least_angle_run(local, local_sources, len(segments), segment_of)
            choice[segments] += inc
        if (i + 1) % max(1, n // 10) == 0:
            elapsed = time.perf_counter() - started
            print(f"  {label}: {i + 1}/{n} segments, {elapsed:.0f}s", file=sys.stderr)
    nain = np.where(td > 0, nc**1.2 / (td + 2), 0.0)
    nach = np.log(choice + 1) / np.log(td + 3)
    return nain, nach


# ------------------------------------------------------------------------- output


def rescale(values: np.ndarray) -> np.ndarray:
    low, high = float(values.min()), float(values.max())
    return np.zeros_like(values) if high == low else (values - low) / (high - low)


def to_geojson(net: Network, measures: dict[str, np.ndarray], metadata: dict) -> dict:
    """One LineString per segment, measures min-max rescaled to 0..1."""
    scaled = {key: rescale(values) for key, values in measures.items()}
    features = []
    for i in range(len(net.a)):
        properties = {key: round(float(values[i]), 3) for key, values in scaled.items()}
        if net.name[i]:
            properties["name"] = net.name[i]
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[round(x, 5), round(y, 5)] for x, y in net.lonlat[i]],
                },
                "properties": properties,
            }
        )
    return {
        "type": "FeatureCollection",
        "attribution": "© OpenStreetMap contributors, ODbL",
        "metadata": metadata,
        "features": features,
    }


def top_streets(net: Network, values: np.ndarray, count: int = 10, min_length: float = 200.0):
    """Named streets ranked by the length-weighted mean of a measure."""
    total, weighted = defaultdict(float), defaultdict(float)
    for name, length, value in zip(net.name, net.length, values, strict=True):
        if name:
            total[name] += length
            weighted[name] += value * length
    ranked = sorted((weighted[k] / total[k], k, total[k]) for k in total if total[k] >= min_length)
    return ranked[::-1][:count]


# --------------------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--radius", type=float, default=2500, help="study area radius, metres")
    parser.add_argument("--local-radius", type=float, default=800, help="0 to skip, metres")
    parser.add_argument(
        "--buffer", type=float, help="extra ring analysed but not output (default: local radius)"
    )
    parser.add_argument("--simplify", type=float, default=1.0, help="Douglas-Peucker, metres")
    parser.add_argument("--cache", type=Path, help="reuse/save the raw Overpass response")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    buffer = args.local_radius if args.buffer is None else args.buffer
    extent = args.radius + buffer

    started = time.perf_counter()
    osm = fetch_osm(args.lat, args.lon, extent, args.cache)
    net = largest_component(build_network(osm, args.lat, args.lon, extent, args.simplify))
    angular, metric = directed_graphs(net)
    print(f"{len(net.a)} segments analysed, {angular.nnz} directed turns", file=sys.stderr)

    measures = {}
    measures["nain"], measures["nach"] = analyse(angular, metric, None, "radius n")
    if args.local_radius > 0:
        r = int(args.local_radius)
        measures[f"nain_r{r}"], measures[f"nach_r{r}"] = analyse(
            angular, metric, args.local_radius, f"radius {r} m"
        )

    # The buffer ring only shields the study area from edge effects; drop it now.
    midpoint = (net.a + net.b) / 2
    inside = np.hypot(midpoint[:, 0], midpoint[:, 1]) <= args.radius
    net = net.subset(inside)
    measures = {key: values[inside] for key, values in measures.items()}

    metadata = {
        "centre": {"lat": args.lat, "lon": args.lon},
        "radius_m": args.radius,
        "buffer_m": buffer,
        "segment_count": len(net.a),
        "date": datetime.now(UTC).date().isoformat(),
        "source": "OpenStreetMap via Overpass API",
        "method": (
            "Angular segment analysis (Turner 2007): OSM streets split at junctions and "
            f"vertices (Douglas-Peucker {args.simplify:g} m), turn cost = angle/90 deg. "
            "nain = NC^1.2/(TD+2), nach = log(CH+1)/log(TD+3) (Hillier, Yang & Turner 2012), "
            "at radius n and, if present, *_rN within an N-metre network radius. Computed on "
            "radius + buffer to limit edge effects; one feature per segment inside radius; "
            "values min-max rescaled to 0..1."
        ),
    }
    collection = to_geojson(net, measures, metadata)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(collection, ensure_ascii=False, separators=(",", ":")))

    elapsed = time.perf_counter() - started
    size = args.out.stat().st_size / 1e6
    print(
        f"\nwrote {args.out} ({size:.2f} MB, {len(net.a)} segments) in {elapsed:.0f}s",
        file=sys.stderr,
    )
    for key, values in measures.items():
        print(f"\ntop streets by {key}:", file=sys.stderr)
        for value, name, length in top_streets(net, values):
            print(f"  {value:8.3f}  {name} ({length:.0f} m)", file=sys.stderr)


if __name__ == "__main__":
    main()
