import os
import re
import uuid
from datetime import datetime, timedelta
from functools import wraps

from bson import ObjectId
from flask import session, g, flash, redirect, url_for, request, current_app
from werkzeug.utils import secure_filename

from db import mongo

PHONE_RE = re.compile(r"^[6-9]\d{9}$")
CATEGORIES = ["Plumber", "Electrician", "Carpenter", "Cleaner", "Painter", "AC Repair"]
TIME_SLOTS = ["Morning (8 AM - 12 PM)", "Afternoon (12 PM - 4 PM)", "Evening (4 PM - 8 PM)"]
IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
VIDEO_EXT = {"mp4", "webm", "mov", "ogg"}
TRANSITIONS = {                      # provider action: (required status, new status)
    "accept": ("pending", "accepted"),
    "reject": ("pending", "rejected"),
    "complete": ("accepted", "completed"),
}


def oid(value):
    try:
        return ObjectId(value)
    except Exception:                # noqa: BLE001
        return None


def ist(dt):
    return (dt + timedelta(hours=5, minutes=30)).strftime("%d %b %Y, %I:%M %p")


# ------------------------------------------------------------ sessions / roles
def current_user():
    if "me" not in g:
        g.me = None
        uid = oid(session.get("uid"))
        if uid:
            g.me = mongo.users.find_one({"_id": uid})
    return g.me


def my_provider():
    """The provider profile of the logged-in provider."""
    if "my_provider" not in g:
        me = current_user()
        g.my_provider = (mongo.providers.find_one({"user_id": me["_id"]})
                         if me and me["role"] == "provider" else None)
    return g.my_provider


def home_for(user):
    return url_for("provider.dashboard" if user["role"] == "provider" else "customer.home")


def login_required(role):
    """Page is only for logged-in users of this role ('customer' or 'provider')."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            me = current_user()
            if not me:
                flash("Please log in to continue.", "error")
                return redirect(url_for(f"auth.{role}_login", next=request.path))
            if me["role"] != role:
                who = "service providers" if role == "provider" else "customers"
                flash(f"That page is only for {who}.", "error")
                return redirect(home_for(me))
            return fn(*a, **kw)
        return wrapper
    return deco


def start_session(user):
    session.clear()
    session["uid"] = str(user["_id"])


# ------------------------------------------------------------ data helpers
def save_media(files, kind):
    allowed = IMAGE_EXT if kind == "image" else VIDEO_EXT
    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    docs = []
    for f in files:
        if not f or not f.filename or "." not in f.filename:
            continue
        if f.filename.rsplit(".", 1)[-1].lower() not in allowed:
            continue
        name = f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"
        f.save(os.path.join(folder, name))
        docs.append({"type": kind, "filename": name,
                     "url": f"/static/uploads/{name}", "uploaded_at": datetime.utcnow()})
    return docs


def remove_media_file(filename):
    if not filename:
        return
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    if os.path.exists(path):
        os.remove(path)


def notify(recipient_id, message, booking_id=None):
    mongo.notifications.insert_one({
        "recipient_id": recipient_id, "message": message, "booking_id": booking_id,
        "read": False, "created_at": datetime.utcnow()})


def recalc_rating(provider_id):
    ratings = [r["rating"] for r in mongo.reviews.find({"provider_id": provider_id})]
    avg = round(sum(ratings) / len(ratings), 1) if ratings else 0
    mongo.providers.update_one({"_id": provider_id},
                               {"$set": {"rating_avg": avg, "rating_count": len(ratings)}})


def parse_location(f):
    """Read state/district/area/lat/lng from a form. Returns (location_doc, error)."""
    try:
        lat, lng = float(f["lat"]), float(f["lng"])
    except (KeyError, ValueError):
        return None, "Please enter the district and area, then click 'Show on map'."
    return {"type": "Point", "coordinates": [lng, lat],
            "area": f.get("area", "").strip(), "district": f.get("district", "").strip(),
            "state": f.get("state", "Tamil Nadu").strip()}, None
