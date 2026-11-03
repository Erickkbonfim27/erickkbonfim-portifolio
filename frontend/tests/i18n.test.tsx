import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { ContactForm } from "../src/components/ContactForm";
import { landingRedirect } from "../src/lib/locale";
import { localize, matchRoute, splitLang } from "../src/lib/router";
import { initTheme } from "../src/lib/theme";
import { entry, json, mockFetch } from "./helpers";

function offline() {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
}

function browserLanguages(languages: string[]) {
  vi.spyOn(window.navigator, "languages", "get").mockReturnValue(languages);
}

function systemDark(dark: boolean) {
  const listeners: (() => void)[] = [];
  const query = { matches: dark, addEventListener: (_: string, listener: () => void) => listeners.push(listener) };
  vi.stubGlobal("matchMedia", vi.fn(() => query));
  return {
    change(next: boolean) {
      query.matches = next;
      listeners.forEach((listener) => listener());
    },
  };
}

describe("language in the URL", () => {
  it("keeps English at the root and Portuguese under /pt", () => {
    expect(splitLang("/pt/work/rhye")).toEqual({ lang: "pt", path: "/work/rhye" });
    expect(splitLang("/pt")).toEqual({ lang: "pt", path: "/" });
    expect(splitLang("/ptx")).toEqual({ lang: "en", path: "/ptx" });
    expect(matchRoute("/pt/work/rhye/")).toEqual({ lang: "pt", name: "case", slug: "rhye" });
    expect(matchRoute("/pt/")).toEqual({ lang: "pt", name: "home" });
    expect([localize("/", "pt"), localize("/#work", "pt"), localize("/mcp", "pt"), localize("/mcp", "en")]).toEqual([
      "/pt",
      "/pt#work",
      "/pt/mcp",
      "/mcp",
    ]);
  });

  it("sends a Portuguese browser to /pt once, unless the visitor chose English", () => {
    const at = (pathname: string, search = "", hash = "") => ({ pathname, search, hash });
    browserLanguages(["pt-BR", "en"]);
    expect(landingRedirect(at("/work/rhye", "?x=1", "#top"))).toBe("/pt/work/rhye?x=1#top");
    expect(landingRedirect(at("/pt/mcp"))).toBeNull();
    window.localStorage.setItem("lang", "en");
    expect(landingRedirect(at("/"))).toBeNull();
    browserLanguages(["en-US"]);
    window.localStorage.setItem("lang", "pt");
    expect(landingRedirect(at("/"))).toBe("/pt");
    window.localStorage.clear();
    expect(landingRedirect(at("/"))).toBeNull();
  });
});

describe("Portuguese pages", () => {
  it("render the copy, the html lang and API content in Portuguese", async () => {
    const { calls } = mockFetch({ "/api/projects/rhye": entry({ summary: "Resumo da API." }) });
    window.history.replaceState({}, "", "/pt");
    render(<App />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Engenheiro de software e IA. EK Integrações, dados e agentes em produção.");
    expect(await screen.findByText("Resumo da API.")).toBeInTheDocument();
    expect(calls.every((call) => call.url.searchParams.get("lang") === "pt")).toBe(true);
    expect(document.documentElement.lang).toBe("pt-BR");
    expect(document.title).toBe("Erick Kopak Bonfim — Engenheiro de Software e IA");
    expect(screen.getByText("MAI 2026 — OUT 2026")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Case da Rhye" })).toHaveAttribute("href", "/pt/work/rhye");
    const primary = screen.getByRole("navigation", { name: "Principal" });
    expect(within(primary).getByRole("link", { name: "Projetos" })).toHaveAttribute("href", "#work");
    expect(within(primary).getByRole("link", { name: "MCP" })).toHaveAttribute("href", "/pt/mcp");
  });

  it("lead back to the Portuguese home from other pages", async () => {
    mockFetch({});
    window.history.replaceState({}, "", "/pt/work/ghost");
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Nada por aqui." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar ao portfólio" })).toHaveAttribute("href", "/pt");
    const primary = screen.getByRole("navigation", { name: "Principal" });
    expect(within(primary).getByRole("link", { name: "Princípios" })).toHaveAttribute("href", "/pt#approach");
  });
});

describe("language switch", () => {
  it("opens the same page in the other language, remembers it and refetches", async () => {
    const { calls } = mockFetch({
      "/api/projects/rhye": (url: URL) => json(entry({ title: url.searchParams.get("lang") === "pt" ? "Rhye (PT)" : "Rhye" })),
    });
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/work/rhye");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Rhye" })).toBeInTheDocument();
    const toPt = screen.getAllByRole("link", { name: "Ver em português" })[0] as HTMLElement;
    expect(toPt).toHaveAttribute("href", "/pt/work/rhye");
    await user.click(toPt);
    expect(window.location.pathname).toBe("/pt/work/rhye");
    expect(await screen.findByRole("heading", { level: 1, name: "Rhye (PT)" })).toBeInTheDocument();
    expect(window.localStorage.getItem("lang")).toBe("pt");
    expect(calls.at(-1)?.url.searchParams.get("lang")).toBe("pt");
    await user.click(screen.getAllByRole("link", { name: "View in English" })[0] as HTMLElement);
    expect(window.location.pathname).toBe("/work/rhye");
    expect(window.localStorage.getItem("lang")).toBe("en");
  });

  it("is in the phone menu too, which closes on the way", async () => {
    offline();
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Open menu" }));
    const prefs = within(screen.getByRole("navigation", { name: "Mobile" })).getByRole("group", { name: "Preferences" });
    await user.click(within(prefs).getByRole("link", { name: "Ver em português" }));
    expect(window.location.pathname).toBe("/pt");
    expect(screen.queryByRole("navigation", { name: "Menu" })).not.toBeInTheDocument();
  });
});

describe("theme", () => {
  it("follows the system until the visitor picks one", () => {
    const system = systemDark(true);
    initTheme();
    expect(document.documentElement.dataset.theme).toBe("dark");
    system.change(false);
    expect(document.documentElement.dataset.theme).toBe("light");
    window.localStorage.setItem("theme", "dark");
    system.change(false);
    initTheme();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("switches from the header and remembers the choice", async () => {
    systemDark(false);
    initTheme();
    offline();
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getAllByRole("button", { name: "Switch to the dark theme" })[0] as HTMLElement);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("theme")).toBe("dark");
    await user.click(screen.getAllByRole("button", { name: "Switch to the light theme" })[0] as HTMLElement);
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("works without storage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    systemDark(true);
    initTheme();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(landingRedirect({ pathname: "/", search: "", hash: "" })).toBeNull();
  });
});

describe("contact form in Portuguese", () => {
  it("sends the language and keeps the API's English detail off the page", async () => {
    const { calls } = mockFetch({ "/api/contact": () => json({ detail: "brief needs 10 to 4000 characters" }, 422) });
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/pt");
    render(<ContactForm />);
    await user.type(screen.getByLabelText("Seu nome"), "Ana");
    await user.type(screen.getByLabelText("E-mail ou telefone"), "ana@corp.dev");
    await user.type(screen.getByLabelText("A vaga ou o projeto"), "Vaga de AI Engineer.");
    await user.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Confira os campos e tente de novo.");
    await waitFor(() => expect(JSON.parse(String(calls[0]?.init?.body)).lang).toBe("pt"));
  });
});
