/** Microsoft Clarity (heatmaps and session replays), loaded from a module because the
 * CSP allows no inline script. Only on the live site, and never for visitors who ask
 * not to be tracked. What people type (chat, search, contact form) is masked in the
 * markup with data-clarity-mask. */

export const CLARITY_ID = "z86318idoy";
const HOSTS = new Set(["erickkbonfim.com.br", "www.erickkbonfim.com.br"]);

type Queue = ((...args: unknown[]) => void) & { q?: unknown[][] };

export function wantsClarity(location: Pick<Location, "hostname">, nav: Navigator): boolean {
  const privacy = nav as Navigator & { globalPrivacyControl?: boolean };
  return HOSTS.has(location.hostname) && nav.doNotTrack !== "1" && privacy.globalPrivacyControl !== true;
}

export function startClarity(id: string = CLARITY_ID, doc: Document = document): void {
  const win = doc.defaultView as (Window & { clarity?: Queue }) | null;
  if (!win || win.clarity) return;
  const queue: Queue = (...args) => {
    (queue.q ??= []).push(args);
  };
  win.clarity = queue;
  const script = doc.createElement("script");
  script.async = true;
  script.src = `https://www.clarity.ms/tag/${id}`;
  doc.head.appendChild(script);
}
