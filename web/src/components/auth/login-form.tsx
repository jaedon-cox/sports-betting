"use client";

import { useFormState, useFormStatus } from "react-dom";

import { requestMagicLink, type LoginState } from "@/lib/actions/login";

function Submit() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className="btn-primary w-full" disabled={pending}>
      {pending ? "Sending…" : "Send sign-in link"}
    </button>
  );
}

export function LoginForm({ next }: { next: string }) {
  const [state, action] = useFormState<LoginState, FormData>(requestMagicLink, {
    status: "idle",
  });

  if (state.status === "sent") {
    return (
      <div className="rule-t pt-6">
        <p className="font-display text-2xl uppercase leading-none text-turf">
          Check your inbox
        </p>
        <p className="mt-3 text-sm leading-relaxed text-chalk/55">{state.message}</p>
      </div>
    );
  }

  return (
    <form action={action} className="space-y-4">
      <input type="hidden" name="next" value={next} />
      <label className="block">
        <span className="text-[10px] uppercase tracking-placard text-chalk/40">
          Email
        </span>
        <input
          type="email"
          name="email"
          autoComplete="email"
          required
          placeholder="you@example.com"
          className="field mt-1.5"
        />
      </label>
      <Submit />
      {(state.status === "error" || state.status === "unconfigured") && (
        <p
          role="status"
          className={`text-xs leading-relaxed ${
            state.status === "error" ? "text-clay" : "text-floodlight"
          }`}
        >
          {state.message}
        </p>
      )}
    </form>
  );
}
