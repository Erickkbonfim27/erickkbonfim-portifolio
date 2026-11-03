// What a visitor chose (language, theme), kept in this browser only. Storage can be
// missing or throw (private windows, blocked site data): the site then follows the
// URL and the system settings, and nothing breaks.

export function readPref(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writePref(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // not remembered: fine
  }
}
