"use client";

import { useFormState, useFormStatus } from "react-dom";

import { saveNotifyEmail, type SettingsState } from "@/lib/actions/settings";

function Save() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className="btn-ghost" disabled={pending}>
      {pending ? "Saving…" : "Save"}
    </button>
  );
}

export function NotifyForm({ initial }: { initial: boolean }) {
  const [state, action] = useFormState<SettingsState, FormData>(saveNotifyEmail, {
    message: "",
    ok: true,
  });

  return (
    <form action={action} className="flex flex-wrap items-center gap-5">
      <label className="flex items-center gap-3">
        <input
          type="checkbox"
          name="notify_email"
          defaultChecked={initial}
          className="h-4 w-4 accent-[#E8A33D]"
        />
        <span className="text-sm text-chalk/70">
          Email me when the day&rsquo;s board publishes
        </span>
      </label>
      <Save />
      {state.message && (
        <p role="status" className={`text-xs ${state.ok ? "text-turf" : "text-clay"}`}>
          {state.message}
        </p>
      )}
    </form>
  );
}
