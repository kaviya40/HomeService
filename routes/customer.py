import re
from datetime import datetime

from flask import (Blueprint, render_template, request, redirect, url_for, flash, abort)

from db import mongo
from utils import (CATEGORIES, TIME_SLOTS, login_required, current_user, oid, notify,
                   recalc_rating)

bp = Blueprint("customer", __name__, url_prefix="/customer")

SORTS = {
    "new": [("created_at", -1)],
    "rating": [("rating_avg", -1), ("rating_count", -1)],
    "price_low": [("price_per_hour", 1)],
    "price_high": [("price_per_hour", -1)],
}


@bp.route("/")
@login_required("customer")
def home():
    q = {"user_id": {"$exists": True}, "available": {"$ne": False}}
    cat = request.args.get("category", "")
    search = request.args.get("q", "").strip()
    sort = request.args.get("sort", "new")
    if cat:
        q["category"] = cat
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        q["$or"] = [{"name": rx}, {"location.area": rx}, {"location.district": rx}]
    data = list(mongo.providers.find(q).sort(SORTS.get(sort, SORTS["new"])))
    return render_template("customer/home.html", providers=data, categories=CATEGORIES,
                           cat=cat, search=search, sort=sort)


@bp.route("/provider/<pid>")
@login_required("customer")
def provider_view(pid):
    p = mongo.providers.find_one({"_id": oid(pid)})
    if not p or "user_id" not in p:
        abort(404)
    reviews = list(mongo.reviews.find({"provider_id": p["_id"]}).sort("created_at", -1))
    jobs_done = mongo.bookings.count_documents({"provider_id": p["_id"], "status": "completed"})
    return render_template("customer/provider.html", p=p, reviews=reviews, jobs_done=jobs_done,
                           slots=TIME_SLOTS, today=datetime.now().strftime("%Y-%m-%d"))


@bp.route("/provider/<pid>/book", methods=["POST"])
@login_required("customer")
def book(pid):
    me = current_user()
    p = mongo.providers.find_one({"_id": oid(pid)})
    if not p or "user_id" not in p:
        abort(404)
    f = request.form
    back = redirect(url_for("customer.provider_view", pid=pid))
    if p.get("available") is False:
        flash("This provider is not taking bookings right now.", "error")
        return back
    address = f.get("address", "").strip()
    if len(address) < 5:
        flash("Please enter the full service address.", "error")
        return back
    try:
        date = datetime.strptime(f["date"], "%Y-%m-%d")
        hours = int(f.get("hours") or 1)
    except (KeyError, ValueError):
        flash("Please enter a valid date and number of hours.", "error")
        return back
    if date.date() < datetime.now().date():
        flash("Please choose today or a future date.", "error")
        return back
    if not 1 <= hours <= 12:
        flash("Hours must be between 1 and 12.", "error")
        return back
    slot = f.get("time_slot", "")
    if slot not in TIME_SLOTS:
        flash("Please choose a time slot.", "error")
        return back

    now = datetime.utcnow()
    res = mongo.bookings.insert_one({
        "customer_id": me["_id"], "customer_name": me["name"], "customer_phone": me["phone"],
        "provider_id": p["_id"], "provider_user_id": p["user_id"],
        "provider_name": p["name"], "category": p["category"],
        "address": address, "date": date, "time_slot": slot, "hours": hours,
        "amount": hours * p.get("price_per_hour", 0), "notes": f.get("notes", "").strip(),
        "status": "pending",
        "timeline": [{"status": "pending", "note": "Booking requested", "at": now}],
        "created_at": now})
    notify(p["user_id"],
           f"New booking request from {me['name']} for {date:%d %b %Y}, {slot} ({hours} hr).",
           res.inserted_id)
    flash("Booking request sent. The provider has been notified.", "success")
    return redirect(url_for("customer.booking", bid=res.inserted_id))


@bp.route("/bookings")
@login_required("customer")
def bookings():
    me = current_user()
    status = request.args.get("status", "")
    items = list(mongo.bookings.find({"customer_id": me["_id"]}).sort("created_at", -1))
    counts = {}
    for b in items:
        counts[b["status"]] = counts.get(b["status"], 0) + 1
    if status:
        items = [b for b in items if b["status"] == status]
    return render_template("customer/bookings.html", items=items, status=status, counts=counts)


def _own_booking(bid):
    me = current_user()
    b = mongo.bookings.find_one({"_id": oid(bid)})
    if not b:
        abort(404)
    if b["customer_id"] != me["_id"]:
        abort(403)
    return b


@bp.route("/bookings/<bid>")
@login_required("customer")
def booking(bid):
    b = _own_booking(bid)
    p = mongo.providers.find_one({"_id": b["provider_id"]})
    review = mongo.reviews.find_one({"booking_id": b["_id"]})
    return render_template("customer/booking.html", b=b, p=p, review=review)


@bp.route("/bookings/<bid>/cancel", methods=["POST"])
@login_required("customer")
def cancel(bid):
    b = _own_booking(bid)
    if b["status"] not in ("pending", "accepted"):
        flash("This booking can no longer be cancelled.", "error")
    else:
        mongo.bookings.update_one({"_id": b["_id"]}, {
            "$set": {"status": "cancelled"},
            "$push": {"timeline": {"status": "cancelled", "note": "Cancelled by customer",
                                   "at": datetime.utcnow()}}})
        notify(b["provider_user_id"],
               f"{b['customer_name']} cancelled the booking for {b['date']:%d %b %Y}.", b["_id"])
        flash("Booking cancelled.", "success")
    return redirect(url_for("customer.booking", bid=bid))


@bp.route("/bookings/<bid>/review", methods=["POST"])
@login_required("customer")
def review(bid):
    me = current_user()
    b = _own_booking(bid)
    back = redirect(url_for("customer.booking", bid=bid))
    if b["status"] != "completed":
        flash("You can review a provider after the job is completed.", "error")
        return back
    if mongo.reviews.find_one({"booking_id": b["_id"]}):
        flash("You have already reviewed this job.", "error")
        return back
    try:
        rating = int(request.form["rating"])
    except (KeyError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        flash("Please choose a rating from 1 to 5.", "error")
        return back
    mongo.reviews.insert_one({
        "provider_id": b["provider_id"], "booking_id": b["_id"], "customer_id": me["_id"],
        "customer_name": me["name"], "rating": rating,
        "comment": request.form.get("comment", "").strip(), "created_at": datetime.utcnow()})
    recalc_rating(b["provider_id"])
    notify(b["provider_user_id"], f"{me['name']} rated you {rating}/5.", b["_id"])
    flash("Thanks for your review!", "success")
    return back


@bp.route("/notifications")
@login_required("customer")
def notifications():
    me = current_user()
    notes = list(mongo.notifications.find({"recipient_id": me["_id"]})
                 .sort("created_at", -1).limit(50))
    mongo.notifications.update_many({"recipient_id": me["_id"], "read": False},
                                    {"$set": {"read": True}})
    return render_template("notifications.html", notes=notes)


@bp.route("/profile", methods=["GET", "POST"])
@login_required("customer")
def profile():
    me = current_user()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name cannot be empty.", "error")
        else:
            mongo.users.update_one({"_id": me["_id"]}, {"$set": {
                "name": name, "address": request.form.get("address", "").strip()}})
            flash("Profile updated.", "success")
        return redirect(url_for("customer.profile"))
    return render_template("customer/profile.html")
