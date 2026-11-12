"""
Naughty List: a CTFd plugin for the Evil Santa theme (works with any theme).

* /naughty-list         everyone can read it
* /admin/naughty-list   admins add or remove entries

Each entry records who (a team or a player), what they did, and the verdict:
a warning, or a ban. A ban also bans the account in CTFd. The team (or the
player, in user mode) can automatically get a notification about it.
Removing an entry undoes its ban and removes its notification.
"""
import datetime

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from CTFd.cache import clear_standings, clear_team_session, clear_user_session
from CTFd.models import Notifications, Teams, Users, db
from CTFd.plugins import register_admin_plugin_menu_bar, register_user_page_menu_bar
from CTFd.schemas.notifications import NotificationSchema
from CTFd.utils.decorators import admins_only


class NaughtyEntry(db.Model):
    __tablename__ = "naughty_list"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    name = db.Column(db.String(128))  # kept even if the account is deleted later
    reason = db.Column(db.Text)
    action = db.Column(db.String(16))  # "warning" or "ban"
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    notification_id = db.Column(db.Integer, nullable=True)

    user = db.relationship("Users", foreign_keys=[user_id], lazy="select")
    team = db.relationship("Teams", foreign_keys=[team_id], lazy="select")


naughty = Blueprint("naughty_list", __name__)


def _set_banned(team_id, user_id, banned):
    target = Teams.query.filter_by(id=team_id).first() if team_id else Users.query.filter_by(id=user_id).first()
    if target is None:
        return
    target.banned = banned
    db.session.commit()
    if team_id:
        clear_team_session(team_id=team_id)
    else:
        clear_user_session(user_id=user_id)
    clear_standings()


@naughty.route("/naughty-list")
def listing():
    entries = NaughtyEntry.query.order_by(NaughtyEntry.date.desc()).all()
    # Use the theme's own page if it has one, otherwise the plugin's plain page
    return render_template(
        ["naughty_list.html", "plugins/naughty_list/templates/naughty_list.html"],
        entries=entries,
    )


@naughty.route("/admin/naughty-list", methods=["GET"])
@admins_only
def admin_listing():
    entries = NaughtyEntry.query.order_by(NaughtyEntry.date.desc()).all()
    teams = Teams.query.order_by(Teams.name).all()
    users = Users.query.filter_by(type="user").order_by(Users.name).all()
    return render_template(
        "plugins/naughty_list/templates/admin.html", entries=entries, teams=teams, users=users
    )


@naughty.route("/admin/naughty-list/add", methods=["POST"])
@admins_only
def admin_add():
    target = request.form.get("target", "")
    reason = (request.form.get("reason") or "").strip()
    action = "ban" if request.form.get("action") == "ban" else "warning"
    # "none", "team" (only the team/player concerned) or "everyone"
    notify = request.form.get("notify", "team")
    if notify not in ("none", "team", "everyone"):
        notify = "team"

    kind, _, raw_id = target.partition(":")
    if kind not in ("team", "user") or not raw_id.isdigit() or not reason:
        abort(400)

    entry = NaughtyEntry(reason=reason, action=action)
    if kind == "team":
        team = Teams.query.filter_by(id=int(raw_id)).first_or_404()
        entry.team_id, entry.name = team.id, team.name
        note_team, note_user = team.id, None
    else:
        user = Users.query.filter_by(id=int(raw_id)).first_or_404()
        entry.user_id, entry.name = user.id, user.name
        # In team mode the whole team hears about it; in user mode just the player
        note_team, note_user = (user.team_id, None) if user.team_id else (None, user.id)

    if notify != "none":
        verdict = "banned" if action == "ban" else "given a warning"
        content = f"**{entry.name}** has been {verdict}.\n\n**Reason:** {reason}"
        if notify == "everyone":
            note = Notifications(title="Naughty List update", content=content)
        else:
            note = Notifications(
                title="You're on the Naughty List!", content=content,
                team_id=note_team, user_id=note_user,
            )
        db.session.add(note)
        db.session.flush()
        entry.notification_id = note.id

    db.session.add(entry)
    db.session.commit()

    # Announcements to everyone also pop up live, like the admin panel's own notifications
    if notify == "everyone":
        data = NotificationSchema().dump(note).data
        data["type"], data["sound"] = "toast", True
        current_app.events_manager.publish(data=data, type="notification")

    if action == "ban":
        _set_banned(entry.team_id, entry.user_id, True)
    return redirect(url_for("naughty_list.admin_listing"))


@naughty.route("/admin/naughty-list/<int:entry_id>/delete", methods=["POST"])
@admins_only
def admin_delete(entry_id):
    entry = NaughtyEntry.query.filter_by(id=entry_id).first_or_404()
    team_id, user_id, was_ban = entry.team_id, entry.user_id, entry.action == "ban"
    if entry.notification_id:
        Notifications.query.filter_by(id=entry.notification_id).delete()
    db.session.delete(entry)
    db.session.commit()

    if was_ban:
        # Lift the ban only if no other ban entry remains for the same account
        others = NaughtyEntry.query.filter_by(action="ban", team_id=team_id, user_id=user_id).count()
        if others == 0:
            _set_banned(team_id, user_id, False)
    return redirect(url_for("naughty_list.admin_listing"))


def load(app):
    app.db.create_all()
    app.register_blueprint(naughty)
    register_admin_plugin_menu_bar("Naughty List", "/admin/naughty-list")
    register_user_page_menu_bar("Naughty List", "/naughty-list")
