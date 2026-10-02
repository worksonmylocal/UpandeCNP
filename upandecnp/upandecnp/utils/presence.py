"""Who is using the field app, and when they last did.

The mobile app signs in with API tokens, not a Frappe session. That matters
here: Frappe's own "who is online" signals - the Sessions table and
User.last_active - are only written for cookie sessions, so a supervisor on
the app leaves no trace in either. An agronomist asking "who is out there?"
would be shown nobody, however many supervisors were working.

Presence is therefore recorded from the requests themselves. After each call
to this app's API by a signed-in user, the user's last-seen time, the call
made and whether it came from the app or the web are written to a small hash
in Redis. Redis rather than a table because this is ephemeral by nature - it
is only ever interesting for the next few hours, it changes on every request,
and a database write per request would cost more than the answer is worth. If
the cache is flushed the picture rebuilds within minutes as people carry on
working.

"Active" therefore means *made a request recently*, not *has the app open*: a
supervisor reading a screen without touching anything goes quiet. The
get_active_supervisors() window is generous for that reason.
"""

import time

import frappe

CACHE_KEY = "cnp_presence"
API_PREFIX = "/api/method/upandecnp.upandecnp.api."


def record_presence(response=None, request=None, **_):
	"""after_request hook. Runs for every request on the site - all of its apps
	- so the first thing it does is leave unless the call is ours, and it must
	never raise: Frappe isolates after_request failures, but a hook that logs
	an error per request would still bury the log."""
	try:
		if request is None or not request.path.startswith(API_PREFIX):
			return
		user = frappe.session.user
		if not user or user == "Guest":
			return

		frappe.cache.hset(CACHE_KEY, user, {
			"ts": time.time(),
			"method": request.path[len(API_PREFIX):].split("?")[0],
			# The app authenticates with a token header; the desk with a cookie.
			"via": "app" if request.headers.get("Authorization") else "web",
		})
	except Exception:
		pass


def read_presence():
	"""{user: {ts, method, via}}. Empty when the cache holds nothing or cannot
	be reached - callers treat that as "nobody seen", which is the truth."""
	try:
		raw = frappe.cache.hgetall(CACHE_KEY) or {}
	except Exception:
		return {}
	return {
		(k.decode() if isinstance(k, bytes) else k): v
		for k, v in raw.items() if isinstance(v, dict)
	}
