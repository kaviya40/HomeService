from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

from db import mongo
from utils import (PHONE_RE, CATEGORIES, current_user, home_for, start_session,
                   save_media, parse_location)

bp = Blueprint("auth", __name__)


def _safe_next():
    nxt = request.args.get("next", "")
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else ""


@bp.route("/")
def landing():
    me = current_user()
    if me:
        return redirect(home_for(me))
    return render_template("landing.html")


def _login(role):
    me = current_user()
    if me and me["role"] == role:
        return redirect(home_for(me))
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        user = mongo.users.find_one({"phone": phone, "role": role})
        if user and check_password_hash(user["password"], request.form.get("password", "")):
            start_session(user)
            return redirect(_safe_next() or home_for(user))
        flash("Wrong mobile number or password.", "error")
    return render_template("auth/login.html", role=role)


@bp.route("/customer/login", methods=["GET", "POST"])
def customer_login():
    return _login("customer")


@bp.route("/provider/login", methods=["GET", "POST"])
def provider_login():
    return _login("provider")


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.landing"))


def _check_account(f, role):
    phone = f.get("phone", "").strip()
    if not PHONE_RE.match(phone):
        return "Please enter a valid 10-digit mobile number."
    if len(f.get("password", "")) < 6:
        return "Password must be at least 6 characters."
    if mongo.users.find_one({"phone": phone, "role": role}):
        return "An account with this mobile number already exists. Please log in."
    return None


@bp.route("/customer/register", methods=["GET", "POST"])
def customer_register():
    if request.method == "POST":
        f = request.form
        err = _check_account(f, "customer")
        if err:
            flash(err, "error")
        else:
            res = mongo.users.insert_one({
                "role": "customer", "name": f["name"].strip(), "phone": f["phone"].strip(),
                "address": f.get("address", "").strip(),
                "password": generate_password_hash(f["password"]),
                "created_at": datetime.utcnow()})
            start_session(mongo.users.find_one({"_id": res.inserted_id}))
            flash("Welcome! Your customer account is ready.", "success")
            return redirect(url_for("customer.home"))
    return render_template("auth/customer_register.html")


@bp.route("/provider/register", methods=["GET", "POST"])
def provider_register():
    if request.method == "POST":
        f = request.form
        back = redirect(url_for("auth.provider_register"))
        err = _check_account(f, "provider")
        if err:
            flash(err, "error")
            return back
        location, err = parse_location(f)
        if err:
            flash(err, "error")
            return back
        phone = f["phone"].strip()
        user_id = mongo.users.insert_one({
            "role": "provider", "name": f["name"].strip(), "phone": phone,
            "password": generate_password_hash(f["password"]),
            "created_at": datetime.utcnow()}).inserted_id
        mongo.providers.insert_one({
            "user_id": user_id, "name": f["name"].strip(), "category": f["category"],
            "phone": phone, "price_per_hour": int(f.get("price") or 0),
            "experience_years": int(f.get("experience") or 0),
            "description": f.get("description", "").strip(),
            "available": True, "location": location,
            "media": save_media(request.files.getlist("images"), "image")
                     + save_media(request.files.getlist("video")[:1], "video"),
            "rating_avg": 0, "rating_count": 0, "created_at": datetime.utcnow()})
        start_session(mongo.users.find_one({"_id": user_id}))
        flash("Your provider account is ready. Customers can now book you.", "success")
        return redirect(url_for("provider.dashboard"))
    return render_template("auth/provider_register.html", categories=CATEGORIES, loc=None)
