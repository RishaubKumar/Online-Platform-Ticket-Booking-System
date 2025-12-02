from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import json
from datetime import datetime, timedelta
import random

"""
Deployment assumptions (from deployment diagram):
- Client device: Web browser
- Application server: This Flask app running on localhost:5000
- Database server: JSON files stored locally under the ./data directory
"""

app = Flask(__name__)
app.secret_key = "change_this_in_real_project"  # Simple session key for demo

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PLATFORMS_FILE = os.path.join(DATA_DIR, "platforms.json")
BOOKINGS_FILE = os.path.join(DATA_DIR, "bookings.json")
PAYMENTS_FILE = os.path.join(DATA_DIR, "payments.json")
TICKETS_FILE = os.path.join(DATA_DIR, "tickets.json")


# --------------------------
# JSON Storage Helper Layer
# --------------------------

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def load_json(path):
    """Utility function from 'Database' component – read JSON file or return empty list."""
    ensure_data_dir()
    if not os.path.exists(path):
        # Initialize with empty list if file does not exist
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_json(path, data):
    """Utility function from 'Database' component – write JSON data back to file."""
    ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_next_id(data, key_name):
    """Generate incremental IDs based on existing list of dicts."""
    if not data:
        return 1
    return max(item.get(key_name, 0) for item in data) + 1


def seed_platforms():
    """Ensure platforms.json has a few default platforms, matching specification."""
    platforms = load_json(PLATFORMS_FILE)
    if not platforms:
        platforms = [
            {"platformNumber": 1, "capacity": 200},
            {"platformNumber": 2, "capacity": 150},
        ]
        save_json(PLATFORMS_FILE, platforms)


# --------------------------
# Helper functions / services
# --------------------------

def get_logged_in_user():
    """Return currently logged in user dict based on session user_id."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    users = load_json(USERS_FILE)
    for u in users:
        if u.get("userId") == user_id:
            return u
    return None


def authenticate_user(email, password):
    """Authentication Service – simple user login (no hashing)."""
    users = load_json(USERS_FILE)
    for u in users:
        if u.get("email") == email and u.get("password") == password:
            return u
    return None


def check_platform_availability(platform_number):
    """
    Booking Service – check availability for a platform.
    Simple version: ensure total active bookings count is less than capacity.
    """
    platforms = load_json(PLATFORMS_FILE)
    bookings = load_json(BOOKINGS_FILE)
    tickets = load_json(TICKETS_FILE)

    platform = next(
        (p for p in platforms if p.get("platformNumber") == platform_number), None
    )
    if not platform:
        return False, "Platform not found."

    capacity = platform.get("capacity", 0)

    # Count bookings whose tickets are ACTIVE (simple capacity logic)
    active_count = 0
    for b in bookings:
        if b.get("platformNumber") == platform_number:
            ticket_id = b.get("ticketId")
            if ticket_id:
                t = next((t for t in tickets if t.get("ticketId") == ticket_id), None)
                if t and t.get("status") == "Active":
                    active_count += 1

    if active_count >= capacity:
        return False, f"Platform {platform_number} is full."
    return True, "Available"


def calculate_amount(duration_hours):
    """Booking Service – calculate amount. Use simple flat rate per hour."""
    rate_per_hour = 10  # e.g., 10 currency units per hour
    return rate_per_hour * duration_hours


def create_booking(user_id, platform_number, selected_duration):
    """
    Booking Service – createBooking() mapped from Booking class.
    Also creates an initial Ticket in state Created/Pending Payment.
    """
    bookings = load_json(BOOKINGS_FILE)
    tickets = load_json(TICKETS_FILE)

    booking_id = get_next_id(bookings, "bookingId")
    ticket_id = get_next_id(tickets, "ticketId")

    booking_time = datetime.now().isoformat()

    # Ticket generation service – generate() with initial state:
    issue_time = datetime.now().isoformat()
    expiry_time = (datetime.now() + timedelta(hours=selected_duration)).isoformat()

    ticket = {
        "ticketId": ticket_id,
        "issueTime": issue_time,
        "expiryTime": expiry_time,
        "status": "Pending Payment",  # Ticket state machine: Created -> Pending Payment
        "platformNumber": platform_number,
    }
    tickets.append(ticket)
    save_json(TICKETS_FILE, tickets)

    booking = {
        "bookingId": booking_id,
        "userId": user_id,
        "platformNumber": platform_number,
        "bookingTime": booking_time,
        "selectedDuration": selected_duration,
        "ticketId": ticket_id,
    }
    bookings.append(booking)
    save_json(BOOKINGS_FILE, bookings)

    return booking


def update_ticket_state(ticket):
    """
    Ticket state machine logic.
    - If Active and current_time > expiryTime => Expired
    - If Pending Payment: stays as is until payment.
    """
    if not ticket:
        return
    status = ticket.get("status")
    if status == "Active":
        try:
            expiry = datetime.fromisoformat(ticket.get("expiryTime"))
            if datetime.now() > expiry:
                ticket["status"] = "Expired"
        except Exception:
            pass


def save_ticket(ticket):
    """Persist a single ticket update back to JSON."""
    tickets = load_json(TICKETS_FILE)
    for idx, t in enumerate(tickets):
        if t.get("ticketId") == ticket.get("ticketId"):
            tickets[idx] = ticket
            break
    save_json(TICKETS_FILE, tickets)


def process_payment(booking_id, amount):
    """
    Payment Service – processPayment() mapped from Payment class.
    For demo, always succeed (or randomize if desired).
    """
    payments = load_json(PAYMENTS_FILE)
    tickets = load_json(TICKETS_FILE)
    bookings = load_json(BOOKINGS_FILE)

    payment_id = get_next_id(payments, "paymentId")
    payment_time = datetime.now().isoformat()

    # Simulate payment: we can randomize success/failure, but here we always succeed.
    # To make it closer to real life, uncomment the random line below.
    # success = random.choice([True, False])
    success = True

    payment_status = "SUCCESS" if success else "FAILED"

    payment = {
        "paymentId": payment_id,
        "bookingId": booking_id,
        "amount": amount,
        "paymentStatus": payment_status,
        "paymentTime": payment_time,
    }
    payments.append(payment)
    save_json(PAYMENTS_FILE, payments)

    # Link with ticket and update its state
    booking = next((b for b in bookings if b.get("bookingId") == booking_id), None)
    if booking:
        ticket_id = booking.get("ticketId")
        ticket = next((t for t in tickets if t.get("ticketId") == ticket_id), None)
        if ticket:
            if success:
                ticket["status"] = "Active"  # Ticket state machine: Pending Payment -> Active
            else:
                ticket["status"] = "Cancelled"  # treat failed payment as cancelled
            save_ticket(ticket)

    return success, payment


# --------------------------
# Authentication Routes (User + Admin)
# --------------------------

@app.route("/")
def home():
    """Home page – maps to Use Case: Login / Register entry point."""
    user = get_logged_in_user()
    return render_template("home.html", user=user)


@app.route("/register", methods=["GET", "POST"])
def register():
    """User registration – corresponds to User entity and login() preparation."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not (name and email and password):
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        users = load_json(USERS_FILE)
        if any(u.get("email") == email for u in users):
            flash("Email already registered.", "warning")
            return redirect(url_for("register"))

        user_id = get_next_id(users, "userId")
        users.append(
            {"userId": user_id, "name": name, "email": email, "password": password}
        )
        save_json(USERS_FILE, users)
        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """User login – implements User.login() from UML."""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        user = authenticate_user(email, password)
        if user:
            session.clear()
            session["user_id"] = user["userId"]
            session["user_name"] = user["name"]
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    """User logout – implements User.logout()."""
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("home"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """
    Simple admin login.
    From Admin class in UML – manageBookings() and managePlatform() will be behind this.
    Hard-coded credentials for demo.
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        # Hard-coded admin. In real system, store in JSON similar to users.
        if email == "admin@railway.com" and password == "admin123":
            session.clear()
            session["admin"] = True
            session["admin_name"] = "Station Admin"
            flash("Admin logged in.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "danger")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    session.pop("admin_name", None)
    flash("Admin logged out.", "info")
    return redirect(url_for("home"))


# --------------------------
# User Dashboard & Booking Flow
# --------------------------

@app.route("/dashboard")
def dashboard():
    """User dashboard – entry to Use Cases: Book Platform Ticket, View Booking History."""
    user = get_logged_in_user()
    if not user:
        flash("Please login first.", "warning")
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=user)


@app.route("/book", methods=["GET", "POST"])
def book():
    """
    Booking route – Use Case: Book Platform Ticket + Select Time Duration.
    Corresponds to Booking.createBooking() and Platform.checkAvailability().
    """
    user = get_logged_in_user()
    if not user:
        flash("Please login first.", "warning")
        return redirect(url_for("login"))

    seed_platforms()
    platforms = load_json(PLATFORMS_FILE)

    durations = [1, 2, 3, 4]  # hours
    amount = None

    if request.method == "POST":
        platform_number = int(request.form.get("platformNumber"))
        duration = int(request.form.get("duration"))

        available, msg = check_platform_availability(platform_number)
        if not available:
            flash(msg, "danger")
            return redirect(url_for("book"))

        amount = calculate_amount(duration)

        # Create booking and pending ticket, then redirect to payment page
        booking = create_booking(
            user_id=user["userId"],
            platform_number=platform_number,
            selected_duration=duration,
        )
        session["current_booking_id"] = booking["bookingId"]
        session["current_amount"] = amount
        return redirect(url_for("payment"))

    return render_template(
        "book.html",
        user=user,
        platforms=platforms,
        durations=durations,
        amount=amount,
    )


@app.route("/pay", methods=["GET", "POST"])
def payment():
    """
    Payment route – Use Case: Make Payment.
    Uses Payment.processPayment() and updates Ticket state to Active or Cancelled.
    """
    user = get_logged_in_user()
    if not user:
        flash("Please login first.", "warning")
        return redirect(url_for("login"))

    booking_id = session.get("current_booking_id")
    amount = session.get("current_amount")
    if not booking_id or not amount:
        flash("No booking to pay for.", "warning")
        return redirect(url_for("book"))

    bookings = load_json(BOOKINGS_FILE)
    booking = next((b for b in bookings if b.get("bookingId") == booking_id), None)

    if request.method == "POST":
        success, payment_record = process_payment(booking_id, amount)
        if success:
            flash("Payment successful!", "success")
            # After payment success: redirect to ticket details
            return redirect(url_for("ticket_details", booking_id=booking_id))
        else:
            flash("Payment failed. Please try again.", "danger")
            return redirect(url_for("book"))

    return render_template(
        "payment.html",
        user=user,
        booking=booking,
        amount=amount,
    )


@app.route("/ticket/<int:booking_id>")
def ticket_details(booking_id):
    """
    Ticket details – Use Case: Get Ticket Details.
    Ticket state machine: update state to Expired if needed when viewing.
    """
    user = get_logged_in_user()
    if not user:
        flash("Please login first.", "warning")
        return redirect(url_for("login"))

    bookings = load_json(BOOKINGS_FILE)
    tickets = load_json(TICKETS_FILE)
    payments = load_json(PAYMENTS_FILE)

    booking = next(
        (b for b in bookings if b.get("bookingId") == booking_id), None
    )
    if not booking or booking.get("userId") != user["userId"]:
        flash("Booking not found.", "danger")
        return redirect(url_for("dashboard"))

    ticket = next(
        (t for t in tickets if t.get("ticketId") == booking.get("ticketId")), None
    )

    # Update ticket state if expired
    if ticket:
        update_ticket_state(ticket)
        save_ticket(ticket)

    payment = next(
        (p for p in payments if p.get("bookingId") == booking_id), None
    )

    return render_template(
        "ticket.html",
        user=user,
        booking=booking,
        ticket=ticket,
        payment=payment,
    )


@app.route("/history")
def history():
    """
    Booking history – Use Case: View Booking History.
    Implements User.viewBookingHistory().
    """
    user = get_logged_in_user()
    if not user:
        flash("Please login first.", "warning")
        return redirect(url_for("login"))

    bookings = load_json(BOOKINGS_FILE)
    platforms = load_json(PLATFORMS_FILE)
    tickets = load_json(TICKETS_FILE)

    user_bookings = [b for b in bookings if b.get("userId") == user["userId"]]

    # Attach related data for display
    platform_map = {
        p.get("platformNumber"): p for p in platforms
    }
    ticket_map = {t.get("ticketId"): t for t in tickets}

    for b in user_bookings:
        b["platform"] = platform_map.get(b.get("platformNumber"))
        b["ticket"] = ticket_map.get(b.get("ticketId"))

    return render_template("history.html", user=user, bookings=user_bookings)


# --------------------------
# Admin Views – Manage Platforms and Bookings
# --------------------------

def require_admin():
    if not session.get("admin"):
        flash("Admin login required.", "warning")
        return False
    return True


@app.route("/admin/dashboard")
def admin_dashboard():
    """Admin dashboard – maps to Admin.manageBookings() and Admin.managePlatform()."""
    if not require_admin():
        return redirect(url_for("admin_login"))
    return render_template("admin_dashboard.html")


@app.route("/admin/platforms", methods=["GET", "POST"])
def admin_platforms():
    """
    Admin manage platforms – use case: Manage Platforms.
    Admin can add new platforms or update capacities.
    """
    if not require_admin():
        return redirect(url_for("admin_login"))

    platforms = load_json(PLATFORMS_FILE)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            platform_number = int(request.form.get("platformNumber"))
            capacity = int(request.form.get("capacity"))
            if any(p.get("platformNumber") == platform_number for p in platforms):
                flash("Platform already exists.", "warning")
            else:
                platforms.append(
                    {
                        "platformNumber": platform_number,
                        "capacity": capacity,
                    }
                )
                save_json(PLATFORMS_FILE, platforms)
                flash("Platform added.", "success")
        elif action == "update":
            platform_number = int(request.form.get("platformNumber"))
            capacity = int(request.form.get("capacity"))
            for p in platforms:
                if p.get("platformNumber") == platform_number:
                    p["capacity"] = capacity
                    save_json(PLATFORMS_FILE, platforms)
                    flash("Platform updated.", "success")
                    break

    platforms = load_json(PLATFORMS_FILE)
    return render_template("admin_platforms.html", platforms=platforms)


@app.route("/admin/bookings")
def admin_bookings():
    """
    Admin manage bookings – use case: Manage Bookings.
    Shows a list of all bookings, with user, platform and ticket info.
    """
    if not require_admin():
        return redirect(url_for("admin_login"))

    bookings = load_json(BOOKINGS_FILE)
    users = load_json(USERS_FILE)
    platforms = load_json(PLATFORMS_FILE)
    tickets = load_json(TICKETS_FILE)
    payments = load_json(PAYMENTS_FILE)

    user_map = {u.get("userId"): u for u in users}
    platform_map = {
        p.get("platformNumber"): p for p in platforms
    }
    ticket_map = {t.get("ticketId"): t for t in tickets}
    payment_map = {p.get("bookingId"): p for p in payments}

    for b in bookings:
        b["user"] = user_map.get(b.get("userId"))
        b["platform"] = platform_map.get(b.get("platformNumber"))
        b["ticket"] = ticket_map.get(b.get("ticketId"))
        b["payment"] = payment_map.get(b.get("bookingId"))

    return render_template("admin_bookings.html", bookings=bookings)


if __name__ == "__main__":
    seed_platforms()
    app.run(debug=True)


