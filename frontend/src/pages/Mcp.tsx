import { useEffect, useRef, useState, type ReactNode } from "react";
import { mcpUrl } from "../api/client";
import { Layout } from "../components/Layout";
import { useI18n } from "../i18n";

const SERVER_NAME = "erick-portfolio";

type CopyState = "idle" | "copied" | "failed";

function CopyButton({ text, label }: { text: string; label: string }) {
  const { t } = useI18n();
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 2000);
  };

  return (
    <button type="button" className="copybtn" aria-label={t.mcp.copyLabel(label)} onClick={() => void copy()}>
      <span aria-live="polite">{state === "copied" ? t.mcp.copied : state === "failed" ? t.mcp.selectIt : t.mcp.copy}</span>
    </button>
  );
}

function Code({ text, label }: { text: string; label: string }) {
  return (
    <div className="mcp-code">
      <pre className="mono">
        <code>{text}</code>
      </pre>
      <CopyButton text={text} label={label} />
    </div>
  );
}

function Client({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card mcp-client" aria-label={title}>
      <h3>{title}</h3>
      {children}
    </section>
  );
}

export function McpContent({ url }: { url: string }) {
  const { t } = useI18n();
  const m = t.mcp;
  const listTools = [
    `curl -s -X POST ${url} \\`,
    `  -H 'content-type: application/json' \\`,
    `  -H 'accept: application/json, text/event-stream' \\`,
    `  -H 'mcp-protocol-version: 2025-06-18' \\`,
    `  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`,
  ].join("\n");

  return (
    <div className="wrap case">
      <header id="top" className="card case-head">
        <span className="label mono">{m.label}</span>
        <h1 className="case-title">{m.title}</h1>
        <p className="case-summary">{m.intro}</p>
        <div className="mcp-url">
          <code className="mono">{url}</code>
          <CopyButton text={url} label={m.serverUrl} />
        </div>
        <p className="mcp-note">{m.facts}</p>
      </header>

      <h2 className="mcp-section-title">{m.addTitle}</h2>
      <div className="mcp-grid">
        <Client title={m.claude.title}>
          <ol>
            {m.claude.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <p className="mcp-note">{m.claude.note}</p>
        </Client>

        <Client title={m.claudeCode.title}>
          <Code text={`claude mcp add --transport http ${SERVER_NAME} ${url}`} label={m.claudeCode.command} />
          <p className="mcp-note">
            {m.claudeCode.notePrefix} <code className="mono">--scope user</code> {m.claudeCode.noteMiddle}{" "}
            <code className="mono">/mcp</code> {m.claudeCode.noteSuffix}
          </p>
        </Client>

        <Client title={m.codex.title}>
          <Code text={`codex mcp add ${SERVER_NAME} --url ${url}`} label={m.codex.command} />
          <p className="mcp-note">{m.codex.note}</p>
          <Code text={`[mcp_servers.${SERVER_NAME}]\nurl = "${url}"`} label={m.codex.config} />
        </Client>

        <Client title={m.chatgpt.title}>
          <ol>
            {m.chatgpt.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <p className="mcp-note">{m.chatgpt.note}</p>
        </Client>
      </div>

      <Client title={m.any.title}>
        <p>{m.any.text}</p>
        <Code text={listTools} label={m.any.command} />
      </Client>

      <h2 className="mcp-section-title">{m.getsTitle}</h2>
      <p className="label mono mcp-list-label">{m.tools}</p>
      <dl className="card mcp-tools" aria-label={m.tools}>
        {m.toolList.map(([name, description]) => (
          <div key={name}>
            <dt className="mono">{name}</dt>
            <dd>{description}</dd>
          </div>
        ))}
      </dl>
      <p className="label mono mcp-list-label">{m.prompts}</p>
      <dl className="card mcp-tools" aria-label={m.prompts}>
        {m.promptList.map(([name, description]) => (
          <div key={name}>
            <dt className="mono">{name}</dt>
            <dd>{description}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Mcp() {
  const { t } = useI18n();
  return (
    <Layout onHome={false} cv={null} title={t.titles.mcp}>
      <McpContent url={mcpUrl()} />
    </Layout>
  );
}
