# Naughty List (CTFd plugin)

Adds a public **Naughty List** page (`/naughty-list`, linked in the navbar) and an
admin page (`Admin → Plugins → Naughty List`, at `/admin/naughty-list`).

Admins add a team or player, what they did, and the verdict:

- **Warning:** listed publicly.
- **Ban:** listed publicly and the account is banned in CTFd.

The admin chooses who gets a notification: only the team concerned (or the
player in user mode), everyone (with a live pop-up), or nobody. Removing an
entry deletes its notification and lifts the ban, unless another ban entry
for the same account remains.

Install: copy this `naughty_list` folder into `CTFd/CTFd/plugins/` and restart CTFd.
The Evil Santa theme styles the page and shows these notifications only to the
team they're for.
