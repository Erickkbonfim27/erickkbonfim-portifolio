import { useEffect, useRef, useState, type ReactNode } from "react";
import { mcpUrl } from "../api/client";
import { Layout } from "../components/Layout";

const SERVER_NAME = "erick-portfolio";

const TOOLS: [string, string][] = [
  ["get_profile", "Who I am: headline, bio, location, links and the CV link."],
  ["check_availability", "Whether I'm open to new work, and since when."],
  ["list_projects", "Published case studies, portfolio or lab."],
  ["get_project", "One case study in full: problem, decisions, result."],
  ["get_resume", "The whole CV in the JSON Resume format."],
  ["search_portfolio", "Hybrid search over everything I published, with sources."],
  ["get_skills", "Each skill with the jobs and projects where I used it."],
  ["list_studies", "Books, courses and topics I'm studying, with my notes."],
  ["contact_erick", "Sends me a message about a role, after your assistant confirms it with you."],
];

const PROMPTS: [string, string][] = [
  ["hire_erick", "Checks my fit for a role with evidence, then offers to contact me."],
  ["career_story", "My career as a short story, in English or Portuguese."],
];

type CopyState = "idle" | "copied" | "failed";

function CopyButton({ text, label }: { text: string; label: string }) {
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
    <button type="button" className="copybtn" aria-label={`Copy ${label}`} onClick={() => void copy()}>
      <span aria-live="polite">{state === "copied" ? "Copied" : state === "failed" ? "Select it" : "Copy"}</span>
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
        <span className="label mono">MCP server</span>
        <h1 className="case-title">Ask your AI about my work.</h1>
        <p className="case-summary">
          This portfolio is also an MCP server. Add it to Claude, ChatGPT, Codex or any MCP client and your
          assistant can read my profile, projects and CV, search everything I've published, and send me a
          message about a role. Free, no sign-in.
        </p>
        <div className="mcp-url">
          <code className="mono">{url}</code>
          <CopyButton text={url} label="the server URL" />
        </div>
        <p className="mcp-note">Remote server · Streamable HTTP · no authentication · read-only, except contact.</p>
      </header>

      <h2 className="mcp-section-title">Add it to your assistant</h2>
      <div className="mcp-grid">
        <Client title="Claude (web and desktop)">
          <ol>
            <li>Open Customize → Connectors.</li>
            <li>Click “+ Add”, then “Add custom connector”.</li>
            <li>Name it “Erick Kopak Bonfim” and paste the server URL.</li>
            <li>For authentication, choose “No sign in”, then click Add.</li>
          </ol>
          <p className="mcp-note">
            The connector syncs to Claude Desktop through your account. On the Free plan you can add one custom
            connector.
          </p>
        </Client>

        <Client title="Claude Code">
          <Code text={`claude mcp add --transport http ${SERVER_NAME} ${url}`} label="the Claude Code command" />
          <p className="mcp-note">
            Add <code className="mono">--scope user</code> to have it in every project. Run{" "}
            <code className="mono">/mcp</code> inside Claude Code to check it's connected.
          </p>
        </Client>

        <Client title="Codex">
          <Code text={`codex mcp add ${SERVER_NAME} --url ${url}`} label="the Codex command" />
          <p className="mcp-note">Or add it to ~/.codex/config.toml:</p>
          <Code text={`[mcp_servers.${SERVER_NAME}]\nurl = "${url}"`} label="the Codex config" />
        </Client>

        <Client title="ChatGPT">
          <ol>
            <li>In Settings → Apps → Advanced settings, turn on Developer mode.</li>
            <li>Click “Create app”, give it a name and paste the server URL.</li>
            <li>Choose “No authentication”, confirm you trust it, and create it.</li>
            <li>In a chat, open the + menu, pick Developer mode and enable the app.</li>
          </ol>
          <p className="mcp-note">
            Developer mode is a beta: whether you have it, and the exact menu names, depend on your plan.
          </p>
        </Client>
      </div>

      <Client title="Any MCP client">
        <p>
          Point it at the URL above with the Streamable HTTP transport. There's no authentication and no session
          to keep: every request stands alone. To see the tools from a terminal:
        </p>
        <Code text={listTools} label="the curl command" />
      </Client>

      <h2 className="mcp-section-title">What your assistant gets</h2>
      <p className="label mono mcp-list-label">Tools</p>
      <dl className="card mcp-tools" aria-label="Tools">
        {TOOLS.map(([name, description]) => (
          <div key={name}>
            <dt className="mono">{name}</dt>
            <dd>{description}</dd>
          </div>
        ))}
      </dl>
      <p className="label mono mcp-list-label">Prompts</p>
      <dl className="card mcp-tools" aria-label="Prompts">
        {PROMPTS.map(([name, description]) => (
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
  useEffect(() => {
    document.title = "MCP server — Erick Kopak Bonfim";
  }, []);
  return (
    <Layout base="/" cv={null}>
      <McpContent url={mcpUrl()} />
    </Layout>
  );
}
