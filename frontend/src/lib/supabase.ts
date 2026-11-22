import { createClient } from "@supabase/supabase-js";

// Supabase publishable keys are designed for browser use; database access is
// protected by Supabase Auth and Row Level Security. Hosting variables override
// these deployment defaults when configured.
const supabaseUrl =
  import.meta.env.VITE_SUPABASE_URL || "https://ktplejfrvshcnqugeorp.supabase.co";
const supabasePublishableKey =
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ||
  "sb_publishable_yaQBFN-tLhgXsk8W_xUfjw_qFCM8pLc";

export const isSupabaseConfigured = Boolean(supabaseUrl && supabasePublishableKey);

export const supabase = isSupabaseConfigured
  ? createClient(supabaseUrl, supabasePublishableKey)
  : null;
