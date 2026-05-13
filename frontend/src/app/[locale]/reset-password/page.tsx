"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api, setToken } from "@/lib/api";
import type { AuthResponse } from "@/lib/types";
import { errMessage } from "@/lib/types";

function ResetForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [token, setTokenInput] = useState(params.get("token") ?? "");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (pw !== pw2) { setError("Passwords don't match"); return; }
    setBusy(true); setError(null);
    try {
      const res = await api<AuthResponse>("/api/auth/reset", {
        method: "POST",
        json: { token, new_password: pw },
      });
      setToken(res.token);
      router.push("/app");
    } catch (e: unknown) {
      setError(errMessage(e, "Could not reset password"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card mt-6 space-y-3">
      <label className="block text-sm">
        Reset token
        <input required value={token} onChange={(e) => setTokenInput(e.target.value)}
          className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm font-mono" />
      </label>
      <label className="block text-sm">
        New password
        <input type="password" required minLength={6} value={pw} onChange={(e) => setPw(e.target.value)}
          className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" />
      </label>
      <label className="block text-sm">
        Confirm new password
        <input type="password" required minLength={6} value={pw2} onChange={(e) => setPw2(e.target.value)}
          className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" />
      </label>
      {error && <div className="text-sm text-red-600">{error}</div>}
      <button className="btn btn-primary" disabled={busy || !token || !pw}>
        {busy ? "Resetting…" : "Reset password"}
      </button>
      <div className="text-sm">
        <Link href="/login" className="text-[var(--accent)]">Back to sign in</Link>
      </div>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="container max-w-md py-16">
      <h1 className="text-2xl font-bold">Set a new password</h1>
      <p className="text-[var(--text-muted)] mt-2 text-sm">
        Paste the token from your reset email (or follow the link directly).
      </p>
      <Suspense fallback={<div className="card mt-6 text-sm">Loading…</div>}>
        <ResetForm />
      </Suspense>
    </main>
  );
}
