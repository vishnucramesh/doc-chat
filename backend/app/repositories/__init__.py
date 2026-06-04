"""Data-access layer.

Plain async functions, one module per table, that wrap the Supabase client.
Routers and services call these instead of building `sb.table(...)` chains
inline. Two reasons:

1. **The tenant boundary is structural here, not remembered.** Every function
   that touches a user-owned row takes `user_id` as a required argument and
   applies the `.eq("user_id", user_id)` filter itself. The service-role
   client bypasses RLS by design (see `services/supabase.py`), so that filter
   is the *only* thing keeping tenants apart — centralizing it means a call
   site can't forget it.
2. Routers stay thin: HTTP concerns (status codes, validation, the SSE stream,
   storage + background tasks) live in the router; persistence lives here.

These are deliberately functions, not a repository class hierarchy — same
framework-light philosophy as the rest of `services/`.
"""
