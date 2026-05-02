"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { api, setToken } from "@/lib/api";
import type { AuthResponse } from "@/lib/types";
import { errMessage } from "@/lib/types";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const res = await api<AuthResponse>("/api/auth/register", {
        method: "POST",
        json: {
          email: email.trim(),
          username: username.trim(),
          password,
          full_name: fullName.trim() || undefined,
        },
      });
      setToken(res.token);
      router.push("/app");
    } catch (e: unknown) {
      setError(errMessage(e, "Sign-up failed"));
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
        <h1 className="text-xl font-bold">Create your account</h1>
        <p className="text-xs text-[var(--text-muted)]">60 days of full Tier 3 access. No card required.</p>
        <input className="w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          placeholder="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          autoComplete="email"
          inputMode="email"
        />
        <input className="w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} required
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          autoComplete="username"
          inputMode="text"
        />
        <input className="w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          placeholder="Full name (optional)" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        <input className="w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          placeholder="Password (min 6 chars)" type="password" value={password}
          onChange={(e) => setPassword(e.target.value)} required minLength={6} />
        {error && <div className="text-sm text-red-600">{error}</div>}
        <button type="submit" className="btn btn-primary w-full justify-center" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
        <p className="text-xs text-[var(--text-muted)] text-center">
          Already have an account? <Link href="/login" className="text-[var(--accent)]">Sign in</Link>
        </p>
      </form>
    </main>
  );
}
