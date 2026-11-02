import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { ContactForm } from "../src/components/ContactForm";
import { MESSAGES } from "../src/lib/contact";
import { navigate } from "../src/lib/router";
import { entry, json, mockFetch, profile, skill } from "./helpers";

async function fill(user: ReturnType<typeof userEvent.setup>, brief = "AI Engineer role, remote.") {
  await user.type(screen.getByLabelText("Your name"), "Ana");
  await user.type(screen.getByLabelText("Email or phone"), "ana@corp.dev");
  await user.type(screen.getByLabelText("The role or project"), brief);
}

describe("ContactForm", () => {
  it("sends, clears the form and confirms", async () => {
    const { calls } = mockFetch({ "/api/contact": () => json({ id: "1" }, 202) });
    const user = userEvent.setup();
    render(<ContactForm />);
    await fill(user);
    await user.type(screen.getByLabelText("Company (optional)"), "Corp");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText(MESSAGES.sent)).toBeInTheDocument();
    expect(screen.getByLabelText("Your name")).toHaveValue("");
    const body = JSON.parse(String(calls[0]?.init?.body));
    expect(body).toEqual({ from: "Ana", contact: "ana@corp.dev", brief: "AI Engineer role, remote.", company: "Corp", lang: "en", website: "" });
    expect(screen.getByText("Used only to reply to you; deleted after 12 months.")).toBeInTheDocument();
  });

  it("shows the API's 422 detail and the 429 message", async () => {
    let status = 422;
    mockFetch({ "/api/contact": () => json({ detail: "brief needs 10 to 4000 characters" }, status) });
    const user = userEvent.setup();
    render(<ContactForm />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Brief needs 10 to 4000 characters.");
    status = 429;
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(MESSAGES.rateLimited));
  });

  it("reuses the idempotency key on retry and renews it after an edit", async () => {
    let fail = true;
    const { calls } = mockFetch({
      "/api/contact": () => (fail ? Promise.reject(new TypeError("offline")) : json({ id: "1" }, 202)),
    });
    const user = userEvent.setup();
    render(<ContactForm />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(MESSAGES.network);
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByRole("alert");
    const key = (n: number) => (calls[n]?.init?.headers as Record<string, string>)["Idempotency-Key"];
    expect(key(0)).toBeTruthy();
    expect(key(1)).toBe(key(0));
    await user.type(screen.getByLabelText("The role or project"), " Edited.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(MESSAGES.sent);
    expect(key(2)).not.toBe(key(0));
  });

  it("disables the button while sending", async () => {
    let release: (r: Response) => void = () => undefined;
    mockFetch({ "/api/contact": () => new Promise<Response>((resolve) => (release = resolve)) });
    const user = userEvent.setup();
    render(<ContactForm />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(screen.getByRole("button", { name: "Sending…" })).toBeDisabled();
    await act(async () => release(json({ id: "1" }, 202)));
    expect(await screen.findByText(MESSAGES.sent)).toBeInTheDocument();
  });

  it("forwards the honeypot so the API can drop bots", async () => {
    const { calls } = mockFetch({ "/api/contact": () => json({ id: "1" }, 202) });
    const user = userEvent.setup();
    const { container } = render(<ContactForm />);
    await fill(user);
    const honeypot = container.querySelector<HTMLInputElement>('input[name="website"]');
    expect(honeypot).not.toBeNull();
    await user.type(honeypot as HTMLInputElement, "spam.biz");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(MESSAGES.sent);
    expect(JSON.parse(String(calls[0]?.init?.body)).website).toBe("spam.biz");
  });
});

describe("Home", () => {
  it("renders the handoff copy when the API is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<App />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("I used to sell apartments. EK Now I build AI agents.");
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.getByText("MAY 2026 — OCT 2026")).toBeInTheDocument();
    expect(screen.getByText("Open to AI Engineer roles")).toBeInTheDocument();
    expect(screen.queryByText(/R\$80M/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Download CV/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Agents & LLMs" })).toBeInTheDocument();
  });

  it("renders API data: experience, skills, availability, CV, work text", async () => {
    const cv = { label: "CV", filename: "erick-cv.pdf", url: "https://files.test/cv.pdf", content_type: "application/pdf", size: 1000 };
    mockFetch({
      "/api/profile": profile({ availability: { status: "not_looking", open: false, updated_at: "2026-11-01" }, attachments: [cv] }),
      "/api/experience": [entry({ kind: "experience", slug: "acme", title: "AI Engineer", summary: "Agents at Acme.", details: { organization: "Acme", start: "2026-12" } })],
      "/api/skills": [skill("LangGraph", "ai")],
      "/api/education": [],
      "/api/certificates": [],
      "/api/studies": [],
      "/api/projects/rhye": entry({ title: "Rhye", summary: "Summary from the API." }),
    });
    render(<App />);
    expect(await screen.findByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("DEC 2026 — NOW")).toBeInTheDocument();
    expect(await screen.findByText("Summary from the API.")).toBeInTheDocument();
    expect(screen.getByText("Not looking for new roles")).toBeInTheDocument();
    const stack = screen.getByRole("region", { name: "Tools I use" });
    expect(within(stack).getByText("LangGraph")).toBeInTheDocument();
    expect(within(stack).queryByText("Data & search")).not.toBeInTheDocument();
    const cvLinks = screen.getAllByRole("link", { name: /Download CV|CV \(PDF\)/ });
    expect(cvLinks.length).toBeGreaterThanOrEqual(2);
    expect(cvLinks[0]).toHaveAttribute("href", cv.url);
  });

  it("toggles the mobile menu and copies the email", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    const user = userEvent.setup(); // installs a clipboard stub on navigator
    render(<App />);
    const menu = screen.getByRole("button", { name: "Open menu" });
    await user.click(menu);
    const mobile = screen.getByRole("navigation", { name: "Mobile" });
    expect(menu).toHaveAttribute("aria-expanded", "true");
    await user.click(within(mobile).getByRole("link", { name: /Work/ }));
    expect(screen.queryByRole("navigation", { name: "Mobile" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy email" }));
    expect(await navigator.clipboard.readText()).toBe("erickkbonfim@gmail.com");
    expect(screen.getByText("Email copied to clipboard")).toBeInTheDocument();
  });
});

describe("Case study page", () => {
  it("renders the entry with sanitized HTML, details, skills, links and downloads", async () => {
    mockFetch({
      "/api/projects/rhye": entry({
        title: "Rhye",
        summary: "People intelligence for 50–300 people.",
        details: { organization: "Rhye", start: "2026-05", state: "active", links: [{ label: "rhye.com.br", url: "https://rhye.com.br" }] },
        body_html: "<h2>Architecture</h2><p>Hexagonal core.</p>",
        skills: [{ slug: "langgraph", title: "LangGraph" }],
        attachments: [{ label: "Usability study", filename: "study.pdf", url: "https://files.test/s.pdf", content_type: "application/pdf", size: 2048 }],
      }),
    });
    window.history.replaceState({}, "", "/work/rhye");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Rhye" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Architecture" })).toBeInTheDocument();
    expect(screen.getByText("MAY 2026 — NOW")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("LangGraph")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /rhye\.com\.br/ })).toHaveAttribute("target", "_blank");
    const download = screen.getByRole("link", { name: /Usability study/ });
    expect(download).toHaveAttribute("download", "study.pdf");
    expect(download).toHaveTextContent("2 KB");
    await waitFor(() => expect(document.title).toBe("Rhye — Erick Kopak Bonfim"));
  });

  it("shows the 404 page for an unknown project and for unknown routes", async () => {
    mockFetch({});
    window.history.replaceState({}, "", "/work/ghost");
    const { unmount } = render(<App />);
    expect(await screen.findByRole("heading", { name: "Nothing here." })).toBeInTheDocument();
    unmount();
    window.history.replaceState({}, "", "/nope/deeper");
    render(<App />);
    expect(screen.getByRole("heading", { name: "Nothing here." })).toBeInTheDocument();
  });

  it("explains a server error and links back", async () => {
    mockFetch({ "/api/projects/rhye": () => new Response("down", { status: 503 }) });
    window.history.replaceState({}, "", "/work/rhye");
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load this case study.");
    expect(screen.getByRole("link", { name: "← All work" })).toHaveAttribute("href", "/#work");
  });

  it("navigates from a work card to its case page without reloading", async () => {
    mockFetch({ "/api/projects/loopia": entry({ slug: "loopia", title: "Loopia" }) });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("link", { name: "Loopia case study" }));
    expect(window.location.pathname).toBe("/work/loopia");
    expect(await screen.findByRole("heading", { level: 1, name: "Loopia" })).toBeInTheDocument();
    act(() => navigate("/"));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("I used to sell");
  });
});
