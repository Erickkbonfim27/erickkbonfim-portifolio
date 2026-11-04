import { useId, useRef, useState, type FormEvent } from "react";
import { api } from "../api/client";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/contact";

type Status = { kind: "idle" } | { kind: "sending" } | { kind: "sent" } | { kind: "error"; message: string };

interface Fields {
  from: string;
  contact: string;
  brief: string;
  company: string;
  website: string;
}

const EMPTY: Fields = { from: "", contact: "", brief: "", company: "", website: "" };

function newKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** Posts to /api/contact. One Idempotency-Key per message: a retry after a failure
 * reuses it (the API returns the same id instead of storing a duplicate); editing the
 * message starts a new one. */
export function ContactForm() {
  const { lang, t } = useI18n();
  const f = t.form;
  const id = useId();
  const [fields, setFields] = useState<Fields>(EMPTY);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const key = useRef<string | null>(null);

  const update = (name: keyof Fields) => (event: { target: { value: string } }) => {
    key.current = null;
    setFields((current) => ({ ...current, [name]: event.target.value }));
    if (status.kind === "error" || status.kind === "sent") setStatus({ kind: "idle" });
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (status.kind === "sending") return;
    key.current ??= newKey();
    setStatus({ kind: "sending" });
    try {
      const company = fields.company.trim();
      await api.contact(
        {
          from: fields.from,
          contact: fields.contact,
          brief: fields.brief,
          ...(company ? { company } : {}),
          lang,
          website: fields.website,
        },
        key.current,
      );
      key.current = null;
      setFields(EMPTY);
      setStatus({ kind: "sent" });
    } catch (error) {
      setStatus({ kind: "error", message: errorMessage(error, lang) });
    }
  };

  const sending = status.kind === "sending";
  return (
    <form className="cform" onSubmit={submit} aria-describedby={`${id}-privacy`} data-clarity-mask="true">
      <div className="cfields">
        <label className="cfield" htmlFor={`${id}-from`}>
          <span className="clabel mono">{f.name}</span>
          <input id={`${id}-from`} name="from" required maxLength={120} autoComplete="name" value={fields.from} onChange={update("from")} />
        </label>
        <label className="cfield" htmlFor={`${id}-contact`}>
          <span className="clabel mono">{f.contact}</span>
          <input
            id={`${id}-contact`}
            name="contact"
            required
            minLength={3}
            maxLength={200}
            autoComplete="email"
            value={fields.contact}
            onChange={update("contact")}
          />
        </label>
        <label className="cfield" htmlFor={`${id}-company`}>
          <span className="clabel mono">{f.company}</span>
          <input id={`${id}-company`} name="company" maxLength={120} autoComplete="organization" value={fields.company} onChange={update("company")} />
        </label>
        <label className="cfield wide" htmlFor={`${id}-brief`}>
          <span className="clabel mono">{f.brief}</span>
          <textarea
            id={`${id}-brief`}
            name="brief"
            required
            minLength={10}
            maxLength={4000}
            rows={4}
            value={fields.brief}
            onChange={update("brief")}
          />
        </label>
        {/* Honeypot: invisible to people and screen readers, tempting to naive bots. */}
        <div className="hp" aria-hidden="true">
          <label htmlFor={`${id}-website`}>Website</label>
          <input id={`${id}-website`} name="website" tabIndex={-1} autoComplete="off" value={fields.website} onChange={update("website")} />
        </div>
      </div>
      <div className="cactions">
        <button className="pillbtn pill-light" type="submit" disabled={sending}>
          {sending ? f.sending : f.send}
        </button>
        <p id={`${id}-privacy`} className="cnote mono">
          {f.privacy}
        </p>
      </div>
      <p className={status.kind === "error" ? "cstatus err" : "cstatus"} role={status.kind === "error" ? "alert" : "status"}>
        {status.kind === "sent" && f.sent}
        {status.kind === "error" && status.message}
      </p>
    </form>
  );
}
