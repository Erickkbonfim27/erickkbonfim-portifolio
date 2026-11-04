import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, streamChat } from "../api/client";
import type { AgentAnswer, AgentStep, ChatTurn } from "../api/types";
import { useI18n } from "../i18n";
import { MAX_QUESTION } from "../lib/search";
import { AgentReply } from "./AgentReply";
import { ArrowUpRight } from "./Icons";
import { Trajectory } from "./Trajectory";

interface Turn {
  id: number;
  question: string;
  /** The conversation before this question, as the agent receives it. */
  history: ChatTurn[];
}

export interface Progress {
  steps: AgentStep[];
  answer: AgentAnswer | null;
  error: string | null;
}

function Exchange({ turn, onProgress }: { turn: Turn; onProgress: (id: number, progress: Progress) => void }) {
  const { lang, t } = useI18n();
  const a = t.assistant;
  const [progress, setProgress] = useState<Progress>({ steps: [], answer: null, error: null });

  useEffect(() => {
    const controller = new AbortController();
    let current: Progress = { steps: [], answer: null, error: null };
    const update = (next: Progress) => {
      current = next;
      setProgress(next);
      onProgress(turn.id, next);
    };
    streamChat(
      { message: turn.question, history: turn.history, lang },
      (event) => {
        if (event.kind === "step") update({ ...current, steps: [...current.steps, event.data] });
        else if (event.kind === "answer") update({ ...current, answer: event.data });
        else update({ ...current, error: a.failed });
      },
      controller.signal,
    ).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      const kind = error instanceof ApiError ? error.kind : "network";
      update({ ...current, error: kind === "rate_limited" ? a.tooMany : kind === "http" && (error as ApiError).status === 503 ? a.resting : a.failed });
    });
    return () => controller.abort();
    // One request per turn; the turn never changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turn.id]);

  const last = progress.steps.at(-1)?.name;
  return (
    <>
      <p className="bubble me">{turn.question}</p>
      {progress.answer ? (
        <AgentReply answer={progress.answer} />
      ) : progress.error ? (
        <p className="bubble site">{progress.error}</p>
      ) : (
        <div className="bubble site thinking">
          <p className="typing" aria-hidden="true">
            <i />
            <i />
            <i />
          </p>
          <span className="mono">{a.working(last)}</span>
        </div>
      )}
    </>
  );
}

/** The floating button in the corner and its conversation panel, on every page, with the
 * trajectory of each answer beside it. Until the agent ships it talks to the site's live
 * search; the agent takes its place, and its steps show up in the same trajectory. */
export function AssistantDot() {
  const { t } = useI18n();
  const a = t.assistant;
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [results, setResults] = useState<Record<number, Progress>>({});
  const [traceOpen, setTraceOpen] = useState(false);
  const [tab, setTab] = useState<"chat" | "trace">("chat");
  const [draft, setDraft] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  const close = () => {
    setOpen(false);
    button.current?.focus();
  };

  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    log.current?.scrollTo?.({ top: log.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const [record] = useState(() => (id: number, progress: Progress) => setResults((current) => ({ ...current, [id]: progress })));

  const ask = (question: string) => {
    const text = question.trim().slice(0, MAX_QUESTION);
    if (!text) return;
    // The agent gets the last turns that were answered, so a follow-up has context.
    const history = turns.flatMap((turn): ChatTurn[] => {
      const answer = results[turn.id]?.answer?.text;
      return answer ? [{ role: "user", content: turn.question }, { role: "assistant", content: answer.slice(0, 1800) }] : [];
    });
    setTurns((current) => [...current, { id: (current.at(-1)?.id ?? 0) + 1, question: text, history: history.slice(-6) }]);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    ask(draft);
    setDraft("");
  };

  // The trajectory of the latest question, live while the agent works.
  const latest = turns.at(-1);
  const trajectory = latest ? results[latest.id] : undefined;

  return (
    <>
      {open && <div className="dot-backdrop" aria-hidden="true" onClick={close} />}
      <div className="dot-wrap">
        {open && (
          <section
            id="assistant-panel"
            className={`dot-panel${traceOpen ? " with-trace" : ""} tab-${tab}`}
            role="dialog"
            aria-label={a.title}
          >
            <div className="dot-tabs" role="tablist">
              <button type="button" role="tab" aria-selected={tab === "chat"} onClick={() => setTab("chat")}>
                {a.chatTab}
              </button>
              <button type="button" role="tab" aria-selected={tab === "trace"} onClick={() => setTab("trace")}>
                {a.traceTab}
              </button>
            </div>
            {(traceOpen || tab === "trace") && (
              <div className="dot-trace" data-clarity-mask="true">
                {trajectory && latest && trajectory.steps.length > 0 ? (
                  <Trajectory
                    key={latest.id}
                    question={latest.question}
                    steps={trajectory.steps}
                    answer={trajectory.answer}
                    running={!trajectory.answer && !trajectory.error}
                  />
                ) : (
                  <p className="tj-empty">{a.noTrace}</p>
                )}
              </div>
            )}
            <div className="dot-chat">
              <header className="dot-head">
                <div className="dot-title">
                  <strong>{a.title}</strong>
                  <span className="mono">
                    <span className="live" aria-hidden="true" /> {a.status}
                  </span>
                </div>
                <button type="button" className="dot-trace-btn mono" aria-pressed={traceOpen} onClick={() => setTraceOpen(!traceOpen)}>
                  {traceOpen ? a.hideTrace : a.showTrace}
                </button>
                <button type="button" className="dot-x" aria-label={a.close} onClick={close}>
                  ×
                </button>
              </header>
              <div ref={log} className="dot-log" aria-live="polite" data-clarity-mask="true">
                <p className="bubble site">{a.greeting}</p>
                {turns.length === 0 && (
                  <div className="asks">
                    {t.hero.presets.map((preset) => (
                      <button key={preset} type="button" className="ask" onClick={() => ask(preset)}>
                        {preset}
                      </button>
                    ))}
                  </div>
                )}
                {turns.map((turn) => (
                  <Exchange key={turn.id} turn={turn} onProgress={record} />
                ))}
              </div>
              <form className="ask-form" onSubmit={submit} data-clarity-mask="true">
                <input
                  ref={input}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  maxLength={MAX_QUESTION}
                  placeholder={t.hero.placeholder}
                  aria-label={t.hero.placeholder}
                />
                <button type="submit" className="ask-send" aria-label={t.hero.send} disabled={!draft.trim()}>
                  <ArrowUpRight size={16} />
                </button>
              </form>
              <div className="dot-foot">
                <p className="dot-note">{a.note}</p>
                {turns.length > 0 && (
                  <button
                    type="button"
                    className="dot-clear tlink"
                    onClick={() => {
                      setTurns([]);
                      setResults({});
                    }}
                  >
                    {a.clear}
                  </button>
                )}
              </div>
            </div>
          </section>
        )}
        <button
          ref={button}
          type="button"
          className={`dot${open ? " open" : ""}`}
          aria-expanded={open}
          aria-controls="assistant-panel"
          aria-label={open ? a.close : a.open}
          onClick={() => (open ? close() : setOpen(true))}
        >
          {open ? (
            <span className="dot-icon" aria-hidden="true">
              ×
            </span>
          ) : (
            <svg className="dot-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 12a8.5 8.5 0 0 1-12.6 7.4L3 21l1.6-5.2A8.5 8.5 0 1 1 21 12Z" />
              <path d="M8.5 12h.01M12 12h.01M15.5 12h.01" />
            </svg>
          )}
          {!open && <span className="dot-live" aria-hidden="true" />}
        </button>
      </div>
    </>
  );
}
