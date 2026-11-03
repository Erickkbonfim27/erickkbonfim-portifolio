import { useState } from "react";
import type { BlockData } from "../../api/types";
import { useI18n } from "../../i18n";
import { useInView } from "../../lib/useInView";

type Data = BlockData["diagram"];
type Node = Data["nodes"][number];
type Box = { x: number; y: number; w: number; h: number };

const NODE_W = 200;
const NODE_H = 64;

function box(node: Node): Box {
  return { x: node.x, y: node.y, w: node.w ?? NODE_W, h: node.h ?? NODE_H };
}

/** Where the line between two box centres leaves the first box. */
function exit(from: Box, to: Box): [number, number] {
  const [cx, cy] = [from.x + from.w / 2, from.y + from.h / 2];
  const [dx, dy] = [to.x + to.w / 2 - cx, to.y + to.h / 2 - cy];
  if (dx === 0 && dy === 0) return [cx, cy];
  const scale = Math.min(dx ? from.w / 2 / Math.abs(dx) : Infinity, dy ? from.h / 2 / Math.abs(dy) : Infinity);
  return [cx + dx * scale, cy + dy * scale];
}

/** Width of the pill behind an edge label, from its length in the 11px mono font. */
function labelWidth(label: string): number {
  return label.length * 6.8 + 18;
}

function inside(inner: Box, outer: Box): boolean {
  return inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.w <= outer.x + outer.w && inner.y + inner.h <= outer.y + outer.h;
}

/** Which nodes a step highlights: the ones it names, and every node inside a group it names. */
function focused(data: Data, focus: string[] | undefined): Set<string> | null {
  if (!focus || focus.length === 0) return null;
  const groups = (data.groups ?? []).filter((group) => focus.includes(group.id));
  return new Set(
    data.nodes.filter((node) => focus.includes(node.id) || groups.some((group) => inside(box(node), group))).map((node) => node.id),
  );
}

function Canvas({ data, lit, drawn }: { data: Data; lit: Set<string> | null; drawn: boolean }) {
  const { t } = useI18n();
  const boxes = new Map(data.nodes.map((node) => [node.id, box(node)]));
  const dim = (id: string) => lit !== null && !lit.has(id);
  return (
    <svg
      className={`dg-svg${drawn ? " drawn" : ""}`}
      viewBox={`0 0 ${data.width} ${data.height}`}
      role="img"
      aria-label={data.title ?? t.blocks.diagram}
    >
      <defs>
        <marker id="dg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" className="dg-arrowhead" />
        </marker>
      </defs>
      {(data.groups ?? []).map((group) => (
        <g key={group.id} className={`dg-group tone-${group.tone ?? "default"}`}>
          <rect x={group.x} y={group.y} width={group.w} height={group.h} rx="18" />
          <text x={group.x + 16} y={group.y + 24} className="dg-group-label">
            {group.label}
          </text>
        </g>
      ))}
      {(data.edges ?? []).map((edge, index) => {
        const [a, b] = [boxes.get(edge.from), boxes.get(edge.to)];
        if (!a || !b) return null;
        const [x1, y1] = exit(a, b);
        const [x2, y2] = exit(b, a);
        const path = `M${x1.toFixed(1)} ${y1.toFixed(1)} L${x2.toFixed(1)} ${y2.toFixed(1)}`;
        const off = dim(edge.from) || dim(edge.to);
        return (
          <g key={`${edge.from}-${edge.to}-${index}`} className={`dg-edge${edge.dashed ? " dashed" : ""}${off ? " dim" : ""}`} style={{ "--i": index } as React.CSSProperties}>
            <path d={path} pathLength={1} markerEnd="url(#dg-arrow)" />
            {edge.flow && !off && (
              <circle r="4.5" className="dg-packet">
                <animateMotion dur={`${2 + (index % 3) * 0.6}s`} repeatCount="indefinite" path={path} />
              </circle>
            )}
            {edge.label && (
              <g className="dg-edge-tag">
                <rect x={(x1 + x2) / 2 - labelWidth(edge.label) / 2} y={(y1 + y2) / 2 - 11} width={labelWidth(edge.label)} height={22} rx={11} />
                <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 + 4} className="dg-edge-label" textAnchor="middle">
                  {edge.label}
                </text>
              </g>
            )}
          </g>
        );
      })}
      {data.nodes.map((node, index) => {
        const b = box(node);
        return (
          <g
            key={node.id}
            className={`dg-node tone-${node.tone ?? "default"}${dim(node.id) ? " dim" : ""}${lit?.has(node.id) ? " lit" : ""}`}
            style={{ "--i": index } as React.CSSProperties}
          >
            <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="14" />
            <text x={b.x + b.w / 2} y={b.y + (node.sub ? b.h / 2 - 4 : b.h / 2 + 5)} textAnchor="middle" className="dg-label">
              {node.label}
            </text>
            {node.sub && (
              <text x={b.x + b.w / 2} y={b.y + b.h / 2 + 15} textAnchor="middle" className="dg-sub">
                {node.sub}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function Diagram({ data }: { data: Data }) {
  const { t } = useI18n();
  const steps = data.steps ?? [];
  const [ref, seen] = useInView<HTMLDivElement>(0.15);
  // -1 is the overview: everything lit. The steps are walked with the buttons or the dots.
  const [active, setActive] = useState(-1);
  const step = steps[active];
  const lit = step ? focused(data, step.focus) : null;
  return (
    <div ref={ref} className="blk-diagram">
      <figure className="dg-figure">
        {data.title && <figcaption className="label mono">{data.title}</figcaption>}
        <div className="dg-scroll">
          <Canvas data={data} lit={lit} drawn={seen} />
        </div>
        {steps.length > 0 && (
          <div className="dg-stepper">
            <div className="dg-step" aria-live="polite">
              <span className="mono dg-step-n">{step ? t.blocks.step(active + 1, steps.length) : t.blocks.overview}</span>
              <h3>{step ? step.title : t.blocks.overviewTitle}</h3>
              <p>{step ? step.text : t.blocks.overviewText(steps.length)}</p>
            </div>
            <div className="dg-controls">
              <button type="button" className="arrowbtn" aria-label={t.blocks.previousStep} disabled={active < 0} onClick={() => setActive(active - 1)}>
                ←
              </button>
              <div className="dg-dots">
                {steps.map((item, index) => (
                  <button
                    key={item.title}
                    type="button"
                    className="dg-dot"
                    aria-label={`${t.blocks.step(index + 1, steps.length)}: ${item.title}`}
                    aria-current={index === active ? "step" : undefined}
                    onClick={() => setActive(index)}
                  />
                ))}
              </div>
              <button
                type="button"
                className="pillbtn pill-dark sm"
                onClick={() => setActive(active + 1 < steps.length ? active + 1 : -1)}
              >
                {active < 0 ? t.blocks.start : active + 1 < steps.length ? t.blocks.nextStep : t.blocks.restart}
              </button>
            </div>
          </div>
        )}
      </figure>
    </div>
  );
}
