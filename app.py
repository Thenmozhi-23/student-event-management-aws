from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql
import boto3
from werkzeug.utils import secure_filename
app = Flask(__name__)

# =========================================================
# SESSION SECRET KEY
# =========================================================

app.secret_key = "student_event_secret_key_123"


# =========================================================
# AMAZON S3 CONFIGURATION
# =========================================================

S3_BUCKET = "student-event-management-2026"
S3_REGION = "ap-south-1"

s3 = boto3.client(
    "s3",
    region_name=S3_REGION
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():
    conn = pymysql.connect(
        host="student-event-db.c9ycimkcoh8l.ap-south-2.rds.amazonaws.com",
        user="admin",
        password="YOUR_RDS_PASSWORD",
        database="student_event_db",
        port=3306,
        cursorclass=pymysql.cursors.DictCursor
    )
    return conn


# =========================================================
# CREATE DATABASE TABLES
# =========================================================

def init_db():
    conn = get_db()
    conn.close()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return render_template("home.html")


# =========================================================
# STUDENT REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        department = request.form.get("department")

        # Check required fields
        if not name or not email or not password:

            flash("Please fill all required fields.")

            return redirect(url_for("register"))

        conn = get_db()

        # Check duplicate email
        existing_user = conn.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (email,)).fetchone()

        if existing_user:

            conn.close()

            flash("Email already registered!")

            return redirect(url_for("register"))

        # Save student
        conn.execute("""
            INSERT INTO users
            (name, email, password, department)
            VALUES (?, ?, ?, ?)
        """, (
            name,
            email,
            password,
            department
        ))

        conn.commit()
        conn.close()

        flash("Registration successful! Please login.")

        return redirect(url_for("login"))

    return render_template("register.html")


# =========================================================
# STUDENT LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE email = ?
            AND password = ?
        """, (
            email,
            password
        )).fetchone()

        conn.close()

        if user:

            # Save login information in session
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]

            return redirect(url_for("dashboard"))

        flash("Invalid email or password!")

        return redirect(url_for("login"))

    return render_template("login.html")


# =========================================================
# STUDENT DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    # Login check
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        name=session["user_name"]
    )


# =========================================================
# VIEW EVENTS
# =========================================================
@app.route("/s3-image/<path:key>")
def s3_image(key):

    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": S3_BUCKET,
                "Key": key
            },
            ExpiresIn=3600
        )

        return redirect(url)

    except Exception as e:
        print("S3 Image Error:", e)
        return "Image not available", 404
@app.route("/events")
def events():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    events_list = conn.execute("""
        SELECT *
        FROM events
        ORDER BY id
    """).fetchall()

    conn.close()

    events_data = []

    for event in events_list:

        event = dict(event)

        # Generate S3 URL for image
        if event.get("image_url"):

            try:
                event["image_url"] = s3.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": S3_BUCKET,
                        "Key": event["image_url"]
                    },
                    ExpiresIn=3600
                )

            except Exception as e:

                print("S3 Image Error:", e)

                event["image_url"] = None

        events_data.append(event)

    return render_template(
        "events.html",
        events=events_data
    )


# =========================================================
# REGISTER FOR EVENT
# =========================================================

@app.route("/register-event/<int:event_id>")
def register_event(event_id):

    # Login check
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db()

    # Check event exists
    selected_event = conn.execute("""
        SELECT *
        FROM events
        WHERE id = ?
    """, (event_id,)).fetchone()

    if not selected_event:

        conn.close()

        flash("Event not found!")

        return redirect(url_for("events"))

    # Check already registered
    existing_registration = conn.execute("""
        SELECT *
        FROM registrations
        WHERE user_id = ?
        AND event_id = ?
    """, (
        user_id,
        event_id
    )).fetchone()

    if existing_registration:

        flash("You already registered for this event!")

    else:

        conn.execute("""
            INSERT INTO registrations
            (user_id, event_id)
            VALUES (?, ?)
        """, (
            user_id,
            event_id
        ))

        conn.commit()

        flash("Event registered successfully!")

    conn.close()

    return redirect(url_for("my_events"))


# =========================================================
# MY REGISTERED EVENTS
# =========================================================

@app.route("/my-events")
def my_events():

    # Login check
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db()

    registered_events = conn.execute("""
        SELECT
            events.id,
            events.name,
            events.date,
            events.time,
            events.venue
        FROM events
        JOIN registrations
        ON events.id = registrations.event_id
        WHERE registrations.user_id = ?
        ORDER BY events.id
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        "my_events.html",
        events=registered_events
    )


# =========================================================
# STUDENT LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    admin_email = "admin@gmail.com"
    admin_password = "admin123"

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        if (
            email == admin_email
            and password == admin_password
        ):

            session["admin"] = True

            return redirect(url_for("admin"))

        flash("Invalid Admin Email or Password!")

        return redirect(url_for("admin_login"))

    return render_template("admin_login.html")


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin():

    # Admin login check
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()

    # Get students
    students = conn.execute("""
        SELECT *
        FROM users
        ORDER BY id DESC
    """).fetchall()

    # Get events
    events_list = conn.execute("""
        SELECT *
        FROM events
        ORDER BY id DESC
    """).fetchall()

    # Get registrations
    registrations = conn.execute("""
        SELECT
            registrations.id,
            users.name AS student_name,
            users.email AS student_email,
            events.name AS event_name,
            events.date,
            events.time,
            events.venue
        FROM registrations
        JOIN users
        ON registrations.user_id = users.id
        JOIN events
        ON registrations.event_id = events.id
        ORDER BY registrations.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        students=students,
        events=events_list,
        registrations=registrations
    )


# =========================================================
# ADD EVENT
# =========================================================

# =========================================================
# ADD EVENT
# =========================================================

@app.route("/add-event", methods=["GET", "POST"])
def add_event():

    # Admin login check
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":

        name = request.form.get("name")
        date = request.form.get("date")
        time = request.form.get("time")
        venue = request.form.get("venue")

        # Get uploaded image
        image = request.files.get("image")

        # Check empty fields
        if not name or not date or not time or not venue:

            flash("Please fill all event fields.")

            return redirect(url_for("add_event"))

        # Default image URL
        image_url = None

        # Upload image to S3
        if image and image.filename:

            filename = secure_filename(image.filename)

            s3_key = f"uploads/{filename}"

            try:

                s3.upload_fileobj(
                    image,
                    S3_BUCKET,
                    s3_key
                )

                # Create S3 image URL
                image_url = s3_key

                print("Image uploaded successfully!")
                print("Image URL:", image_url)

            except Exception as e:

                print("S3 Upload Error:", e)

                flash("Image upload failed!")

                return redirect(url_for("add_event"))

        # Save event in database
        conn = get_db()

        conn.execute("""
            INSERT INTO events
            (name, date, time, venue, image_url)
            VALUES (?, ?, ?, ?, ?)
        """, (
            name,
            date,
            time,
            venue,
            image_url
        ))

        conn.commit()
        conn.close()

        flash("Event added successfully!")

        return redirect(url_for("admin"))

    return render_template("add_event.html")

# =========================================================
# EDIT EVENT
# =========================================================

@app.route("/edit-event/<int:event_id>", methods=["GET", "POST"])
def edit_event(event_id):

    # Admin login check
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()

    event = conn.execute("""
        SELECT *
        FROM events
        WHERE id = ?
    """, (event_id,)).fetchone()

    if not event:

        conn.close()

        flash("Event not found!")

        return redirect(url_for("admin"))

    if request.method == "POST":

        name = request.form.get("name")
        date = request.form.get("date")
        time = request.form.get("time")
        venue = request.form.get("venue")

        if not name or not date or not time or not venue:

            conn.close()

            flash("Please fill all event fields.")

            return redirect(
                url_for(
                    "edit_event",
                    event_id=event_id
                )
            )

        conn.execute("""
            UPDATE events
            SET name = ?, date = ?, time = ?, venue = ?
            WHERE id = ?
        """, (
            name,
            date,
            time,
            venue,
            event_id
        ))

        conn.commit()
        conn.close()

        flash("Event updated successfully!")

        return redirect(url_for("admin"))

    conn.close()

    return render_template(
        "edit_event.html",
        event=event
    )


# =========================================================
# DELETE EVENT
# =========================================================

@app.route("/delete-event/<int:event_id>")
def delete_event(event_id):

    # Admin login check
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()

    # Delete registrations related to event
    conn.execute("""
        DELETE FROM registrations
        WHERE event_id = ?
    """, (event_id,))

    # Delete event
    conn.execute("""
        DELETE FROM events
        WHERE id = ?
    """, (event_id,))

    conn.commit()
    conn.close()

    flash("Event deleted successfully!")

    return redirect(url_for("admin"))


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin-logout")
def admin_logout():

    session.pop("admin", None)

    return redirect(url_for("home"))


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    init_db()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
  if __name__ == "__main__":
    init_db()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
