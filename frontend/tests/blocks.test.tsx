import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { BlockData, Explained, Segment } from "../src/api/types";
import { App } from "../src/App";
import { Body } from "../src/components/blocks/Body";
import { Trajectory } from "../src/components/Trajectory";
import { classes, percentile, project, readStreets, spaced, topStreets } from "../src/lib/streets";
import { entry, json, mockFetch } from "./helpers";

const diagram: BlockData["diagram"] = {
  title: "Vizzion on GCP",
  width: 900,
  height: 400,
  groups: [{ id: "vpc", label: "VPC", x: 0, y: 0, w: 900, h: 400 }],
  nodes: [
    { id: "lb", label: "Cloud Load Balancing", x: 20, y: 20 },
    { id: "main", label: "vizzion_main", sub: "Cloud Run", x: 400, y: 20, tone: "accent" },
    { id: "same", label: "Same spot", x: 400, y: 20, w: 200, h: 64 },
  ],
  edges: [
    { from: "lb", to: "main", label: "HTTPS", flow: true },
    { from: "main", to: "same", dashed: true },
    { from: "lb", to: "ghost" },
  ],
  steps: [
    { title: "The way in", text: "Requests arrive.", focus: ["lb"] },
    { title: "The network", text: "Everything inside.", focus: ["vpc"] },
  ],
};

const layer = {
  type: "FeatureCollection",
  features: [
    { type: "Feature", properties: { name: "Av. Primeiro de Maio", nain: 1, nach: 0.2 }, geometry: { type: "LineString", coordinates: [[-48.92, -27.1], [-48.91, -27.09]] } },
    { type: "Feature", properties: { name: "Rua Azambuja", nain: 0.3, nach: 0.9 }, geometry: { type: "MultiLineString", coordinates: [[[-48.915, -27.1], [-48.912, -27.095]]] } },
    { type: "Feature", properties: { nain: 0.5 }, geometry: { type: "LineString", coordinates: [[-48.913, -27.097], [-48.911, -27.096]] } },
    { type: "Feature", properties: null, geometry: { type: "Point", coordinates: [0, 0] } },
    { type: "Feature", properties: { name: "Short", nain: 0.1 }, geometry: null },
  ],
};

function segments(...blocks: Segment[]): Segment[] {
  return blocks;
}

describe("structured blocks", () => {
  it("render every kind between html runs, and skip unknown ones", async () => {
    mockFetch({ "/files/streets.geojson": layer });
    const user = userEvent.setup();
    render(
      <Body
        fallbackHtml=""
        segments={segments(
          { type: "html", html: "<p>Intro</p>" },
          { type: "block", kind: "facts", data: { items: [{ label: "Role", text: "Co-founder and CTO" }] } },
          { type: "block", kind: "metrics", data: { items: [{ value: "150", label: "data sources", note: "23 areas" }, { value: "3rd", label: "PropVentures" }, { value: "GCP", label: "cloud" }] } },
          { type: "block", kind: "quote", data: { text: "They came to ask.", author: "Ana Prado", role: "Vangarden", url: "https://linkedin.com/x" } },
          { type: "block", kind: "quote", data: { text: "Plain.", author: "Ana" } },
          { type: "block", kind: "cases", data: { items: [{ title: "RAIS and CAGED", tag: "files", parts: [{ label: "Problem", text: "One format per file." }] }] } },
          { type: "block", kind: "timeline", data: { title: "Path", items: [{ when: "2023", title: "Reuni", tag: "SS1", text: "7th", image: { src: "/r.webp", alt: "Team" }, link: { label: "News", url: "https://unifebe.edu.br" } }, { when: "2024", title: "Fair" }] } },
          { type: "block", kind: "timeline", data: { style: "roadbook", title: "Ecosystem", items: [{ when: "2023", title: "Reuni", place: "Brusque", image: { src: "/r.webp", alt: "Stage" } }, { when: "2024", title: "PropVentures", tag: "SS2" }] } },
          { type: "block", kind: "diagram", data: diagram },
          { type: "block", kind: "diagram", data: { width: 300, height: 200, nodes: [{ id: "a", label: "Alone", x: 0, y: 0 }] } },
          { type: "block", kind: "map", data: { src: "/files/streets.geojson", attribution: "© OpenStreetMap contributors", metrics: [{ key: "nain", label: "Integration", low: "segregated", high: "integrated" }, { key: "nach", label: "Choice", note: "Routes that pass through." }], caption: "Downtown Brusque.", legend: { low: "low", high: "high" } } },
          { type: "block", kind: "poll", data: {} } as unknown as Segment,
        )}
      />,
    );
    expect(screen.getByText("Intro")).toBeInTheDocument();
    expect(screen.getByText("Co-founder and CTO")).toBeInTheDocument();
    expect(screen.getAllByText("150")).not.toHaveLength(0);
    expect(screen.getByText("23 areas")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ana Prado/ })).toHaveAttribute("href", "https://linkedin.com/x");
    expect(screen.getByText("Ana")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "RAIS and CAGED" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /News/ })).toHaveAttribute("target", "_blank");
    const roadbook = screen.getByRole("region", { name: "Ecosystem" });
    expect(within(roadbook).getByText("SS1")).toBeInTheDocument();
    expect(within(roadbook).getByText("SS2")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Vizzion on GCP" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Architecture diagram" })).toBeInTheDocument();
    // The stepper: overview first, then each step lights its part, then back to the overview.
    expect(screen.getByText("The whole system")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous step" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Step by step" }));
    expect(screen.getByRole("heading", { name: "The way in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Step 1 of 2: The way in" })).toHaveAttribute("aria-current", "step");
    expect(document.querySelector(".dg-node.lit")).toHaveTextContent("Cloud Load Balancing");
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("heading", { name: "The network" })).toBeInTheDocument();
    expect(document.querySelectorAll(".dg-node.lit")).toHaveLength(3); // every node inside the VPC group
    await user.click(screen.getByRole("button", { name: "Back to the overview" }));
    expect(screen.getAllByText("The whole system")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Step 2 of 2: The network" }));
    await user.click(screen.getByRole("button", { name: "Previous step" }));
    expect(screen.getByRole("heading", { name: "The way in" })).toBeInTheDocument();
    expect(screen.getByText("HTTPS")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "Integration. Downtown Brusque." })).toBeInTheDocument();
    expect(screen.getAllByText("Av. Primeiro de Maio")).toHaveLength(2); // on the map and in the list
    await user.click(screen.getByRole("button", { name: "Choice" }));
    expect(screen.getByRole("button", { name: "Choice" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByText("Highest values").parentElement as HTMLElement).getAllByRole("listitem")[0]).toHaveTextContent("Rua Azambuja");
    expect(screen.getByText("Routes that pass through.")).toBeInTheDocument();
    const svg = screen.getByRole("img", { name: /Choice/ });
    const street = svg.querySelector('path[data-i="1"]') as SVGPathElement;
    fireEvent.pointerMove(street, { clientX: 10, clientY: 10 });
    expect(screen.getByRole("status")).toHaveTextContent("Rua Azambuja");
    expect(screen.getByRole("status")).toHaveTextContent("Choice: above 50% of the streets");
    fireEvent.pointerMove(svg, { clientX: 1, clientY: 1 });
    expect(screen.queryByText("Choice: above 50% of the streets")).not.toBeInTheDocument();
    expect(svg.querySelector('path[data-i="2"]')).toBeNull(); // no choice value: not drawn
    await user.click(screen.getByRole("button", { name: "Integration" }));
    fireEvent.pointerMove(screen.getByRole("img", { name: /Integration/ }).querySelector('path[data-i="2"]') as SVGPathElement);
    expect(screen.getByText("Unnamed street")).toBeInTheDocument();
    fireEvent.pointerLeave(screen.getByRole("img", { name: /Integration/ }));
  });

  it("falls back to the html when there are no segments", () => {
    const { container } = render(<Body segments={[]} fallbackHtml="<p>Old body</p>" />);
    expect(screen.getByText("Old body")).toBeInTheDocument();
    render(<Body segments={undefined} fallbackHtml="" />);
    expect(container.querySelectorAll(".cflow")).toHaveLength(1);
  });

  it("says when the map layer fails", async () => {
    mockFetch({});
    render(<Body fallbackHtml="" segments={[{ type: "block", kind: "map", data: { src: "/nope.geojson", attribution: "OSM", metrics: [{ key: "nain", label: "Integration" }] } }]} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The map layer didn't load.");
  });

  it("opens photos in a lightbox that pages and closes", async () => {
    const user = userEvent.setup();
    render(
      <Body
        fallbackHtml=""
        segments={[
          {
            type: "block",
            kind: "gallery",
            data: {
              layout: "feature",
              items: [
                { src: "/a.webp", alt: "Booth", caption: "Fairtech", wide: true },
                { src: "/b.webp", alt: "Stage" },
              ],
            },
          },
          { type: "block", kind: "gallery", data: { items: [{ src: "/c.webp", alt: "Alone" }] } },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Open photo: Booth" }));
    const dialog = screen.getByRole("dialog", { name: "Booth" });
    expect(within(dialog).getByText("1 / 2")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Close" })).toHaveFocus();
    await user.click(within(dialog).getByRole("button", { name: "Next photo" }));
    expect(screen.getByRole("dialog", { name: "Stage" })).toBeInTheDocument();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("dialog", { name: "Booth" })).toBeInTheDocument();
    await user.keyboard("{ArrowLeft}");
    await user.click(screen.getByRole("button", { name: "Previous photo" }));
    expect(screen.getByRole("dialog", { name: "Booth" })).toBeInTheDocument();
    await user.click(within(screen.getByRole("dialog")).getByRole("img"));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open photo: Alone" }));
    expect(screen.queryByRole("button", { name: "Next photo" })).not.toBeInTheDocument();
    await user.keyboard("{ArrowRight}");
    await user.click(screen.getByRole("dialog"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("lists logos by group, folds long groups and filters by name", async () => {
    const user = userEvent.setup();
    const items = Array.from({ length: 30 }, (_, n) => ({ name: `Source ${n}`, url: `https://s${n}.test`, note: "REST" }));
    render(
      <Body
        fallbackHtml=""
        segments={[
          {
            type: "block",
            kind: "logos",
            data: {
              title: "Vizzion",
              note: "Integrated, not partners.",
              groups: [
                { title: "Government", items: [{ name: "IBGE", logo: "/ibge.webp" }, ...items] },
                { title: "Imagery", items: [{ name: "Planet" }] },
              ],
            },
          },
          { type: "block", kind: "logos", data: { groups: [{ title: "Loopia", items: [{ name: "Nuvemshop" }] }] } },
        ]}
      />,
    );
    expect(screen.getByText("32")).toBeInTheDocument();
    expect(screen.queryByText("Source 15")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show all 31" }));
    expect(screen.getByText("Source 15")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show fewer" }));
    await user.type(screen.getByRole("searchbox", { name: "Filter by name" }), "plan");
    expect(screen.getByText("Planet")).toBeInTheDocument();
    expect(screen.queryByText("IBGE")).not.toBeInTheDocument();
    await user.clear(screen.getByRole("searchbox"));
    await user.type(screen.getByRole("searchbox"), "zzz");
    expect(screen.getByText("No integration with that name.")).toBeInTheDocument();
    expect(screen.getByText("Nuvemshop")).toBeInTheDocument();
  });
});

describe("street layers", () => {
  it("read lines, project them, class them by rank and label the top ones", () => {
    const streets = readStreets(layer, ["nain"]);
    expect(streets).toHaveLength(3);
    const { height, path, point } = project(streets);
    expect(height).toBeGreaterThan(0);
    expect(path(streets[0]?.line ?? [])).toMatch(/^M0\.0 /);
    expect(classes(streets, "nain")).toEqual([6, 0, 3]);
    expect(classes(streets, "nach")).toEqual([null, null, null]);
    expect(percentile(streets, "nain", 1)).toBe(67);
    expect(percentile([], "nain", 1)).toBe(0);
    expect(topStreets(streets, "nain", point).map((label) => label.name)).toEqual(["Av. Primeiro de Maio", "Rua Azambuja"]);
    expect(readStreets(null, ["nain"])).toEqual([]);
    const near = [
      { name: "A", x: 100, y: 100 },
      { name: "B", x: 150, y: 110 },
      { name: "C", x: 150, y: 200 },
    ];
    expect(spaced(near).map((label) => label.name)).toEqual(["A", "C"]);
  });
});

const explained: Explained = {
  query: "Has Erick shipped RAG in production?",
  hits: [
    { entry_id: "1", kind: "project", slug: "rhye", title: "Rhye", heading: "Grounding", text: "…", score: 0.5 },
    { entry_id: "2", kind: "experience", slug: "loopia", title: "Loopia", heading: "", text: "…", score: 0.4 },
    { entry_id: "3", kind: "study", slug: "ddia", title: "DDIA", heading: "", text: "…", score: 0.3 },
  ],
  dense: [{ slug: "rhye", title: "Rhye", heading: "Retrieval", score: 0.8 }],
  sparse: [{ slug: "loopia", title: "Loopia", heading: "", score: 7.1 }],
  steps: [
    { name: "bm25.encode", ms: 3 },
    { name: "dense.encode", ms: 1205 },
    { name: "dense.search", ms: 20 },
    { name: "bm25.search", ms: 12 },
    { name: "rrf.fuse", ms: 30 },
  ],
  degraded: false,
};

describe("hero live search", () => {
  it("answers a question with passages, shows the trace, and takes the visitor's own question", async () => {
    const { calls } = mockFetch({
      "/api/search/explain": (url: URL) =>
        json(url.searchParams.get("q")?.startsWith("Which") ? { ...explained, degraded: true, dense: [] } : explained),
    });
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByText("I found this in 3 places on the site:")).toBeInTheDocument();
    expect(screen.getByText(/1\.27s · dense \+ BM25 · RRF/)).toBeInTheDocument();
    expect(screen.getByText("passed")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Rhye.*Grounding/ })[0]).toHaveAttribute("href", "/work/rhye");
    expect(screen.getAllByRole("link", { name: "Loopia" })[0]).toHaveAttribute("href", "/#experience");
    await user.click(screen.getByRole("button", { name: "Which data sources did Vizzion integrate?" }));
    expect(await screen.findByText("bm25 only")).toBeInTheDocument();
    expect(screen.getByText(/BM25 only/)).toBeInTheDocument();
    expect(calls.at(-1)?.url.searchParams.get("q")).toBe("Which data sources did Vizzion integrate?");
    const field = screen.getAllByRole("textbox", { name: "Ask something about my work…" })[0] as HTMLElement;
    await user.type(field, "  Has he used Qdrant?  {Enter}");
    await waitFor(() => expect(calls.at(-1)?.url.searchParams.get("q")).toBe("Has he used Qdrant?"));
    expect(screen.getAllByText("Has he used Qdrant?").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Has Erick shipped RAG in production?" }));
    await waitFor(() => expect(calls.at(-1)?.url.searchParams.get("q")).toBe("Has Erick shipped RAG in production?"));
  });

  it("says when nothing matches, and when the API is down", async () => {
    mockFetch({ "/api/search/explain": { ...explained, hits: [] } });
    const { unmount } = render(<App />);
    expect(await screen.findByText(/Nothing on the site matches that/)).toBeInTheDocument();
    unmount();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<App />);
    expect((await screen.findAllByText("The API didn't answer. The rest of the site still works.")).length).toBeGreaterThan(0);
    expect(screen.getByText("offline")).toBeInTheDocument();
  });
});

function sse(events: [string, unknown][]): Response {
  const body = events.map(([kind, data]) => `event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`).join("");
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

const found = [
  { n: 1, title: "Erick", heading: "Engineer", score: 1 },
  { n: 2, title: "Loopia", heading: "", score: 0.71 },
];
const agentSteps: [string, unknown][] = [
  ["step", { name: "route", ms: 0.4, detail: { mode: "tools", reason: "a question about the work" } }],
  [
    "step",
    {
      name: "retrieve",
      ms: 310,
      detail: {
        query: "How does he evaluate AI agents?",
        steps: [
          { name: "bm25.encode", ms: 2 },
          { name: "dense.encode", ms: 250 },
          { name: "rrf.fuse", ms: 1 },
        ],
        dense: [{ title: "Loopia", heading: "", score: 0.612 }],
        sparse: [{ title: "Loopia", heading: "Evals", score: 7.1 }],
        found,
      },
    },
  ],
  ["step", { name: "model", ms: 1800, detail: { model: "openai/gpt-oss-120b", input_tokens: 900, output_tokens: 80, tool_calls: ["read_case"] } }],
  ["step", { name: "tool.read_case", ms: 40, detail: { slug: "loopia", found: [] } }],
  ["step", { name: "guard", ms: 1, detail: { passed: false, reasons: ["numbers not in the passages: 300"] } }],
  ["step", { name: "rewrite", ms: 900, detail: { reasons: ["numbers not in the passages: 300"] } }],
  ["step", { name: "grounding", ms: 700, detail: { model: "openai/gpt-4o-mini", passed: false, unsupported: ["won an award"] } }],
  ["step", { name: "agent.mystery", ms: 1, detail: { skipped: true, error: "x" } }],
];
const agentAnswer = {
  text: "Erick set up Langfuse for the agents' evals [2].\n\nHe is an engineer [1] [9].",
  citations: [
    { n: 2, title: "Loopia", heading: "", kind: "experience", slug: "loopia" },
    { n: 1, title: "Erick", heading: "Engineer", kind: "profile", slug: "profile" },
  ],
  stop: "answered",
  usage: { input_tokens: 1200, output_tokens: 110, cost: 0.00042, ms: 3750 },
};

describe("assistant dot", () => {
  it("talks to the agent, streams its steps and shows the trajectory", async () => {
    const { calls } = mockFetch({ "/api/chat": () => sse([...agentSteps, ["answer", agentAnswer]]) });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Talk to my agent" }));
    const panel = screen.getByRole("dialog", { name: "Talk to my agent" });
    expect(within(panel).getByRole("textbox")).toHaveFocus();
    await user.click(within(panel).getByRole("button", { name: "See the trajectory" }));
    expect(within(panel).getByText("Ask something: each answer's steps show up here.")).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "How does he evaluate AI agents?" }));
    expect(await within(panel).findByText(/set up Langfuse for the agents' evals/)).toBeInTheDocument();
    const sent = JSON.parse(String(calls.at(-1)?.init?.body));
    expect(sent).toEqual({ message: "How does he evaluate AI agents?", history: [], lang: "en" });
    // Citations link to where they came from; an unknown number stays plain text.
    expect(within(panel).getAllByRole("link", { name: "2" })[0]).toHaveAttribute("href", "/#experience");
    expect(within(panel).getAllByRole("link", { name: "1" })[0]).toHaveAttribute("href", "/#top");
    expect(within(panel).getByText(/\[9\]/)).toBeInTheDocument();
    expect(within(panel).getByText("Sources")).toBeInTheDocument();

    const trajectory = within(panel).getByRole("region", { name: "Trajectory of the answer" });
    expect(within(trajectory).getByText(/3\.75s in total · 1,310 tokens · US\$ 0\.00042/)).toBeInTheDocument();
    expect(within(trajectory).getByRole("img", { name: "Graph" })).toBeInTheDocument();
    // The last step is selected; unknown steps get a generic description.
    expect(within(trajectory).getByText("A step of this answer.")).toBeInTheDocument();
    await user.click(within(trajectory).getByRole("button", { name: "retrieve, 310ms" }));
    expect(within(trajectory).getByText(/searched the site/)).toBeInTheDocument();
    expect(within(trajectory).getByText("Dense ranking (meaning)")).toBeInTheDocument();
    expect(within(trajectory).getByText("7.100")).toBeInTheDocument();
    expect(within(trajectory).getAllByText("dense.encode").length).toBeGreaterThan(0);
    fireEvent.keyDown(within(trajectory).getByRole("button", { name: "guard, 1ms" }), { key: "Enter" });
    expect(within(trajectory).getByText("numbers not in the passages: 300")).toBeInTheDocument();
    fireEvent.keyDown(within(trajectory).getByRole("button", { name: "model, 1.80s" }), { key: "Tab" });
    await user.click(within(trajectory).getByRole("button", { name: "Timeline" }));
    await user.click(within(trajectory).getByRole("button", { name: /grounding/ }));
    expect(within(trajectory).getByText("won an award")).toBeInTheDocument();
    await user.click(within(trajectory).getByRole("button", { name: /^model/ }));
    expect(within(trajectory).getByText("900 → 80")).toBeInTheDocument();
    expect(within(trajectory).getByText("read_case")).toBeInTheDocument();
    await user.click(within(trajectory).getByRole("button", { name: /tool\.read_case/ }));
    expect(within(trajectory).getByText("Nothing came back from this lookup.")).toBeInTheDocument();
    await user.click(within(trajectory).getByRole("button", { name: /^route/ }));
    expect(within(trajectory).getByText("tools · a question about the work")).toBeInTheDocument();

    await user.click(within(panel).getByRole("tab", { name: "Conversation" }));
    await user.click(within(panel).getByRole("tab", { name: "Trajectory" }));
    await user.click(within(panel).getByRole("button", { name: "Hide the trajectory" }));
    // A follow-up carries the answered turn as history.
    await user.type(within(panel).getByRole("textbox"), "And Qdrant?{Enter}");
    await waitFor(() => expect(JSON.parse(String(calls.at(-1)?.init?.body)).history).toHaveLength(2));
    await user.type(within(panel).getByRole("textbox"), "   {Enter}");
    await user.click(within(panel).getByRole("button", { name: "Clear the conversation" }));
    expect(within(panel).queryByText("And Qdrant?")).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Talk to my agent" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Talk to my agent" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Talk to my agent" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Talk to my agent" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Talk to my agent" }));
    await user.click(document.querySelector(".dot-backdrop") as HTMLElement);
    expect(screen.queryByRole("dialog", { name: "Talk to my agent" })).not.toBeInTheDocument();
  });

  it.each([
    [() => json({ detail: "slow down" }, 429), "Too many questions in a row. Wait a minute and ask again."],
    [() => json({ detail: "resting" }, 503), /used today's budget/],
    [() => sse([["error", { message: "the assistant failed" }]]), "I couldn't answer right now. Try again in a moment."],
    [() => Promise.reject(new TypeError("offline")), "I couldn't answer right now. Try again in a moment."],
  ])("says plainly when the agent can't answer (%#)", async (handler, message) => {
    mockFetch({ "/api/chat": handler });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Talk to my agent" }));
    const panel = screen.getByRole("dialog", { name: "Talk to my agent" });
    await user.type(within(panel).getByRole("textbox"), "Hi there?{Enter}");
    expect(await within(panel).findByText(message)).toBeInTheDocument();
  });

  it("shows the working step while the answer is on its way", async () => {
    mockFetch({ "/api/chat": () => sse(agentSteps.slice(0, 2)) });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Talk to my agent" }));
    const panel = screen.getByRole("dialog", { name: "Talk to my agent" });
    await user.click(within(panel).getByRole("button", { name: "See the trajectory" }));
    await user.type(within(panel).getByRole("textbox"), "Evals?{Enter}");
    expect(await within(panel).findByText("Searching the site…")).toBeInTheDocument();
    expect(within(panel).getByText("Working…")).toBeInTheDocument();
  });
});

describe("trajectory", () => {
  it("draws a search's inner steps under its node and an empty lookup", () => {
    const steps = [
      { name: "retrieve", ms: 12, detail: { query: "q", steps: [{ name: "bm25.encode", ms: 1 }, { name: "custom.step", ms: 2 }], dense: [], sparse: [], found: [] } },
      { name: "model", ms: 5, detail: {} },
    ];
    render(<Trajectory question="Q" steps={steps} answer={null} running={false} />);
    expect(screen.getByText("bm25 enc")).toBeInTheDocument();
    expect(screen.getByText("custom.step")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "retrieve, 12ms" }));
    expect(screen.getByText("Nothing came back from this lookup.")).toBeInTheDocument();
    expect(screen.getByText(/0\.02s in total|17ms in total/)).toBeInTheDocument();
  });
});

describe("case study with blocks", () => {
  it("renders the segments of a case", async () => {
    mockFetch({
      "/api/projects/vizzion": entry({
        slug: "vizzion",
        title: "Vizzion",
        details: { state: "building" },
        body: [
          { type: "html", html: "<h2>Problem</h2>" },
          { type: "block", kind: "metrics", data: { items: [{ value: "150", label: "data sources" }] } },
        ],
      }),
    });
    window.history.replaceState({}, "", "/work/vizzion");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 2, name: "Problem" })).toBeInTheDocument();
    expect(screen.getByText("data sources")).toBeInTheDocument();
    expect(screen.getByText("In progress")).toBeInTheDocument();
    await waitFor(() => expect(document.title).toContain("Vizzion"));
  });
});

describe("written pages", () => {
  it("shows the integrations page from the API, linked from the header", async () => {
    mockFetch({
      "/api/writing/integrations": (url: URL) =>
        json(
          entry({
            kind: "writing",
            slug: "integrations",
            title: url.searchParams.get("lang") === "pt" ? "Integrações" : "Integrations",
            summary: "158 integrations.",
            body: [{ type: "html", html: '<p>See <a href="/work/vizzion">Vizzion</a>.</p>' }],
          }),
        ),
      "/api/projects/vizzion": entry({ slug: "vizzion", title: "Vizzion" }),
    });
    const user = userEvent.setup();
    render(<App />);
    const primary = screen.getByRole("navigation", { name: "Primary" });
    await user.click(within(primary).getByRole("link", { name: "Integrations" }));
    expect(window.location.pathname).toBe("/integrations");
    expect(await screen.findByText("158 integrations.")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: "Integrations" })).toHaveAttribute("aria-current", "page");
    expect(document.title).toBe("Integrations — Erick Kopak Bonfim");
    await user.click(screen.getByRole("link", { name: "Vizzion" }));
    expect(window.location.pathname).toBe("/work/vizzion");
  });

  it("says so when the integrations page fails or is missing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    window.history.replaceState({}, "", "/pt/integrations");
    const { unmount } = render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("O servidor não respondeu.");
    unmount();
    mockFetch({});
    window.history.replaceState({}, "", "/integrations");
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Nothing here." })).toBeInTheDocument();
  });

  it("puts the road book on the home page when it is published", async () => {
    mockFetch({
      "/api/writing/ecosystem": entry({
        kind: "writing",
        slug: "ecosystem",
        title: "The road so far",
        summary: "Told as rally stages.",
        body: [{ type: "block", kind: "timeline", data: { style: "roadbook", title: "Road book", items: [{ when: "2023", title: "Reuni Challenge" }] } }],
      }),
    });
    render(<App />);
    expect(await screen.findByRole("heading", { level: 2, name: "The road so far" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Road book" })).toBeInTheDocument();
  });
});
