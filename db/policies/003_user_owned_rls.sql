-- User-owned tables (§3.5): profiles / user_settings / user_saved_picks
-- add an auth.uid() = user_id row filter on top of authenticated-only
-- access. This is the ONLY user-facing write path in the whole schema —
-- every other write comes from the pipeline's service-role key, which
-- bypasses RLS entirely (§5).

CREATE POLICY own_profile_select ON profiles
    FOR SELECT TO authenticated USING (auth.uid() = id);
CREATE POLICY own_profile_update ON profiles
    FOR UPDATE TO authenticated USING (auth.uid() = id) WITH CHECK (auth.uid() = id);
-- No INSERT policy: fn_handle_new_auth_user() (006_users_and_auth.sql)
-- provisions this row via SECURITY DEFINER on signup.

CREATE POLICY own_settings_select ON user_settings
    FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY own_settings_update ON user_settings
    FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
-- Belt-and-suspenders INSERT policy in case a row is ever missing (the
-- signup trigger is the normal path and already covers this).
CREATE POLICY own_settings_insert ON user_settings
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

CREATE POLICY own_saved_picks_select ON user_saved_picks
    FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY own_saved_picks_insert ON user_saved_picks
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY own_saved_picks_delete ON user_saved_picks
    FOR DELETE TO authenticated USING (auth.uid() = user_id);

GRANT SELECT, UPDATE ON profiles TO authenticated;
GRANT SELECT, INSERT, UPDATE ON user_settings TO authenticated;
GRANT SELECT, INSERT, DELETE ON user_saved_picks TO authenticated;
