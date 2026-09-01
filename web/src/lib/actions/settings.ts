"use server";

import { revalidatePath } from "next/cache";

import { getSessionUser } from "@/lib/data/auth";
import { setNotifyEmail } from "@/lib/data/settings";

export type SettingsState = { message: string; ok: boolean } | { message: ""; ok: true };

/**
 * The only write the frontend performs. It carries no user id from the client:
 * the id comes from the verified session, and RLS re-checks auth.uid() on the
 * row regardless.
 */
export async function saveNotifyEmail(
  _prev: SettingsState,
  formData: FormData,
): Promise<SettingsState> {
  const user = await getSessionUser();
  if (!user) return { ok: false, message: "Your session expired. Sign in again." };

  const result = await setNotifyEmail(user.id, formData.get("notify_email") === "on");
  if (result.ok) revalidatePath("/account");
  return result;
}
