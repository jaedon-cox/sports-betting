-- Users / auth (§3.2, §3.5). Auth is fully delegated to Supabase Auth —
-- invite-only via auth.admin.inviteUserByEmail() with self-serve signup
-- disabled; auth.users existence IS the allowlist, no custom table.
-- profiles/user_settings/user_saved_picks are the only app-owned,
-- user-mutable tables in the whole schema (the other exception besides
-- pipeline_runs and the model_runs status flip, §3.1).

CREATE TABLE profiles (
    id            UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
    display_name  TEXT,
    role          TEXT NOT NULL DEFAULT 'user',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_settings (
    user_id       UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
    -- Bankroll immutability (§3.5): the only $ figure anywhere in the
    -- schema, and it is deliberately NOT joined into historical picks —
    -- picks.kelly_stake_fraction is a % and is the only stake figure ever
    -- persisted, so changing this value never rewrites historical stakes.
    bankroll_usd  NUMERIC(12, 2) NOT NULL DEFAULT 0,
    notify_email  BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_user_settings_touch_updated_at
    BEFORE UPDATE ON user_settings
    FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();

-- Deferred/optional per the doc's sketch — created now since the table
-- costs nothing empty and a future "save a pick" feature needs no
-- migration to land.
CREATE TABLE user_saved_picks (
    user_id   UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    pick_id   BIGINT NOT NULL REFERENCES picks (id),
    saved_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, pick_id)
);

-- Auto-provisions a profiles row on signup (invite acceptance) so the
-- frontend never has to special-case "authenticated but no profile yet."
CREATE OR REPLACE FUNCTION fn_handle_new_auth_user() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    INSERT INTO public.profiles (id, display_name) VALUES (NEW.id, NEW.email);
    INSERT INTO public.user_settings (user_id) VALUES (NEW.id);
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION fn_handle_new_auth_user();
