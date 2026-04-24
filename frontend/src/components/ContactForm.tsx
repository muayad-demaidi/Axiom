"use client";
import { useState } from "react";

type Status = { kind: "idle" } | { kind: "sending" } | { kind: "ok" } | { kind: "error"; message: string };

export function ContactForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (status.kind === "sending") return;
    const trimmedName = name.trim();
    const trimmedEmail = email.trim();
    const trimmedMessage = message.trim();
    if (!trimmedName || !trimmedEmail || trimmedMessage.length < 5) {
      setStatus({ kind: "error", message: "Please fill in your name, email, and a short message." });
      return;
    }
    setStatus({ kind: "sending" });
    try {
      const res = await fetch("/api/support/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ name: trimmedName, email: trimmedEmail, message: trimmedMessage }),
      });
      if (!res.ok) {
        let detail = `Request failed (${res.status})`;
        try {
          const j = (await res.json()) as { detail?: string };
          if (j?.detail) detail = j.detail;
        } catch { /* ignore */ }
        throw new Error(detail);
      }
      setStatus({ kind: "ok" });
      setName("");
      setEmail("");
      setMessage("");
    } catch (err) {
      setStatus({
        kind: "error",
        message: err instanceof Error ? err.message : "Could not send — please try again.",
      });
    }
  }

  const busy = status.kind === "sending";

  return (
    <form className="card mt-8 space-y-3" onSubmit={onSubmit} noValidate>
      <div>
        <label htmlFor="contact-name" className="block text-xs font-medium mb-1">
          Name
        </label>
        <input
          id="contact-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={120}
          disabled={busy}
          className="w-full border border-[var(--border)] rounded px-3 py-2 text-sm bg-transparent"
          autoComplete="name"
        />
      </div>
      <div>
        <label htmlFor="contact-email" className="block text-xs font-medium mb-1">
          Email
        </label>
        <input
          id="contact-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          maxLength={254}
          disabled={busy}
          className="w-full border border-[var(--border)] rounded px-3 py-2 text-sm bg-transparent"
          autoComplete="email"
        />
      </div>
      <div>
        <label htmlFor="contact-message" className="block text-xs font-medium mb-1">
          Message
        </label>
        <textarea
          id="contact-message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          required
          rows={5}
          maxLength={5000}
          disabled={busy}
          className="w-full border border-[var(--border)] rounded px-3 py-2 text-sm bg-transparent"
          placeholder="How can we help?"
        />
      </div>
      <div className="flex items-center gap-3 pt-1">
        <button type="submit" disabled={busy} className="btn btn-primary text-sm">
          {busy ? "Sending…" : "Send message"}
        </button>
        {status.kind === "ok" && (
          <span className="text-xs text-[var(--accent)]">Thanks — we&rsquo;ll get back to you shortly.</span>
        )}
        {status.kind === "error" && (
          <span className="text-xs text-red-600">{status.message}</span>
        )}
      </div>
    </form>
  );
}
