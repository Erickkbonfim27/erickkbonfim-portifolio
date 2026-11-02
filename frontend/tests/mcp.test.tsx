import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { matchRoute, navigate } from "../src/lib/router";
import { mcpUrl } from "../src/api/client";
import { McpContent } from "../src/pages/Mcp";

const TOOLS = [
  "get_profile",
  "check_availability",
  "list_projects",
  "get_project",
  "get_resume",
  "search_portfolio",
  "get_skills",
  "list_studies",
  "contact_erick",
];

function offline() {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
}

describe("Nav", () => {
  it("keeps layout out of inline styles, so small screens can hide the desktop links", () => {
    offline();
    render(<App />);
    const primary = screen.getByRole("navigation", { name: "Primary" });
    expect(primary).not.toHaveAttribute("style");
    expect(primary.parentElement?.querySelector(".nav-actions")).not.toHaveAttribute("style");
  });

  it("links to the MCP page from the header and marks it as current", async () => {
    offline();
    const user = userEvent.setup();
    render(<App />);
    const primary = screen.getByRole("navigation", { name: "Primary" });
    const link = within(primary).getByRole("link", { name: "MCP" });
    expect(link).toHaveAttribute("href", "/mcp");
    expect(link).not.toHaveAttribute("aria-current");
    await user.click(link);
    expect(window.location.pathname).toBe("/mcp");
    expect(screen.getByRole("heading", { level: 1, name: "Ask your AI about my work." })).toBeInTheDocument();
    const current = within(screen.getByRole("navigation", { name: "Primary" })).getByRole("link", { name: "MCP" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(document.title).toBe("MCP server — Erick Kopak Bonfim");
  });

  it("offers the MCP page in the mobile menu, which closes on the way", async () => {
    offline();
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Open menu" }));
    const mobile = screen.getByRole("navigation", { name: "Mobile" });
    await user.click(within(mobile).getByRole("link", { name: /MCP server/ }));
    expect(window.location.pathname).toBe("/mcp");
    expect(screen.queryByRole("navigation", { name: "Mobile" })).not.toBeInTheDocument();
    // Section links from the MCP page lead back to the home page.
    expect(within(screen.getByRole("navigation", { name: "Primary" })).getByRole("link", { name: "Work" })).toHaveAttribute(
      "href",
      "/#work",
    );
  });
});

describe("MCP page", () => {
  it("is a route of its own, with or without a trailing slash", () => {
    expect(matchRoute("/mcp")).toEqual({ name: "mcp" });
    expect(matchRoute("/mcp/")).toEqual({ name: "mcp" });
  });

  it("derives the server URL from the API base, or the site's origin", () => {
    expect(mcpUrl("https://api.erick.dev")).toBe("https://api.erick.dev/mcp");
    expect(mcpUrl("")).toBe(`${window.location.origin}/mcp`);
    vi.stubEnv("VITE_API_URL", "https://api.erick.dev/");
    expect(mcpUrl()).toBe("https://api.erick.dev/mcp");
    vi.unstubAllEnvs();
  });

  it("gives every client its setup with the server URL", () => {
    const url = "https://api.erick.dev/mcp";
    render(<McpContent url={url} />);
    for (const client of ["Claude (web and desktop)", "Claude Code", "Codex", "ChatGPT", "Any MCP client"]) {
      expect(screen.getByRole("region", { name: client })).toBeInTheDocument();
    }
    expect(screen.getByText(`claude mcp add --transport http erick-portfolio ${url}`)).toBeInTheDocument();
    expect(screen.getByText(`codex mcp add erick-portfolio --url ${url}`)).toBeInTheDocument();
    const terms = (label: string) =>
      within(screen.getByLabelText(label)).getAllByRole("term").map((term) => term.textContent);
    expect(terms("Tools")).toEqual(TOOLS);
    expect(terms("Prompts")).toEqual(["hire_erick", "career_story"]);
  });

  it("copies the server URL and says so", async () => {
    const user = userEvent.setup(); // installs a clipboard stub on navigator
    render(<McpContent url="https://api.erick.dev/mcp" />);
    const button = screen.getByRole("button", { name: "Copy the server URL" });
    await user.click(button);
    expect(await navigator.clipboard.readText()).toBe("https://api.erick.dev/mcp");
    expect(button).toHaveTextContent("Copied");
  });

  it("asks to select the text when the clipboard is unavailable", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    render(<McpContent url="https://api.erick.dev/mcp" />);
    const button = screen.getByRole("button", { name: "Copy the Claude Code command" });
    await user.click(button);
    expect(button).toHaveTextContent("Select it");
  });

  it("is reachable by navigating in the app", () => {
    offline();
    render(<App />);
    act(() => navigate("/mcp"));
    expect(screen.getByText("Remote server · Streamable HTTP · no authentication · read-only, except contact.")).toBeInTheDocument();
  });
});
