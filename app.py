import os
import secrets

from flask import Flask, render_template, request, session, abort
from markupsafe import Markup

from config import Config
from db import init_db, mongo
from utils import current_user, ist


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    init_db(app.config["MONGO_URI"], app.config["MONGO_DB"])

    from routes.auth import bp as auth_bp
    from routes.customer import bp as customer_bp
    from routes.provider import bp as provider_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(provider_bp)

    app.jinja_env.filters["ist"] = ist

    # ---- CSRF protection for every POST form
    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return session["csrf"]

    @app.before_request
    def check_csrf():
        if request.method == "POST":
            sent = request.form.get("csrf", "")
            if not sent or sent != session.get("csrf"):
                abort(400, "Session expired. Go back, refresh the page and try again.")

    @app.context_processor
    def inject():
        me = current_user()
        unread = pending = 0
        if me:
            unread = mongo.notifications.count_documents(
                {"recipient_id": me["_id"], "read": False})
            if me["role"] == "provider":
                from utils import my_provider
                p = my_provider()
                if p:
                    pending = mongo.bookings.count_documents(
                        {"provider_id": p["_id"], "status": "pending"})
        return {"me": me, "unread": unread, "pending_count": pending,
                "csrf_input": lambda: Markup(
                    f'<input type="hidden" name="csrf" value="{csrf_token()}">')}

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def error(e):
        return render_template("error.html", e=e), e.code

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
