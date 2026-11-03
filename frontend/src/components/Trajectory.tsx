import { useState } from "react";
import type { AgentAnswer, AgentStep } from "../api/types";
import { useI18n } from "../i18n";
import { ms } from "../lib/search";

const NODE_W = 168;
const NODE_H = 34;
const GAP = 52;
// A search opens into its inner steps, drawn as small chips under the node.
const SUB_H = 22;
const SUB_GAP = 40;
const SUB_LABEL: Record<string, string> = {
  "bm25.encode": "bm25 enc",
  "dense.encode": "embed",
  "dense.search": "dense",
  "bm25.search": "bm25",
  "rrf.fuse": "rrf",
};

interface SubStep {
  name: string;
  ms: number;
}

function subSteps(step: AgentStep): SubStep[] {
  const raw = step.detail.steps;
  return Array.isArray(raw) ? (raw.filter((item) => typeof item === "object" && item !== null && "name" in item) as SubStep[]) : [];
}

interface Found {
  n: number;
  title: string;
  heading: string;
  score: number;
}

function isFound(value: unknown): value is Found[] {
  return Array.isArray(value) && value.every((item) => typeof item === "object" && item !== null && "title" in item);
}

/** What a step did, from its detail: the passages it found, the model and its tokens, the checks. */
function Detail({ step }: { step: AgentStep }) {
  const { t } = useI18n();
  const j = t.trajectory;
  const d = step.detail;
  const rows: [string, string][] = [];
  if (typeof d.mode === "string") rows.push([j.labels.mode, `${d.mode} · ${String(d.reason ?? "")}`]);
  if (typeof d.query === "string") rows.push([j.labels.query, d.query]);
  if (typeof d.slug === "string") rows.push([j.labels.slug, d.slug]);
  if (typeof d.model === "string") rows.push([j.labels.model, d.model]);
  if (typeof d.input_tokens === "number") rows.push([j.labels.tokens, `${d.input_tokens} → ${String(d.output_tokens ?? 0)}`]);
  if (Array.isArray(d.tool_calls)) rows.push([j.labels.tools, d.tool_calls.length ? d.tool_calls.join(", ") : j.labels.none]);
  if (typeof d.passed === "boolean") rows.push([j.labels.passed, d.passed ? j.labels.yes : j.labels.no]);
  if (Array.isArray(d.reasons) && d.reasons.length) rows.push([j.labels.reasons, d.reasons.join("; ")]);
  if (typeof d.error === "string") rows.push([j.labels.error, d.error]);
  if (d.skipped === true) rows.push([j.labels.error, j.labels.skipped]);
  const inner = subSteps(step);
  const ranking = (title: string, value: unknown) =>
    isFound(value) && value.length > 0 ? (
      <div className="tj-ranking">
        <span className="label mono">{title}</span>
        <ol className="tj-rank">
          {value.map((item, index) => (
            <li key={`${index}-${item.title}-${item.heading}`}>
              <span>
                <strong>{item.title}</strong>
                {item.heading && ` · ${item.heading}`}
              </span>
              <span className="mono">{item.score.toFixed(3)}</span>
            </li>
          ))}
        </ol>
      </div>
    ) : null;
  return (
    <>
      {inner.length > 0 && (
        <ol className="tj-inner">
          {inner.map((item) => (
            <li key={item.name} className="mono">
              <span>{item.name}</span>
              <span>{ms(item.ms)}</span>
            </li>
          ))}
        </ol>
      )}
      {ranking(j.labels.dense, d.dense)}
      {ranking(j.labels.sparse, d.sparse)}
      {Array.isArray(d.unsupported) && d.unsupported.length > 0 && (
        <ul className="tj-unsupported">
          {d.unsupported.map((claim) => (
            <li key={String(claim)}>{String(claim)}</li>
          ))}
        </ul>
      )}
      {rows.length > 0 && (
        <dl className="tj-kv">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt className="mono">{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {isFound(d.found) &&
        (d.found.length === 0 ? (
          <p className="tj-empty">{j.none}</p>
        ) : (
          <ol className="tj-rank tj-final">
            {d.found.map((item) => (
              <li key={`${item.n}-${item.title}-${item.heading}`}>
                <span>
                  <span className="mono tj-n-ref">[{item.n}]</span> <strong>{item.title}</strong>
                  {item.heading && ` · ${item.heading}`}
                </span>
                <span className="mono">{item.score.toFixed(3)}</span>
              </li>
            ))}
          </ol>
        ))}
    </>
  );
}

function Graph({ steps, selected, running, answered, onSelect }: { steps: AgentStep[]; selected: number; running: boolean; answered: boolean; onSelect: (i: number) => void }) {
  const { t } = useI18n();
  const j = t.trajectory;
  const CX = 150;
  // One column, in the order the agent ran; tool calls step to the side of the model that asked.
  const x = (step: AgentStep) => (step.name.startsWith("tool.") ? CX + 24 : CX);
  const ys: number[] = [24];
  steps.forEach((_step, index) => {
    const before = index === 0 ? 0 : subSteps(steps[index - 1] as AgentStep).length ? SUB_GAP : 0;
    ys.push((ys[index] as number) + GAP + before);
  });
  const lastSubs = steps.length && subSteps(steps[steps.length - 1] as AgentStep).length ? SUB_GAP : 0;
  const end = (ys[steps.length] as number) + GAP + lastSubs;
  const centers = [CX, ...steps.map(x), CX];
  const allY = [...ys, end];
  return (
    <svg className="tj-graph" viewBox={`0 0 300 ${end + 26}`} role="img" aria-label={j.graph}>
      <defs>
        <marker id="tj-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" className="tj-arrowhead" />
        </marker>
      </defs>
      {centers.slice(1).map((cx, i) => {
        if (i === steps.length && !answered) return null;
        const px = centers[i] as number;
        const fromSubs = i > 0 && subSteps(steps[i - 1] as AgentStep).length ? SUB_GAP : 0;
        return (
          <path
            key={i}
            className="tj-edge"
            d={`M${px} ${(allY[i] as number) + NODE_H / 2 + fromSubs} L${cx} ${(allY[i + 1] as number) - NODE_H / 2 - 3}`}
            markerEnd="url(#tj-arrow)"
          />
        );
      })}
      <g className="tj-node edge-node">
        <rect x={CX - NODE_W / 2} y={24 - NODE_H / 2} width={NODE_W} height={NODE_H} rx={NODE_H / 2} />
        <text x={CX} y={28} textAnchor="middle" className="tj-n">
          {j.question}
        </text>
      </g>
      {steps.map((step, index) => {
        const cx = x(step);
        const cy = allY[index + 1] as number;
        const failed = step.detail.passed === false || typeof step.detail.error === "string";
        const live = running && index === steps.length - 1;
        const inner = subSteps(step);
        const chipW = 52;
        const rowW = inner.length * chipW + (inner.length - 1) * 4;
        return (
          <g
            key={`${step.name}-${index}`}
            className={`tj-node${index === selected ? " on" : ""}${failed ? " warn" : ""}${live ? " live" : ""}`}
            role="button"
            tabIndex={0}
            aria-label={`${step.name}, ${ms(step.ms)}`}
            aria-pressed={index === selected}
            onClick={() => onSelect(index)}
            onKeyDown={(event) => (event.key === "Enter" || event.key === " ") && onSelect(index)}
          >
            <rect x={cx - NODE_W / 2} y={cy - NODE_H / 2} width={NODE_W} height={NODE_H} rx="10" />
            <text x={cx - NODE_W / 2 + 10} y={cy + 4} className="tj-n">
              {step.name}
            </text>
            <text x={cx + NODE_W / 2 - 10} y={cy + 4} textAnchor="end" className="tj-m">
              {ms(step.ms)}
            </text>
            {inner.map((sub, k) => {
              const sx = cx - rowW / 2 + k * (chipW + 4);
              const sy = cy + NODE_H / 2 + 8;
              return (
                <g key={sub.name} className="tj-sub">
                  <rect x={sx} y={sy} width={chipW} height={SUB_H} rx="6" />
                  <text x={sx + chipW / 2} y={sy + 9} textAnchor="middle" className="tj-sn">
                    {SUB_LABEL[sub.name] ?? sub.name}
                  </text>
                  <text x={sx + chipW / 2} y={sy + 18} textAnchor="middle" className="tj-sm">
                    {ms(sub.ms)}
                  </text>
                </g>
              );
            })}
          </g>
        );
      })}
      {answered && (
        <g className="tj-node edge-node">
          <rect x={CX - NODE_W / 2} y={end - NODE_H / 2} width={NODE_W} height={NODE_H} rx={NODE_H / 2} />
          <text x={CX} y={end + 4} textAnchor="middle" className="tj-n">
            {j.answerNode}
          </text>
        </g>
      )}
    </svg>
  );
}

/** Every step the agent took for one answer, as a graph or a waterfall; click one to see it. */
export function Trajectory({ question, steps, answer, running }: { question: string; steps: AgentStep[]; answer: AgentAnswer | null; running: boolean }) {
  const { t } = useI18n();
  const j = t.trajectory;
  const [chosen, setChosen] = useState<number | null>(null);
  const [view, setView] = useState<"graph" | "timeline">("graph");
  const selected = chosen ?? steps.length - 1;
  const total = steps.reduce((sum, step) => sum + step.ms, 0) || 1;
  const starts = steps.map((_, index) => steps.slice(0, index).reduce((sum, step) => sum + step.ms, 0));
  const step = steps[selected];
  return (
    <section className="tj" aria-label={j.title}>
      <header className="tj-head">
        <span className="label mono">{j.title}</span>
        <p className="tj-q">{question}</p>
        <p className="mono tj-total">
          {running ? j.running : j.total(ms(answer?.usage.ms ?? total))}
          {answer && ` · ${j.usage(answer.usage.input_tokens + answer.usage.output_tokens, answer.usage.cost)}`}
        </p>
      </header>
      <div className="tj-views" role="group" aria-label={j.view}>
        <button type="button" aria-pressed={view === "graph"} onClick={() => setView("graph")}>
          {j.graph}
        </button>
        <button type="button" aria-pressed={view === "timeline"} onClick={() => setView("timeline")}>
          {j.timeline}
        </button>
      </div>
      {view === "graph" ? (
        <Graph steps={steps} selected={selected} running={running} answered={answer !== null} onSelect={setChosen} />
      ) : (
        <ol className="tj-steps">
          {steps.map((item, index) => (
            <li key={`${item.name}-${index}`}>
              <button type="button" aria-pressed={index === selected} onClick={() => setChosen(index)}>
                <span className="tj-name mono">{item.name}</span>
                <span className="tj-bar" aria-hidden="true">
                  <i style={{ left: `${((starts[index] ?? 0) / total) * 100}%`, width: `${Math.max((item.ms / total) * 100, 2)}%` }} />
                </span>
                <span className="tj-ms mono">{ms(item.ms)}</span>
              </button>
            </li>
          ))}
        </ol>
      )}
      {step && (
        <div className="tj-detail" aria-live="polite">
          <span className="mono tj-dname">{step.name}</span>
          <p>{j.steps[step.name] ?? (step.name.startsWith("tool.") ? j.tool : j.unknown)}</p>
          <Detail step={step} />
        </div>
      )}
    </section>
  );
}
