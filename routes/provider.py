from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, session

from db import mongo
from utils import (CATEGORIES, TRANSITIONS, login_required, current_user, my_provider, oid,
                   notify, save_media, remove_media_file, parse_location)

bp = Blueprint("provider", __name__, url_prefix="/provider")

TABS = [("pending", "Pending", ["pending"]),
        ("active", "Accepted", ["accepted"]),
        ("completed", "Completed", ["completed"]),
        ("closed", "Rejected / Cancelled", ["rejected", "cancelled"])]


def _profile_or_logout():
    p = my_provider()
    if not p:
        session.clear()
        abort(404)
    return p


@bp.route("/")
@login_required("provider")
def dashboard():
    p = _profile_or_logout()
    items = list(mongo.bookings.find({"provider_id": p["_id"]}).sort("date", 1))
    by = lambda *s: [b for b in items if b["status"] in s]          # noqa: E731
    stats = {
        "pending": len(by("pending")), "accepted": len(by("accepted")),
        "completed": len(by("completed")),
        "earnings": sum(b["amount"] for b in by("completed")),
    }
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    upcoming = [b for b in by("accepted") if b["date"] >= today][:5]
    return render_template("provider/dashboard.html", p=p, stats=stats,
                           pending=by("pending")[:5], upcoming=upcoming)


@bp.route("/requests")
@login_required("provider")
def requests_page():
    p = _profile_or_logout()
    tab = request.args.get("tab", "pending")
    items = list(mongo.bookings.find({"provider_id": p["_id"]}).sort("date", -1))
    counts = {key: len([b for b in items if b["status"] in sts]) for key, _, sts in TABS}
    wanted = next((sts for key, _, sts in TABS if key == tab), TABS[0][2])
    shown = [b for b in items if b["status"] in wanted]
    return render_template("provider/requests.html", tabs=TABS, tab=tab, counts=counts, items=shown)


@bp.route("/bookings/<bid>/<action>", methods=["POST"])
@login_required("provider")
def booking_action(bid, action):
    p = _profile_or_logout()
    b = mongo.bookings.find_one({"_id": oid(bid)})
    if not b or action not in TRANSITIONS:
        abort(400)
    if b["provider_id"] != p["_id"]:
        abort(403)
    src, dst = TRANSITIONS[action]
    back = redirect(request.form.get("back") or url_for("provider.requests_page"))
    if b["status"] != src:
        flash("This booking has already been updated.", "error")
        return back
    day = b["date"].strftime("%d %b %Y")
    texts = {
        "accepted": (f"{p['name']} accepted your booking for {day} ({b['time_slot']}).",
                     "Accepted by provider"),
        "rejected": (f"{p['name']} could not take your booking for {day}. "
                     "Please choose another provider.", "Rejected by provider"),
        "completed": (f"Your job with {p['name']} is marked as completed. "
                      "You can now leave a review.", "Job marked as completed"),
    }
    message, note = texts[dst]
    mongo.bookings.update_one({"_id": b["_id"]}, {
        "$set": {"status": dst},
        "$push": {"timeline": {"status": dst, "note": note, "at": datetime.utcnow()}}})
    notify(b["customer_id"], message, b["_id"])
    flash(f"Booking {dst}. The customer has been notified.", "success")
    return back


@bp.route("/profile", methods=["GET", "POST"])
@login_required("provider")
def profile():
    p = _profile_or_logout()
    me = current_user()
    if request.method == "POST":
        f = request.form
        location, err = parse_location(f)
        if err:
            flash(err, "error")
            return redirect(url_for("provider.profile"))
        update = {
            "name": f["name"].strip(), "category": f["category"],
            "price_per_hour": int(f.get("price") or 0),
            "experience_years": int(f.get("experience") or 0),
            "description": f.get("description", "").strip(),
            "available": f.get("available") == "on", "location": location}
        mongo.providers.update_one({"_id": p["_id"]}, {"$set": update})
        mongo.users.update_one({"_id": me["_id"]}, {"$set": {"name": update["name"]}})
        flash("Profile updated.", "success")
        return redirect(url_for("provider.profile"))
    return render_template("provider/profile.html", p=p, categories=CATEGORIES, loc=p["location"])


@bp.route("/delete-account", methods=["POST"])
@login_required("provider")
def delete_account():
    p = _profile_or_logout()
    me = current_user()
    for m in p.get("media", []):
        remove_media_file(m.get("filename"))
    for b in mongo.bookings.find({"provider_id": p["_id"], "status": {"$in": ["pending", "accepted"]}}):
        mongo.bookings.update_one({"_id": b["_id"]}, {
            "$set": {"status": "cancelled"},
            "$push": {"timeline": {"status": "cancelled", "note": "Provider closed their account",
                                   "at": datetime.utcnow()}}})
        notify(b["customer_id"], f"{p['name']} is no longer available. Your booking was cancelled.", b["_id"])
    mongo.providers.delete_one({"_id": p["_id"]})
    mongo.notifications.delete_many({"recipient_id": me["_id"]})
    mongo.users.delete_one({"_id": me["_id"]})
    session.clear()
    flash("Your provider account was deleted.", "success")
    return redirect(url_for("auth.landing"))


@bp.route("/gallery", methods=["GET", "POST"])
@login_required("provider")
def gallery():
    p = _profile_or_logout()
    if request.method == "POST":
        images = save_media(request.files.getlist("images"), "image")
        video = save_media(request.files.getlist("video")[:1], "video")
        if video:                                  # only one video: replace the old one
            for m in p.get("media", []):
                if m["type"] == "video":
                    remove_media_file(m.get("filename"))
            mongo.providers.update_one({"_id": p["_id"]}, {"$pull": {"media": {"type": "video"}}})
        if images or video:
            mongo.providers.update_one({"_id": p["_id"]}, {"$push": {"media": {"$each": images + video}}})
            flash(f"{len(images)} photo(s) and {len(video)} video uploaded.", "success")
        else:
            flash("Please choose a valid image or video file.", "error")
        return redirect(url_for("provider.gallery"))
    return render_template("provider/gallery.html", p=p)


@bp.route("/gallery/<filename>/delete", methods=["POST"])
@login_required("provider")
def delete_media(filename):
    p = _profile_or_logout()
    if any(m.get("filename") == filename for m in p.get("media", [])):
        mongo.providers.update_one({"_id": p["_id"]}, {"$pull": {"media": {"filename": filename}}})
        remove_media_file(filename)
    return redirect(url_for("provider.gallery"))


@bp.route("/reviews")
@login_required("provider")
def reviews():
    p = _profile_or_logout()
    data = list(mongo.reviews.find({"provider_id": p["_id"]}).sort("created_at", -1))
    return render_template("provider/reviews.html", p=p, reviews=data)


@bp.route("/notifications")
@login_required("provider")
def notifications():
    me = current_user()
    notes = list(mongo.notifications.find({"recipient_id": me["_id"]})
                 .sort("created_at", -1).limit(50))
    mongo.notifications.update_many({"recipient_id": me["_id"], "read": False},
                                    {"$set": {"read": True}})
    return render_template("notifications.html", notes=notes)
