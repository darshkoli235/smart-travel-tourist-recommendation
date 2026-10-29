"""Flask application for the Smart Travel & Tourist Recommendation System."""

import hmac
import os
import secrets
import sqlite3
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from knowledge_base import DESTINATIONS
from recommender import backward_chain_recommendation, forward_chain


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"

app = Flask(__name__)
app.config["SECRET_KEY"] = (
    os.environ.get("SECRET_KEY")
    or os.environ.get("SESSION_SECRET")
    or secrets.token_hex(32)
)
app.config["DATABASE"] = INSTANCE_DIR / "travel_recommendations.db"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def get_db():
    """Open one SQLite connection for the current web request."""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_db():
    """Create the small user and saved-preference tables when needed."""
    database_path = Path(app.config["DATABASE"])
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS preferences (
            user_id INTEGER PRIMARY KEY,
            budget INTEGER NOT NULL,
            trip_days INTEGER NOT NULL,
            destination_type TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """
    )
    connection.commit()
    connection.close()


@app.teardown_appcontext
def close_db(_error=None):
    """Close the request's database connection."""
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


@app.before_request
def load_user_and_csrf_token():
    """Load the signed-in user and prepare a token for forms that change data."""
    session.setdefault("_csrf_token", secrets.token_urlsafe(32))
    user_id = session.get("user_id")
    g.user = None

    if user_id is not None:
        g.user = get_db().execute(
            "SELECT id, username, email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


@app.context_processor
def add_template_values():
    return {
        "current_user": g.get("user"),
        "csrf_token": session.get("_csrf_token", ""),
    }


def check_csrf_token():
    """Reject form submissions that do not belong to this browser session."""
    submitted_token = request.form.get("csrf_token", "")
    session_token = session.get("_csrf_token", "")
    if not session_token or not hmac.compare_digest(session_token, submitted_token):
        abort(400, description="This form expired. Refresh the page and try again.")


def login_required(view_function):
    """Keep private pages available only to signed-in users."""

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if g.get("user") is None:
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)

    return wrapped_view


def get_saved_preferences(user_id):
    return get_db().execute(
        """
        SELECT budget, trip_days, destination_type
        FROM preferences
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()


@app.route("/")
def home():
    return render_template("home.html", featured_destinations=DESTINATIONS[:3])


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.get("user") is not None:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        check_csrf_token()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        errors = []

        if not 2 <= len(username) <= 32:
            errors.append("Choose a username between 2 and 32 characters.")
        if not email or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            errors.append("Enter a valid email address.")
        if not 8 <= len(password) <= 128:
            errors.append("Your password must be between 8 and 128 characters.")

        if not errors:
            try:
                connection = get_db()
                cursor = connection.execute(
                    """
                    INSERT INTO users (username, email, password_hash)
                    VALUES (?, ?, ?)
                    """,
                    (username, email, generate_password_hash(password)),
                )
                connection.commit()
                session.clear()
                session["user_id"] = cursor.lastrowid
                flash("Your account is ready. Let’s plan a trip.", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                errors.append("That username or email is already in use.")

        return render_template(
            "register.html",
            username=username,
            email=email,
            errors=errors,
        ), 400

    return render_template("register.html", username="", email="", errors=[])


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user") is not None:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        check_csrf_token()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, username, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Email or password not recognized. Please try again.", "error")
            return render_template("login.html", email=email), 401

        session.clear()
        session["user_id"] = user["id"]
        flash(f"Welcome back, {user['username']}.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html", email="")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    check_csrf_token()
    session.clear()
    flash("You have signed out.", "info")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    preferences = get_saved_preferences(g.user["id"])
    return render_template("dashboard.html", preferences=preferences)


@app.route("/plan-trip", methods=["GET", "POST"])
@login_required
def plan_trip():
    saved = get_saved_preferences(g.user["id"])

    if request.method == "POST":
        check_csrf_token()
        try:
            budget = int(request.form.get("budget", ""))
            trip_days = int(request.form.get("trip_days", ""))
        except ValueError:
            flash("Please enter a valid budget and trip duration.", "error")
            return redirect(url_for("plan_trip"))

        destination_type = request.form.get("destination_type", "")
        valid_types = {"nature", "beach", "culture", "adventure", "spiritual"}
        if not 2000 <= budget <= 60000:
            flash("Choose a budget between ₹2,000 and ₹60,000 per person.", "error")
            return redirect(url_for("plan_trip"))
        if not 1 <= trip_days <= 21:
            flash("Choose a trip duration between 1 and 21 days.", "error")
            return redirect(url_for("plan_trip"))
        if destination_type not in valid_types:
            flash("Please choose one of the listed destination types.", "error")
            return redirect(url_for("plan_trip"))

        connection = get_db()
        connection.execute(
            """
            INSERT INTO preferences (user_id, budget, trip_days, destination_type)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                budget = excluded.budget,
                trip_days = excluded.trip_days,
                destination_type = excluded.destination_type,
                updated_at = CURRENT_TIMESTAMP
            """,
            (g.user["id"], budget, trip_days, destination_type),
        )
        connection.commit()
        return redirect(url_for("recommendations"))

    return render_template("plan_trip.html", preferences=saved)


@app.route("/recommendations")
@login_required
def recommendations():
    saved = get_saved_preferences(g.user["id"])
    if saved is None:
        flash("Add your trip preferences first to get recommendations.", "info")
        return redirect(url_for("plan_trip"))

    preferences = {
        "budget": saved["budget"],
        "trip_days": saved["trip_days"],
        "destination_type": saved["destination_type"],
    }
    suggestions = forward_chain(preferences)

    for rank, destination in enumerate(suggestions, start=1):
        destination["rank"] = rank
        destination["proof"] = backward_chain_recommendation(
            destination,
            preferences,
            rank,
        )

    return render_template(
        "recommendations.html",
        preferences=preferences,
        recommendations=suggestions,
    )


@app.route("/about-ai")
def about_ai():
    return render_template("about_ai.html")


if __name__ == "__main__":
    with app.app_context():
        init_db()

    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
