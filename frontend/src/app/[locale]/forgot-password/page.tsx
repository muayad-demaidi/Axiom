"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { errMessage } from "@/lib/types";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sent" | "error">("idle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api("/api/auth/forgot", { method: "POST", json: { email } });
      setStatus("sent");
    } catch (e: unknown) {
      setStatus("error");
      setError(errMessage(e, "Could not send reset email"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="container max-w-md py-16">
      <h1 className="text-2xl font-bold">Reset your password</h1>
      <p className="text-[var(--text-muted)] mt-2 text-sm">
        Enter the email associated with your AXIOM account and we&apos;ll send you a link to set a new password.
      </p>
      {status === "sent" ? (
        <div className="card mt-6">
          <p className="text-sm">
            If an account exists for <strong>{email}</strong>, a reset link has been sent. The link expires in 1 hour.
          </p>
          <Link href="/login" className="btn btn-ghost mt-4">Back to sign in</Link>
        </div>
      ) : (
        <form onSubmit={submit} className="card mt-6 space-y-3">
          <label className="block text-sm">
            Email
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" />
          </label>
          {error && <div className="text-sm text-red-600">{error}</div>}
          <button className="btn btn-primary" disabled={busy}>{busy ? "Sending…" : "Send reset link"}</button>
          <div className="text-sm">
            <Link href="/login" className="text-[var(--accent)]">Back to sign in</Link>
          </div>
        </form>
      )}
    </main>
  );
}
