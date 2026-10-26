from flask import (
    Flask, request, redirect, url_for,
    jsonify, render_template_string, session, flash
)
from flask_login import (
    LoginManager, UserMixin, login_user,
    logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from pathlib import Path
import os

app = Flask(__name__)

# Secret key for secure login sessions
app.secret_key = os.environ.get(
    "COMMUNITYLENS_SECRET_KEY",
    os.urandom(32).hex()
)

# Login manager configuration
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "community.db"


# Import the existing feedback grouping function
try:
    from ai_grouping import group_feedback
except ImportError:
    group_feedback = None


# ---------------- DATABASE ----------------

def init_db():
    conn = sqlite3.connect(DATABASE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    """)

    feedback_columns = {
        row[1] for row in conn.execute(
            "PRAGMA table_info(feedback)"
        ).fetchall()
    }

    for column, column_type in {
        "location": "TEXT",
        "urgency": "TEXT NOT NULL DEFAULT 'Medium'",
        "photo_filename": "TEXT",
        "latitude": "REAL",
        "longitude": "REAL"
    }.items():
        if column not in feedback_columns:
            conn.execute(
                f"ALTER TABLE feedback ADD COLUMN {column} {column_type}"
            )

    conn.commit()
    conn.close()
def load_user(user_id):
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        "SELECT id, username, password_hash, role FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    conn.close()

    if row is None:
        return None

    user = UserMixin()
    user.id = row["id"]
    user.username = row["username"]
    user.password_hash = row["password_hash"]
    user.role = row["role"]

    return user


@login_manager.user_loader
def user_loader(user_id):
    return load_user(user_id)

def get_feedback():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id, description, category, status
        FROM feedback
        ORDER BY id DESC
    """).fetchall()

    conn.close()
    return [dict(row) for row in rows]

# ---------------- USER REGISTRATION AND LOGIN ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if len(username) < 3 or len(password) < 8:
            return "Username must have at least 3 characters and password at least 8.", 400

        password_hash = generate_password_hash(password)

        try:
            conn = sqlite3.connect(DATABASE)
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'user')",
                (username, password_hash)
            )
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            return "That username is already taken.", 400

        return redirect(url_for("login"))

    return render_template_string("""
        <h1>CommunityLens Registration</h1>
        <form method="POST">
            <label>Username</label>
            <input name="username" minlength="3" required>
            <br><br>
            <label>Password (at least 8 characters)</label>
            <input name="password" type="password" minlength="8" required>
            <br><br>
            <button type="submit">Register</button>
        </form>
        <p>Already registered? <a href="/login">Log in</a></p>
    """)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        user = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            account = load_user(user["id"])
            login_user(account)
            if account.role == "admin":
                return redirect(url_for("dashboard"))
            else:
                return redirect(url_for("give_feedback"))

        return "Invalid username or password.", 401

    return render_template_string("""
        <style>
    * {
        box-sizing: border-box;
    }

    body {
        margin: 0;
        min-height: 100vh;
        font-family: "Segoe UI", Arial, sans-serif;
        background:
            radial-gradient(circle at top left, #67e8f9 0%, transparent 35%),
            radial-gradient(circle at bottom right, #c4b5fd 0%, transparent 40%),
            linear-gradient(135deg, #0f172a, #312e81, #4338ca);
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 25px;
    }

    /* Login card */
    body > h1,
    body > form,
    body > p,
    body > div {
        /* Keep the page content above the background */
    }

    h1 {
        color: #312e81;
        font-size: 30px;
        text-align: center;
        margin: 0 0 25px;
    }

    form {
        background: rgba(255, 255, 255, 0.97);
        width: 100%;
        max-width: 430px;
        padding: 38px;
        border-radius: 22px;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.5);
    }

    label {
        display: block;
        color: #334155;
        font-weight: 600;
        margin: 15px 0 8px;
    }

    input[type="text"],
    input[type="password"] {
        width: 100%;
        padding: 13px 15px;
        border: 1px solid #cbd5e1;
        border-radius: 10px;
        background: #f8fafc;
        font-size: 15px;
        outline: none;
        transition: 0.25s;
    }

    input:focus {
        border-color: #6366f1;
        box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.15);
        background: white;
    }

    button,
    input[type="submit"] {
        width: 100%;
        margin-top: 24px;
        padding: 14px;
        border: none;
        border-radius: 10px;
        background: linear-gradient(135deg, #4f46e5, #7c3aed);
        color: white;
        font-size: 16px;
        font-weight: 700;
        cursor: pointer;
        transition: transform 0.2s, box-shadow 0.2s;
    }

    button:hover,
    input[type="submit"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(79, 70, 229, 0.35);
    }

    a {
        color: #4f46e5;
        font-weight: 600;
        text-decoration: none;
    }

    a:hover {
        color: #7c3aed;
        text-decoration: underline;
    }

    p {
        text-align: center;
        margin-top: 20px;
    }

    @media (max-width: 480px) {
        form {
            padding: 25px 20px;
        }

        h1 {
            font-size: 25px;
        }
    }
</style>
        <h1>CommunityLens Login</h1>
        <form method="POST">
            <label>Username</label>
            <input name="username" required>
            <br><br>
            <label>Password</label>
            <input name="password" type="password" required>
            <br><br>
            <button type="submit">Log In</button>
        </form>
        <p>New here? <a href="/register">Create an account</a></p>
    """)

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        user = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        conn.close()

        if (
            user
            and user["role"] == "admin"
            and check_password_hash(user["password_hash"], password)
        ):
            account = load_user(user["id"])
            login_user(account)
            return redirect(url_for("dashboard"))

        return "Invalid administrator username or password.", 401

    return render_template_string("""
        <style>
    * {
        box-sizing: border-box;
    }

    body {
        margin: 0;
        min-height: 100vh;
        font-family: "Segoe UI", Arial, sans-serif;
        background:
            radial-gradient(circle at top left, #67e8f9 0%, transparent 35%),
            radial-gradient(circle at bottom right, #c4b5fd 0%, transparent 40%),
            linear-gradient(135deg, #0f172a, #312e81, #4338ca);
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 25px;
    }

    /* Login card */
    body > h1,
    body > form,
    body > p,
    body > div {
        /* Keep the page content above the background */
    }

    h1 {
        color: #312e81;
        font-size: 30px;
        text-align: center;
        margin: 0 0 25px;
    }

    form {
        background: rgba(255, 255, 255, 0.97);
        width: 100%;
        max-width: 430px;
        padding: 38px;
        border-radius: 22px;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.5);
    }

    label {
        display: block;
        color: #334155;
        font-weight: 600;
        margin: 15px 0 8px;
    }

    input[type="text"],
    input[type="password"] {
        width: 100%;
        padding: 13px 15px;
        border: 1px solid #cbd5e1;
        border-radius: 10px;
        background: #f8fafc;
        font-size: 15px;
        outline: none;
        transition: 0.25s;
    }

    input:focus {
        border-color: #6366f1;
        box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.15);
        background: white;
    }

    button,
    input[type="submit"] {
        width: 100%;
        margin-top: 24px;
        padding: 14px;
        border: none;
        border-radius: 10px;
        background: linear-gradient(135deg, #4f46e5, #7c3aed);
        color: white;
        font-size: 16px;
        font-weight: 700;
        cursor: pointer;
        transition: transform 0.2s, box-shadow 0.2s;
    }

    button:hover,
    input[type="submit"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(79, 70, 229, 0.35);
    }

    a {
        color: #4f46e5;
        font-weight: 600;
        text-decoration: none;
    }

    a:hover {
        color: #7c3aed;
        text-decoration: underline;
    }

    p {
        text-align: center;
        margin-top: 20px;
    }

    @media (max-width: 480px) {
        form {
            padding: 25px 20px;
        }

        h1 {
            font-size: 25px;
        }
    }
</style>
        <h1>Administrator Login</h1>
        <form method="POST">
            <label>Username</label>
            <input type="text" name="username" required>
            <br><br>
            <label>Password</label>
            <input type="password" name="password" required>
            <br><br>
            <button type="submit">Login as Administrator</button>
        </form>
        <p><a href="/">Back to Home</a></p>
    """)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))
# ---------------- HOME PAGE ----------------

HOME_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CommunityLens</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #e0f2fe, #ede9fe);
            margin: 0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: #1e293b;
        }

        h1 {
            font-size: 42px;
            margin-bottom: 10px;
            color: #4338ca;
        }

        .subtitle {
            margin: 0 20px 35px;
            text-align: center;
            color: #475569;
        }

        .cards {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 25px;
            padding: 20px;
        }

        .card {
            background: white;
            width: 280px;
            padding: 30px;
            border-radius: 18px;
            text-align: center;
            box-shadow: 0 8px 25px #00000018;
        }

        .user-card {
            border-top: 6px solid #2563eb;
        }

        .admin-card {
            border-top: 6px solid #9333ea;
        }

        .btn {
            display: block;
            padding: 12px;
            margin-top: 15px;
            border-radius: 8px;
            color: white;
            text-decoration: none;
            font-weight: bold;
        }

        .user-btn {
            background: #2563eb;
        }

        .admin-btn {
            background: #9333ea;
        }

        .btn:hover {
            opacity: 0.85;
        }
    </style>
</head>
<body>
    <h1>CommunityLens</h1>
    <p class="subtitle">
        Your voice matters. Together, we can improve our community.
    </p>

    <div class="cards">
        <section class="card user-card">
            <h2>👥 Community User</h2>
            <p>Share your feedback and help improve your community.</p>
            <a class="btn user-btn" href="/login">User Login</a>
            <a class="btn user-btn" href="/register">Create an Account</a>
        </section>

        <section class="card admin-card">
            <h2>🛡️ Administrator</h2>
            <p>Review community feedback and analyze important issues.</p>
            <a class="btn admin-btn" href="/admin-login">Admin Login</a>
        </section>
    </div>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HOME_PAGE)
@app.route("/give-feedback", methods=["GET"])
@login_required
def give_feedback():
    if current_user.role != "user":
        return "Access denied: Users only.", 403

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Give Feedback - CommunityLens</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #eff6ff;
                padding: 40px;
            }
            .container {
                max-width: 600px;
                margin: auto;
                background: white;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 4px 15px #00000015;
            }
            textarea, select {
                width: 100%;
                padding: 12px;
                margin: 10px 0 20px;
                box-sizing: border-box;
            }
            button {
                background: #2563eb;
                color: white;
                padding: 12px 20px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Give Feedback</h1>
            <p>Help us improve your community.</p>

            <form action="/submit" method="POST" enctype="multipart/form-data">
                <label>Describe the problem</label>
                <textarea name="description" rows="5"
                    maxlength="2000" required></textarea>

                <label>Choose a category</label>
                <select name="category" required>
                    <option value="">Select category</option>
                    <option value="Infrastructure">Infrastructure</option>
                    <option value="Internet and Technology">Internet and Technology</option>
                    <option value="Cleanliness">Cleanliness</option>
                    <option value="Safety">Safety</option>
                    <option value="Transportation">Transportation</option>
                    <option value="Other">Other</option>
                </select>

                <label>Location of the problem</label>
<p>Click on the map to mark where the issue is happening.</p>

<div id="problem-map" style="height: 350px; width: 100%; border-radius: 12px; margin: 12px 0;"></div>

<input
    type="hidden"
    name="latitude"
    id="latitude"
>

<input
    type="hidden"
    name="longitude"
    id="longitude"
>

<input
    type="text"
    name="location"
    id="location"
    placeholder="Selected location will appear here"
    maxlength="200"
    required
    readonly
>
<input
    type="text"
    name="location"
    placeholder="e.g. Library, Block A, Main Road"
    maxlength="200"
    required
>

<label>Urgency level</label>
<select name="urgency" required>
    <option value="Low">Low</option>
    <option value="Medium" selected>Medium</option>
    <option value="High">High</option>
</select>

<label>Upload photo evidence (optional)</label>
<input
    type="file"
    name="photo"
    accept="image/png,image/jpeg,image/webp"
>

                <button type="submit">Submit Feedback</button>
            </form>

            <p><a href="/">Back to Home</a></p>
            <p><a href="/logout">Logout</a></p>
        </div>
        <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
/>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>
    const map = L.map('problem-map').setView([16.5062, 80.6480], 12);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);

    let marker;

    map.on('click', function (event) {
        const lat = event.latlng.lat;
        const lng = event.latlng.lng;

        if (marker) {
            map.removeLayer(marker);
        }

        marker = L.marker([lat, lng]).addTo(map);

        document.getElementById('latitude').value = lat;
        document.getElementById('longitude').value = lng;
        document.getElementById('location').value =
            lat.toFixed(6) + ', ' + lng.toFixed(6);
    });
</script>
    </body>
    </html>
    """)


# ---------------- SUBMIT FEEDBACK ----------------

@app.route("/submit", methods=["POST"])
@app.route("/feedback", methods=["POST"])
@login_required
def submit_feedback():
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "").strip()
    location = request.form.get("location", "").strip()
    urgency = request.form.get("urgency", "Medium").strip()

    latitude = request.form.get("latitude", "").strip()
    longitude = request.form.get("longitude", "").strip()

    try:
        latitude = float(latitude)
        longitude = float(longitude)

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError
    except ValueError:
        return "Please select the problem location on the map.", 400

    if urgency not in {"Low", "Medium", "High"}:
        return "Please select a valid urgency level.", 400

    allowed_categories = {
        "Infrastructure",
        "Internet and Technology",
        "Cleanliness",
        "Safety",
        "Transportation",
        "Other"
    }

    if not description or len(description) > 2000:
        return "Please enter a valid problem description.", 400

    if category not in allowed_categories:
        return "Please choose a valid category.", 400

    conn = sqlite3.connect(DATABASE)

    conn.execute(
    """
    INSERT INTO feedback
    (description, category, status, location, urgency, latitude, longitude)
    VALUES (?, ?, 'New', ?, ?, ?, ?)
    """,
    (
        description,
        category,
        location,
        urgency,
        latitude,
        longitude
    )
)
    conn.commit()
    conn.close()

    return """
    <h2>Feedback saved successfully!</h2>
    <p>Thank you for helping improve your community.</p>
    <a href="/">Back to Home</a>
    <a href="/dashboard">View Dashboard</a>
    """


# ---------------- DASHBOARD ----------------
@app.route("/admin-map")
@login_required
def admin_map():
    if current_user.role != "admin":
        return "Access denied: Admins only.", 403

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    reports = conn.execute("""
        SELECT id, description, category, location, urgency,
               latitude, longitude, status
        FROM feedback
        WHERE latitude IS NOT NULL
          AND longitude IS NOT NULL
    """).fetchall()

    conn.close()

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>CommunityLens - Problem Map</title>
        <link rel="stylesheet"
              href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
        <style>
            body { font-family: Arial, sans-serif; margin: 24px; }
            #admin-map { height: 550px; width: 100%; border-radius: 12px; }
        </style>
    </head>
    <body>
        <h1>Community Problem Map</h1>
        <p>Click a marker to view the reported problem and its urgency.</p>
        <div id="admin-map"></div>
        <p><a href="/dashboard">Back to Dashboard</a></p>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            const reports = {{ reports | tojson }};
            const map = L.map('admin-map').setView([16.5062, 80.6480], 12);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(map);

            const markers = [];

            reports.forEach(report => {
                const marker = L.marker([
                    report.latitude, report.longitude
                ]).addTo(map);

                marker.bindPopup(
                    '<b>Problem:</b> ' + report.description +
                    '<br><b>Category:</b> ' + report.category +
                    '<br><b>Urgency:</b> ' + report.urgency +
                    '<br><b>Status:</b> ' + report.status
                );

                markers.push(marker);
            });

            if (markers.length > 0) {
                const group = L.featureGroup(markers);
                map.fitBounds(group.getBounds().pad(0.15));
            } else {
                L.popup()
                    .setLatLng([16.5062, 80.6480])
                    .setContent('No feedback reports have saved map coordinates yet.')
                    .openOn(map);
            }
        </script>
    </body>
    </html>
    """, reports=[dict(row) for row in reports])

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role != "admin":
        return "Access denied: Admins only.", 403

    feedback_list = get_feedback()
    category_counts = {}

    for item in feedback_list:
        category = item["category"]
        category_counts[category] = category_counts.get(category, 0) + 1
        from collections import Counter

    groups = group_feedback(feedback_list)

    priority_counts = {"High": 0, "Medium": 0, "Low": 0}

    for group in groups:
        count = group["count"]

        if count >= 5:
            priority_counts["High"] += 1
        elif count >= 3:
            priority_counts["Medium"] += 1
        else:
            priority_counts["Low"] += 1
    return render_template_string("""

    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>CommunityLens Dashboard</title>

        <style>
            body {
                font-family: Arial, sans-serif;
                background: #f4f7fb;
                padding: 25px;
                color: #1e293b;
            }

            .container {
                max-width: 1100px;
                margin: auto;
                background: white;
                padding: 25px;
                border-radius: 12px;
                overflow-x: auto;
            }

            h1 {
                color: #087f6e;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }

            th, td {
                padding: 12px;
                border-bottom: 1px solid #ddd;
                text-align: left;
            }

            th {
                background: #087f6e;
                color: white;
            }

            a {
                color: #087f6e;
                margin-right: 15px;
            }
        </style>
    </head>

    <body>
        <div class="container">
            <h1>CommunityLens Dashboard</h1>
            <p>Review feedback submitted by your community.</p>

            <p>Total submissions: {{ feedback_list|length }}</p>
            <h2>Category-wise Summary</h2>
            <canvas id="categoryChart" width="400" height="180"></canvas>
            <h2>Priority Summary</h2>
            <p>High Priority: {{ priority_counts["High"] }}</p>
            <p>Medium Priority: {{ priority_counts["Medium"] }}</p>
            <p>Low Priority: {{ priority_counts["Low"] }}</p>
            <canvas id="priorityChart" width="400" height="180"></canvas>

            {% for category, count in category_counts.items() %}
                <p>
                    <strong>{{ category }}:</strong> {{ count }} issue(s)
                </p>
            {% else %}
                <p>No feedback available yet.</p>
            {% endfor %}

            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Feedback</th>
                        <th>Category</th>
                        <th>Status</th>
                    </tr>
                </thead>

                <tbody>
                    {% for item in feedback_list %}
                    <tr>
                        <td>{{ item.id }}</td>
                        <td>{{ item.description }}</td>
                        <td>{{ item.category }}</td>
                        <td>
    <form action="/update-status/{{ item.id }}" method="POST">
        <select name="status">
            <option value="New"
                {% if item.status == "New" %}selected{% endif %}>
                New
            </option>
            <option value="In Progress"
                {% if item.status == "In Progress" %}selected{% endif %}>
                In Progress
            </option>
            <option value="Resolved"
                {% if item.status == "Resolved" %}selected{% endif %}>
                Resolved
            </option>
        </select>
        <button type="submit">Update</button>
    </form>
</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="4">No feedback submitted yet.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>

            <p>
                <a href="/">Back to Home</a>
                <a href="/ai-page">View AI Analysis</a>
                <a href="/admin-map">View Problem Map</a>
            </p>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<script>
const categoryLabels = {{ category_counts.keys() | list | tojson }};
const categoryValues = {{ category_counts.values() | list | tojson }};

new Chart(document.getElementById("categoryChart"), {
    type: "bar",
    data: {
        labels: categoryLabels,
        datasets: [{
            label: "Number of Reports",
            data: categoryValues
        }]
    },
    options: {
        responsive: true,
        scales: {
            y: {
                beginAtZero: true,
                ticks: {
                    stepSize: 1
                }
            }
        }
    }
});
</script>
<script>
const priorityLabels = ["High", "Medium", "Low"];
const priorityValues = [
    {{ priority_counts["High"] }},
    {{ priority_counts["Medium"] }},
    {{ priority_counts["Low"] }}
];

new Chart(document.getElementById("priorityChart"), {
    type: "doughnut",
    data: {
        labels: priorityLabels,
        datasets: [{
            label: "Number of Issues",
            data: priorityValues
        }]
    },
    options: {
        responsive: true
    }
});
</script>
    </body>
    </html>
    """, feedback_list=feedback_list, category_counts=category_counts, priority_counts=priority_counts)

# ---------------- AI ANALYSIS API ----------------

@app.route("/ai-analysis")
@login_required
def ai_analysis():
    if current_user.role != "admin":
        return jsonify({"error": "Admins only"}), 403
    feedback_list = get_feedback()
    category_counts = {}

    for item in feedback_list: 
        category = item["category"]
        category_counts[category] = category_counts.get(category, 0) + 1

    if not feedback_list:
        return jsonify([])

    if group_feedback is None:
        return jsonify({
            "error": (
                "Could not import group_feedback from ai_grouping.py. "
                "Check the function name in that file."
            )
        }), 500

    try:
        groups = group_feedback(feedback_list)
        return jsonify(groups)

    except Exception:
        app.logger.exception("Feedback grouping failed")
        return jsonify({
            "error": "Feedback grouping failed. Check ai_grouping.py."
        }), 500


# ---------------- AI ANALYSIS PAGE ----------------

# ---------------- AI ANALYSIS PAGE ----------------
@app.route("/ai-page")
@login_required
def ai_page():
    if current_user.role != "admin":
        return "Access denied: Admins only.", 403
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>CommunityLens AI Analysis</title>

        <style>
            body {
                font-family: Arial, sans-serif;
                background: #f4f7fb;
                padding: 25px;
                color: #1e293b;
            }

            main {
                max-width: 850px;
                margin: auto;
                background: white;
                padding: 25px;
                border-radius: 12px;
                box-shadow: 0 4px 15px #00000012;
            }

            h1 {
                color: #087f6e;
            }

            .group {
                padding: 18px;
                margin: 18px 0;
                background: #f0fdfa;
                border-left: 5px solid #087f6e;
                border-radius: 6px;
            }

            .priority {
                display: inline-block;
                padding: 6px 12px;
                border-radius: 20px;
                font-weight: bold;
                font-size: 14px;
                margin: 5px 0 10px;
            }

            .high {
                background: #fee2e2;
                color: #991b1b;
            }

            .medium {
                background: #fef3c7;
                color: #92400e;
            }

            .low {
                background: #dcfce7;
                color: #166534;
            }

            .feedback-item {
                background: white;
                padding: 12px;
                margin-top: 10px;
                border-radius: 6px;
                overflow-wrap: anywhere;
            }

            a {
                color: #087f6e;
            }

            .count {
                color: #475569;
            }
        </style>
    </head>

    <body>
        <main>
            <h1>AI-Identified Community Issues</h1>

            <p>
                Related feedback is grouped to help identify
                recurring community problems and their priority.
            </p>

            <div id="aiResults">Loading analysis...</div>

            <p><a href="/">Back to Home</a></p>
            <p><a href="/dashboard">Back to Dashboard</a></p>
        </main>

        <script>
        async function loadAIResults() {
            const container = document.getElementById("aiResults");

            try {
                const response = await fetch("/ai-analysis");
                const groups = await response.json();

                if (!response.ok || !Array.isArray(groups)) {
                    throw new Error(
                        groups.error || "Analysis failed"
                    );
                }

                container.replaceChildren();

                if (groups.length === 0) {
                    container.textContent =
                        "No feedback available yet.";
                    return;
                }

                groups.forEach((group) => {
                    const card = document.createElement("section");
                    card.className = "group";

                    const heading = document.createElement("h2");
                    heading.textContent =
                        group.issue || "Community issue";
                    card.appendChild(heading);

                    const count = Number(group.count) || 0;

                    const priority = document.createElement("span");
                    priority.className = "priority";

                    // Initial rule based on the number of
                    // feedback submissions in each group.
                    let level;

                    if (count >= 5) {
                        level = "High";
                        priority.classList.add("high");
                    } else if (count >= 3) {
                        level = "Medium";
                        priority.classList.add("medium");
                    } else {
                        level = "Low";
                        priority.classList.add("low");
                    }

                    priority.textContent = "Priority: " + level;
                    card.appendChild(priority);

                    const countText = document.createElement("p");
                    countText.className = "count";
                    countText.textContent =
                        "Related feedback submissions: " + count;
                    card.appendChild(countText);

                    const feedbackHeading =
                        document.createElement("h3");
                    feedbackHeading.textContent =
                        "Reported feedback";
                    card.appendChild(feedbackHeading);

                    const feedbackList = Array.isArray(group.feedback)
                        ? group.feedback
                        : [];

                    feedbackList.forEach((item) => {
                        const entry = document.createElement("div");
                        entry.className = "feedback-item";

                        const description =
                            document.createElement("p");
                        description.textContent =
                            item.description || "No description";
                        entry.appendChild(description);

                        const category =
                            document.createElement("small");
                        category.textContent =
                            "Category: " + (item.category || "Other");
                        entry.appendChild(category);

                        card.appendChild(entry);
                    });

                    container.appendChild(card);
                });

            } catch (error) {
                container.textContent =
                    "Unable to load AI analysis: " + error.message;
            }
        }

        loadAIResults();
        </script>
    </body>
    </html>
    """)
def create_admin():
    username = os.environ.get("COMMUNITYLENS_ADMIN_USERNAME")
    password = os.environ.get("COMMUNITYLENS_ADMIN_PASSWORD")

    if not username or not password:
        print("Admin not created: set admin username and password environment variables.")
        return

    if len(password) < 12:
        print("Admin password must be at least 12 characters.")
        return

    conn = sqlite3.connect(DATABASE)

    existing = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        (username,)
    ).fetchone()

    if existing:
        print("Admin username already exists. No changes made.")
    else:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            (username, generate_password_hash(password))
        )
        print("Admin account created successfully.")

    conn.commit()
    conn.close()
@app.route("/update-status/<int:feedback_id>", methods=["POST"])
@login_required
def update_status(feedback_id):
    if current_user.role != "admin":
        return "Access denied: Admins only.", 403

    new_status = request.form.get("status", "")

    if new_status not in ["New", "In Progress", "Resolved"]:
        return "Invalid status.", 400

    conn = sqlite3.connect(DATABASE)
    conn.execute(
        "UPDATE feedback SET status = ? WHERE id = ?",
        (new_status, feedback_id)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))
if __name__ == "__main__":
    init_db()
    create_admin()
    app.run(debug=True)