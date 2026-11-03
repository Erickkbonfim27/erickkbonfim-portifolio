// Street layers for the space-syntax map: GeoJSON lines, projected and classed.

type Line = [number, number][];
interface Feature {
  geometry: { type: string; coordinates: unknown } | null;
  properties: Record<string, unknown> | null;
}

/** Classes, coloured like depthmapX's blue-to-red spectral scale. */
export const BINS = 10;
export const WIDTH = 1000;

export interface Street {
  line: Line;
  name: string;
  values: Record<string, number>;
}

export function readStreets(layer: unknown, keys: string[]): Street[] {
  const features = (layer as { features?: Feature[] } | null)?.features ?? [];
  const streets: Street[] = [];
  for (const feature of features) {
    const geometry = feature.geometry;
    const lines = geometry?.type === "LineString" ? [geometry.coordinates] : geometry?.type === "MultiLineString" ? (geometry.coordinates as unknown[]) : [];
    const values: Record<string, number> = {};
    for (const key of keys) {
      const value = feature.properties?.[key];
      if (typeof value === "number") values[key] = value;
    }
    const name = typeof feature.properties?.name === "string" ? feature.properties.name : "";
    for (const line of lines) if (Array.isArray(line) && line.length > 1) streets.push({ line: line as Line, name, values });
  }
  return streets;
}

/** Equirectangular projection, corrected for latitude: fine at city scale. */
export function project(streets: Street[]) {
  const points = streets.flatMap((street) => street.line);
  const lons = points.map((p) => p[0]);
  const lats = points.map((p) => p[1]);
  const [minLon, maxLon, minLat, maxLat] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)];
  const k = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
  const scale = WIDTH / Math.max((maxLon - minLon) * k, 1e-9);
  const height = Math.max(1, Math.round((maxLat - minLat) * scale));
  const point = ([lon, lat]: [number, number]): [number, number] => [(lon - minLon) * k * scale, (maxLat - lat) * scale];
  const path = (line: Line) =>
    `M${line
      .map(point)
      .map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`)
      .join("L")}`;
  return { height, point, path };
}

/** Each street's class by rank (deciles): an outlier cannot wash out the rest of the scale. */
export function classes(streets: Street[], key: string): (number | null)[] {
  const ranked = streets
    .map((street, index) => ({ index, value: street.values[key] }))
    .filter((item): item is { index: number; value: number } => item.value !== undefined)
    .sort((a, b) => a.value - b.value);
  const out: (number | null)[] = streets.map(() => null);
  ranked.forEach((item, rank) => {
    out[item.index] = Math.min(BINS - 1, Math.floor((rank / ranked.length) * BINS));
  });
  return out;
}

/** The share of streets below this one, as a whole percentile. */
export function percentile(streets: Street[], key: string, value: number): number {
  const known = streets.filter((street) => street.values[key] !== undefined);
  const below = known.filter((street) => (street.values[key] ?? 0) < value).length;
  return Math.round((below / Math.max(known.length, 1)) * 100);
}

export interface Label {
  name: string;
  x: number;
  y: number;
}

/** The top streets by their best value, each labelled at the middle of its longest stretch. */
export function topStreets(streets: Street[], key: string, point: (p: [number, number]) => [number, number], count = 5): Label[] {
  const best = new Map<string, { value: number; street: Street; length: number }>();
  for (const street of streets) {
    const value = street.values[key];
    if (!street.name || value === undefined) continue;
    const [a, b] = [point(street.line[0] as [number, number]), point(street.line.at(-1) as [number, number])];
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    const current = best.get(street.name);
    if (!current || value > current.value || (value === current.value && length > current.length)) {
      best.set(street.name, { value, street, length });
    }
  }
  return [...best.entries()]
    .sort((a, b) => b[1].value - a[1].value)
    .slice(0, count)
    .map(([name, { street }]) => {
      const [a, b] = [point(street.line[0] as [number, number]), point(street.line.at(-1) as [number, number])];
      return { name, x: (a[0] + b[0]) / 2, y: (a[1] + b[1]) / 2 };
    });
}

/** Labels that would overlap an earlier (higher-ranked) one are left off the map. */
export function spaced(labels: Label[], width = 220, height = 28): Label[] {
  const kept: Label[] = [];
  for (const label of labels) {
    if (kept.every((other) => Math.abs(other.x - label.x) > width || Math.abs(other.y - label.y) > height)) kept.push(label);
  }
  return kept;
}
