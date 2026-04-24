"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { api, setToken } from "@/lib/api";
import type { AuthResponse } from "@/lib/types";
import { errMessage } from "@/lib/types";
// Forgot-password link is rendered below the form.

export default function LoginPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const res = await api<AuthResponse>("/api/auth/login", {
        method: "POST",
        json: { email_or_username: identifier, password },
      });
      setToken(res.token);
      router.push("/app");
    } catch (e: unknown) {
      setError(errMessage(e, "Login failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4">
      <Link
        href="/"
        aria-label="AXIOM home"
        className="flex items-center gap-3 mb-8 font-semibold text-lg tracking-tight"
      >
        <Image
          src="/logo-mark.png"
          alt=""
          aria-hidden="true"
          width={40}
          height={40}
          priority
          className="h-10 w-10 object-contain"
        />
        <span>AXIOM</span>
      </Link>
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <h1 className="text-xl font-bold">Sign in</h1>
        <input
          className="w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          placeholder="Email or username"
          value={identifier} onChange={(e) => setIdentifier(e.target.value)} required
        />
        <input
          className="w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          placeholder="Password" type="password"
          value={password} onChange={(e) => setPassword(e.target.value)} required
        />
        {error && <div className="text-sm text-red-600">{error}</div>}
        <button type="submit" className="btn btn-primary w-full justify-center" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <div className="flex justify-between text-xs text-[var(--text-muted)]">
          <Link href="/signup" className="text-[var(--accent)]">Create an account</Link>
          <Link href="/forgot-password" className="text-[var(--accent)]">Forgot password?</Link>
        </div>
      </form>
    </main>
  );
}
