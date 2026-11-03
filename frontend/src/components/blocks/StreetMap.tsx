import { useEffect, useMemo, useState, type PointerEvent } from "react";
import type { BlockData } from "../../api/types";
import { useI18n } from "../../i18n";
import { BINS, WIDTH, classes, percentile, project, readStreets, spaced, topStreets } from "../../lib/streets";
import { useInView } from "../../lib/useInView";

type Data = BlockData["map"];

interface Hover {
  index: number;
  x: number;
  y: number;
}

export function StreetMap({ data }: { data: Data }) {
  const { t } = useI18n();
  const [ref, seen] = useInView<HTMLElement>(0.25);
  const [layer, setLayer] = useState<unknown>(null);
  const [failed, setFailed] = useState(false);
  const [metricKey, setMetricKey] = useState(data.metrics[0]?.key ?? "");
  const [hover, setHover] = useState<Hover | null>(null);
  const metric = data.metrics.find((m) => m.key === metricKey) ?? data.metrics[0];

  useEffect(() => {
    if (!seen) return;
    const controller = new AbortController();
    fetch(data.src, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then(setLayer, () => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [seen, data.src]);

  const keys = data.metrics.map((m) => m.key).join(",");
  const streets = useMemo(() => (layer ? readStreets(layer, keys.split(",")) : []), [layer, keys]);
  const view = useMemo(() => (streets.length ? project(streets) : null), [streets]);
  const classed = useMemo(() => classes(streets, metricKey), [streets, metricKey]);
  // One group per class, lowest first, so the most integrated streets are drawn on top.
  const groups = useMemo(() => {
    if (!view) return [];
    const bins = Array.from({ length: BINS }, () => [] as { index: number; d: string }[]);
    classed.forEach((bin, index) => {
      const street = streets[index];
      if (bin !== null && street) bins[bin]?.push({ index, d: view.path(street.line) });
    });
    return bins;
  }, [classed, streets, view]);
  const labels = useMemo(() => (view ? topStreets(streets, metricKey, view.point) : []), [streets, metricKey, view]);

  const hovered = hover ? streets[hover.index] : undefined;
  const hoveredValue = hovered?.values[metricKey];

  const onMove = (event: PointerEvent<SVGSVGElement>) => {
    const index = (event.target as SVGElement).dataset?.i;
    const box = event.currentTarget.getBoundingClientRect();
    setHover(index === undefined ? null : { index: Number(index), x: event.clientX - box.left, y: event.clientY - box.top });
  };

  return (
    <figure ref={ref} className="blk-map card dark">
      <div className="map-head">
        {data.metrics.length > 1 && (
          <div className="map-toggle" role="group">
            {data.metrics.map((m) => (
              <button key={m.key} type="button" aria-pressed={metricKey === m.key} onClick={() => setMetricKey(m.key)}>
                {m.label}
              </button>
            ))}
          </div>
        )}
        <span className="map-legend mono" aria-hidden="true">
          {metric?.low ?? data.legend?.low}
          <span className="map-ramp" />
          {metric?.high ?? data.legend?.high}
        </span>
      </div>
      {metric?.note && <p className="map-note">{metric.note}</p>}
      <div className="map-stage">
        {view ? (
          <svg
            key={metricKey}
            className="map-svg"
            viewBox={`0 0 ${WIDTH} ${view.height}`}
            role="img"
            aria-label={[metric?.label, data.caption].filter(Boolean).join(". ")}
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
          >
            {groups.map((paths, bin) => (
              <g key={bin} className={`mb mb-${bin}`} style={{ animationDelay: `${bin * 120}ms` }}>
                {paths.map(({ index, d }) => (
                  <path key={index} d={d} data-i={index} className={hover?.index === index ? "hot" : undefined} />
                ))}
              </g>
            ))}
            {spaced(labels).map((label) => (
              <text key={label.name} x={label.x} y={label.y} className="map-label" textAnchor="middle">
                {label.name}
              </text>
            ))}
          </svg>
        ) : (
          <p className="map-status mono" role={failed ? "alert" : "status"}>
            {failed ? t.blocks.mapError : t.blocks.mapLoading}
          </p>
        )}
        {hover && hovered && hoveredValue !== undefined && (
          <div className="map-tip" style={{ left: hover.x, top: hover.y }} role="status">
            <strong>{hovered.name || t.blocks.unnamedStreet}</strong>
            <span className="mono">{t.blocks.percentile(metric?.label ?? "", percentile(streets, metricKey, hoveredValue))}</span>
          </div>
        )}
        {labels.length > 0 && (
          <div className="map-top">
            <span className="label mono">{t.blocks.topStreets}</span>
            <ol>
              {labels.map((label) => (
                <li key={label.name}>{label.name}</li>
              ))}
            </ol>
          </div>
        )}
      </div>
      <figcaption>
        {data.caption && <span>{data.caption}</span>}
        <span className="mono map-attr">{data.attribution}</span>
      </figcaption>
    </figure>
  );
}
