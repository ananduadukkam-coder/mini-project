import os
import uuid
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)

db = SQLAlchemy(app)


# ========================================================
# DATABASE MODELS
# ========================================================

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=True)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    reservations = db.relationship("Reservation", backref="user", lazy=True)
    orders = db.relationship("Order", backref="user", lazy=True)


class MenuItem(db.Model):
    __tablename__ = "menu_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(500), default="")
    image = db.Column(db.String(255), default="/static/images/restaurant.jpg")
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "price": self.price,
            "description": self.description,
            "image": self.image,
            "is_available": self.is_available
        }


class Reservation(db.Model):
    __tablename__ = "reservations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)
    persons = db.Column(db.Integer, nullable=False, default=2)
    special_requests = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(20), default="Pending")  # Pending, Confirmed, Cancelled
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    customer_email = db.Column(db.String(120), nullable=False)
    delivery_address = db.Column(db.String(255), nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    tax = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="Pending")  # Pending, Preparing, Ready, Completed, Cancelled
    payment_method = db.Column(db.String(50), default="Not paid yet")
    payment_status = db.Column(db.String(20), default="Unpaid")  # Unpaid, Paid
    table_number = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan", lazy=True)


class RestaurantTable(db.Model):
    __tablename__ = "restaurant_tables"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, unique=True, nullable=False)
    seats = db.Column(db.Integer, default=4)


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=True)
    item_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    customizations = db.Column(db.String(255), default="")
    item_total = db.Column(db.Float, nullable=False)


class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    subject = db.Column(db.String(150), default="General Inquiry")
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="Unread")  # Unread, Read, Replied
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ========================================================
# SECURITY & AUTHENTICATION DECORATORS
# ========================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Admin login required.", "danger")
            return redirect(url_for("login", next=request.url))
        if not session.get("is_admin", False):
            flash("Access denied. Admin privileges required.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated_function


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


def save_image_file(file_storage):
    """Saves uploaded image safely and returns the static URL path."""
    if not file_storage or file_storage.filename == "":
        return None
    if allowed_file(file_storage.filename):
        ext = file_storage.filename.rsplit(".", 1)[1].lower()
        unique_name = f"{uuid.uuid4().hex[:12]}_{secure_filename(file_storage.filename.rsplit('.', 1)[0])}.{ext}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        file_storage.save(save_path)
        return f"/static/images/uploads/{unique_name}"
    return None


# Helper to compute server-side cart totals reliably
def compute_cart_details():
    cart = session.get("cart", [])
    computed_items = []
    subtotal = 0.0

    for item in cart:
        menu_item = db.session.get(MenuItem, item.get("id"))
        if not menu_item:
            # Try by name if ID not set
            menu_item = MenuItem.query.filter_by(name=item.get("name")).first()

        unit_price = menu_item.price if menu_item else float(item.get("price", 0))
        qty = max(1, int(item.get("quantity", 1)))
        extra_price = float(item.get("extras_price", 0.0))
        item_total = (unit_price + extra_price) * qty

        subtotal += item_total
        computed_items.append({
            "id": menu_item.id if menu_item else item.get("id"),
            "name": menu_item.name if menu_item else item.get("name"),
            "category": menu_item.category if menu_item else "",
            "price": unit_price,
            "extras_price": extra_price,
            "quantity": qty,
            "customizations": item.get("customizations", ""),
            "item_total": round(item_total, 2)
        })

    tax = round(subtotal * 0.05, 2)
    total = round(subtotal + tax, 2)
    return computed_items, round(subtotal, 2), tax, total


# ========================================================
# DATABASE INITIALIZATION & SEEDING
# ========================================================

DEFAULT_MENU_ITEMS = [
    {
        "name": "Veg Burger",
        "category": "Burger",
        "price": 120.0,
        "description": "Crisp vegetable patty with melted cheese, lettuce, fresh tomatoes, and special creamy mayo sauce in a toasted sesame bun.",
        "image": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd"
    },
    {
        "name": "Pizza",
        "category": "Pizza",
        "price": 250.0,
        "description": "Handcrafted crust loaded with mozzarella cheese, homemade tomato sauce, bell peppers, black olives, onions, and oregano.",
        "image": "https://images.unsplash.com/photo-1513104890138-7c749659a591"
    },
    {
        "name": "Pasta",
        "category": "Pasta",
        "price": 180.0,
        "description": "Penne tossed in silky Italian white cream sauce with garlic, sauteed mushrooms, herbs, and melted parmesan cheese.",
        "image": "https://images.unsplash.com/photo-1555949258-eb67b1ef0ceb"
    },
    {
        "name": "Biryani",
        "category": "Rice",
        "price": 320.0,
        "description": "Authentic fragrant Basmati rice slow-cooked with rich spices, saffron, caramelized onions, served with cooling raita and gravy.",
        "image": "https://images.unsplash.com/photo-1633945274405-b6c8069047b0?w=500"
    },
    {
        "name": "Paneer Tikka",
        "category": "Starter",
        "price": 220.0,
        "description": "Fresh cottage cheese cubes marinated in aromatic tandoori spices and char-grilled to perfection with peppers and mint chutney.",
        "image": "https://images.unsplash.com/photo-1567188040759-fb8a883dc6d8?w=500"
    },
    {
        "name": "French Fries",
        "category": "Snacks",
        "price": 90.0,
        "description": "Golden crispy potato fries seasoned with peri-peri herbs and served with tangy dipping sauce.",
        "image": "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=500"
    },
    {
        "name": "Chicken Wings",
        "category": "Starter",
        "price": 280.0,
        "description": "Juicy chicken wings tossed in smoky BBQ glaze, sprinkled with sesame seeds and fresh scallions.",
        "image": "https://images.unsplash.com/photo-1504674900247-0877df9cc836"
    },
    {
        "name": "Sandwich",
        "category": "Sandwich",
        "price": 150.0,
        "description": "Multi-layered grilled sandwich with spiced vegetables, cheese, and our signature green mint chutney.",
        "image": "https://images.unsplash.com/photo-1509722747041-616f39b57569?w=500"
    },
    {
        "name": "Coffee",
        "category": "Beverage",
        "price": 80.0,
        "description": "Rich freshly brewed espresso with steamed creamy milk and a gentle aromatic foam layer.",
        "image": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085"
    },
    {
        "name": "Chocolate Ice Cream",
        "category": "Dessert",
        "price": 100.0,
        "description": "Velvety Belgian chocolate ice cream studded with chocolate chips and rich chocolate fudge drizzle.",
        "image": "https://images.unsplash.com/photo-1563805042-7684c019e1cb"
    },
    {
        "name": "Strawberry Sundae",
        "category": "Dessert",
        "price": 140.0,
        "description": "Luscious strawberry scoops topped with strawberry compote, whipped cream, and crunchy toasted nuts.",
        "image": "https://images.unsplash.com/photo-1600718374662-0483d2b9da44?w=500"
    },
    {
        "name": "Sizzling Brownie",
        "category": "Dessert",
        "price": 190.0,
        "description": "Warm gooey chocolate walnut brownie served on a hot sizzler plate with vanilla bean ice cream and hot fudge.",
        "image": "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=500"
    },
    {
        "name": "Blueberry Cheesecake",
        "category": "Dessert",
        "price": 210.0,
        "description": "Creamy New York style cheesecake on a buttery graham crust, crowned with sweet-tart blueberry coulis.",
        "image": "https://images.unsplash.com/photo-1533134242443-d4fd215305ad?w=500"
    },
    {
        "name": "Falooda",
        "category": "Dessert",
        "price": 180.0,
        "description": "Royal dessert beverage crafted with rose milk, vermicelli, sweet basil seeds, ice cream, and dry fruits.",
        "image": "https://images.unsplash.com/photo-1541658016709-82535e94bc69?w=500"
    }
]


def migrate_schema():
    """Add the dine-in columns to an existing SQLite database without losing data."""
    from sqlalchemy import text
    if db.engine.dialect.name != "sqlite":
        return
    with db.engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(orders)"))}
        if cols and "table_number" not in cols:
            conn.execute(text("ALTER TABLE orders ADD COLUMN table_number INTEGER"))
        if cols and "payment_status" not in cols:
            conn.execute(text("ALTER TABLE orders ADD COLUMN payment_status VARCHAR(20) DEFAULT 'Unpaid'"))


def init_database():
    with app.app_context():
        db.create_all()
        migrate_schema()

        # Seed dining tables (QR codes are generated per table)
        if RestaurantTable.query.count() == 0:
            for n in range(1, 11):
                db.session.add(RestaurantTable(number=n, seats=4))
            db.session.commit()

        # Seed default Admin account if not present
        # Migrate the old admin address (pre-rebrand) so existing databases keep working
        legacy_admin = User.query.filter_by(email="admin@restaurant.com").first()
        if legacy_admin and not User.query.filter_by(email="admin@bitetheory.com").first():
            legacy_admin.email = "admin@bitetheory.com"
            legacy_admin.fullname = "BITE THEORY Administrator"
            db.session.commit()

        admin_user = User.query.filter_by(email="admin@bitetheory.com").first()
        if not admin_user:
            admin_user = User(
                fullname="BITE THEORY Administrator",
                email="admin@bitetheory.com",
                phone="+91 9876543210",
                password=generate_password_hash("Admin@123"),
                is_admin=True
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Default admin created: admin@bitetheory.com / Admin@123")

        # Seed menu items if empty
        if MenuItem.query.count() == 0:
            for item in DEFAULT_MENU_ITEMS:
                db.session.add(MenuItem(
                    name=item["name"],
                    category=item["category"],
                    price=item["price"],
                    description=item["description"],
                    image=item["image"],
                    is_available=True
                ))
            db.session.commit()
            print(f"Seeded {len(DEFAULT_MENU_ITEMS)} menu items.")


# ========================================================
# CONTEXT PROCESSORS
# ========================================================

@app.template_filter("ist")
def to_ist(dt):
    """Stored times are UTC; show them in Indian Standard Time."""
    if dt is None:
        return dt
    return dt + timedelta(hours=5, minutes=30)


def iso_utc(dt):
    return dt.isoformat() + "Z" if dt and dt.tzinfo is None else (dt.isoformat() if dt else None)


def all_tables():
    return RestaurantTable.query.order_by(RestaurantTable.number).all()


def can_view_order(order):
    if session.get("is_admin"):
        return True
    if order.id in session.get("my_orders", []):
        return True
    uid = session.get("user_id")
    return bool(uid and order.user_id == uid)


@app.context_processor
def inject_global_data():
    cart = session.get("cart", [])
    cart_count = sum(item.get("quantity", 1) for item in cart)
    return {
        "cart_count": cart_count,
        "current_user_name": session.get("user_name"),
        "table_no": session.get("table_no"),
        "is_admin_user": session.get("is_admin", False)
    }


# ========================================================
# PUBLIC / CUSTOMER ROUTES
# ========================================================

@app.route("/")
def home():
    menu_items = MenuItem.query.filter_by(is_available=True).all()
    categories = sorted(list(set(item.category for item in menu_items)))
    computed_items, subtotal, tax, total = compute_cart_details()

    # Pre-fill user data if logged in
    user_data = None
    if "user_id" in session:
        user_data = db.session.get(User, session["user_id"])

    return render_template(
        "rest.html",
        menu_items=menu_items,
        categories=categories,
        cart_items=computed_items,
        subtotal=subtotal,
        tax=tax,
        total=total,
        user=user_data,
        tables=all_tables()
    )


@app.route("/menu")
def menu():
    selected_category = request.args.get("category", "")
    query = MenuItem.query.filter_by(is_available=True)
    if selected_category:
        query = query.filter_by(category=selected_category)
    items = query.all()
    all_categories = sorted(list(set(m.category for m in MenuItem.query.all())))

    return render_template(
        "menu.html",
        items=items,
        categories=all_categories,
        selected_category=selected_category
    )


@app.route("/api/menu")
def api_menu():
    items = MenuItem.query.filter_by(is_available=True).all()
    return jsonify([item.to_dict() for item in items])


# ========================================================
# AUTHENTICATION ROUTES
# ========================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        if not fullname or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return render_template("register.html", fullname=fullname, email=email, phone=phone)

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("register.html", fullname=fullname, email=email, phone=phone)

        if confirm_password and password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html", fullname=fullname, email=email, phone=phone)

        # Check existing user
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("An account with this email already exists. Please login.", "danger")
            return redirect(url_for("login"))

        # Create new customer
        hashed_password = generate_password_hash(password)
        new_user = User(
            fullname=fullname,
            email=email,
            phone=phone,
            password=hashed_password,
            is_admin=False
        )
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        next_page = request.args.get("next") or request.form.get("next")

        if not email or not password:
            flash("Please provide both email and password.", "danger")
            return render_template("login.html", email=email)

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            # Save session
            session["user_id"] = user.id
            session["user_name"] = user.fullname
            session["user_email"] = user.email
            session["is_admin"] = user.is_admin

            flash(f"Welcome back, {user.fullname}!", "success")

            if next_page and (next_page.startswith("/") and not next_page.startswith("//") or next_page.startswith(request.host_url)):
                return redirect(next_page)
            if user.is_admin:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("home"))
        else:
            flash("Invalid email or password. Please try again.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)
    session.pop("is_admin", None)
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("home"))


# ========================================================
# TABLE RESERVATIONS
# ========================================================

@app.route("/reservation", methods=["POST"])
@login_required
def reservation():
    user = db.session.get(User, session["user_id"])

    # Name and email come from the logged-in account - the customer is not asked again
    name = user.fullname
    email = user.email
    phone = request.form.get("phone", "").strip() or (user.phone or "")
    date_val = request.form.get("date", "").strip()
    time_val = request.form.get("time", "").strip()
    persons_raw = request.form.get("persons", "2").strip()
    special_requests = request.form.get("special_requests", "").strip()

    # Validation
    if not phone or not date_val:
        flash("Please provide your phone number and reservation date.", "danger")
        return redirect(url_for("home") + "#reservation")

    try:
        persons = int(persons_raw)
        if persons < 1:
            persons = 1
    except ValueError:
        persons = 2

    if not time_val:
        time_val = "19:00"

    booking = Reservation(
        user_id=user.id,
        name=name,
        phone=phone,
        email=email,
        date=date_val,
        time=time_val,
        persons=persons,
        special_requests=special_requests,
        status="Pending"
    )
    db.session.add(booking)
    db.session.commit()

    flash(f"Table reserved for {persons} guest(s) on {date_val} at {time_val}. Status: Pending confirmation.", "success")
    return redirect(url_for("reservations_view"))


@app.route("/reservations")
def reservations_view():
    user_id = session.get("user_id")
    if user_id:
        user = db.session.get(User, user_id)
        if user.is_admin:
            all_reservations = Reservation.query.order_by(Reservation.created_at.desc()).all()
        else:
            all_reservations = Reservation.query.filter(
                (Reservation.user_id == user_id) | (Reservation.email == user.email)
            ).order_by(Reservation.created_at.desc()).all()
    else:
        # Show recent guest booking if in flash/session or prompt login
        all_reservations = []

    return render_template("reservations.html", reservations=all_reservations)


# ========================================================
# SHOPPING CART & ORDERING
# ========================================================

@app.route("/cart/add", methods=["POST"])
def cart_add():
    item_id = request.form.get("item_id")
    food_name = request.form.get("food", "").strip()
    quantity = int(request.form.get("quantity", 1))
    customizations = request.form.get("customizations", "")
    extras_price = float(request.form.get("extras_price", 0.0))

    menu_item = None
    if item_id:
        menu_item = db.session.get(MenuItem, int(item_id))
    elif food_name:
        menu_item = MenuItem.query.filter_by(name=food_name).first()

    if not menu_item:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"status": "error", "message": "Item not found"}), 404
        flash("Item not found.", "danger")
        return redirect(url_for("home"))

    cart = session.get("cart", [])

    # Check if exact item + customizations already in cart
    found = False
    for item in cart:
        if item.get("id") == menu_item.id and item.get("customizations") == customizations:
            item["quantity"] = item.get("quantity", 1) + quantity
            found = True
            break

    if not found:
        cart.append({
            "id": menu_item.id,
            "name": menu_item.name,
            "price": menu_item.price,
            "extras_price": extras_price,
            "quantity": quantity,
            "customizations": customizations
        })

    session["cart"] = cart
    session.modified = True

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        computed_items, subtotal, tax, total = compute_cart_details()
        return jsonify({
            "status": "success",
            "message": f"Added {menu_item.name} to cart!",
            "cart_count": sum(i["quantity"] for i in computed_items),
            "cart": computed_items,
            "subtotal": subtotal,
            "tax": tax,
            "total": total
        })

    flash(f"Added {menu_item.name} to your cart!", "success")
    return redirect(url_for("cart"))


@app.route("/cart/update", methods=["POST"])
def cart_update():
    cart = session.get("cart", [])
    index = request.form.get("index")
    action = request.form.get("action")  # increase, decrease, remove

    if index is not None:
        try:
            idx = int(index)
            if 0 <= idx < len(cart):
                if action == "increase":
                    cart[idx]["quantity"] = cart[idx].get("quantity", 1) + 1
                elif action == "decrease":
                    if cart[idx].get("quantity", 1) > 1:
                        cart[idx]["quantity"] -= 1
                    else:
                        cart.pop(idx)
                elif action == "remove":
                    cart.pop(idx)

                session["cart"] = cart
                session.modified = True
        except (ValueError, IndexError):
            pass

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        computed_items, subtotal, tax, total = compute_cart_details()
        return jsonify({
            "status": "success",
            "cart_count": sum(i["quantity"] for i in computed_items),
            "cart": computed_items,
            "subtotal": subtotal,
            "tax": tax,
            "total": total
        })

    return redirect(url_for("cart"))


@app.route("/cart/clear", methods=["POST"])
def cart_clear():
    session["cart"] = []
    session.modified = True
    flash("Cart cleared.", "info")
    return redirect(url_for("cart"))


@app.route("/cart")
def cart():
    computed_items, subtotal, tax, total = compute_cart_details()
    user_data = None
    if "user_id" in session:
        user_data = db.session.get(User, session["user_id"])

    return render_template(
        "cart.html",
        items=computed_items,
        subtotal=subtotal,
        tax=tax,
        total=total,
        user=user_data,
        tables=all_tables()
    )


@app.route("/t/<int:table_no>")
def table_landing(table_no):
    """Target of the QR code printed on each table."""
    table = RestaurantTable.query.filter_by(number=table_no).first()
    if not table:
        flash("This table QR code is not valid. Please select your table.", "warning")
        return redirect(url_for("scan"))
    session["table_no"] = table.number
    flash(f"Welcome to BITE THEORY! You are seated at Table {table.number}.", "success")
    return redirect(url_for("menu"))


@app.route("/scan", methods=["GET", "POST"])
def scan():
    """Fallback when a QR cannot be scanned: pick the table number manually."""
    if request.method == "POST":
        try:
            n = int(request.form.get("table_no", ""))
        except ValueError:
            n = None
        if n and RestaurantTable.query.filter_by(number=n).first():
            session["table_no"] = n
            return redirect(url_for("menu"))
        flash("Please choose a valid table.", "danger")
    return render_template("scan.html", tables=all_tables())


@app.route("/checkout", methods=["POST"])
def checkout():
    computed_items, subtotal, tax, total = compute_cart_details()

    if not computed_items:
        flash("Your cart is empty! Please add items before placing an order.", "warning")
        return redirect(url_for("menu"))

    # Table comes from the scanned QR (session) or the selector on the form
    try:
        table_no = int(request.form.get("table_no") or session.get("table_no") or 0)
    except ValueError:
        table_no = 0
    if not table_no or not RestaurantTable.query.filter_by(number=table_no).first():
        flash("Please scan your table QR code or choose your table number.", "danger")
        return redirect(url_for("cart"))
    session["table_no"] = table_no

    user = db.session.get(User, session["user_id"]) if session.get("user_id") else None
    name = request.form.get("name", "").strip() or (user.fullname if user else f"Table {table_no} Guest")
    notes = request.form.get("notes", "").strip()

    order = Order(
        user_id=user.id if user else None,
        customer_name=name,
        customer_phone=(user.phone if user and user.phone else "-"),
        customer_email=(user.email if user else ""),
        delivery_address=f"Dine-in · Table {table_no}",
        table_number=table_no,
        subtotal=subtotal,
        tax=tax,
        total=total,
        status="Pending",
        payment_status="Unpaid",
        payment_method="Not paid yet",
        notes=notes
    )
    db.session.add(order)
    db.session.flush()

    for item in computed_items:
        db.session.add(OrderItem(
            order_id=order.id,
            menu_item_id=item.get("id"),
            item_name=item["name"],
            price=item["price"] + item.get("extras_price", 0.0),
            quantity=item["quantity"],
            customizations=item.get("customizations", ""),
            item_total=item["item_total"]
        ))
    db.session.commit()

    # Remember this order for the guest (no login needed) and clear the cart
    my_orders = session.get("my_orders", [])
    my_orders.append(order.id)
    session["my_orders"] = my_orders
    session["cart"] = []
    session.modified = True

    flash(f"Order #{order.id} sent to the kitchen for Table {table_no}!", "success")
    return redirect(url_for("order_track", order_id=order.id))


@app.route("/order/<int:order_id>")
def order_track(order_id):
    order = Order.query.get_or_404(order_id)
    if not can_view_order(order):
        flash("Please place an order from your table to track it.", "warning")
        return redirect(url_for("scan"))
    upi_link = (
        f"upi://pay?pa={app.config['UPI_ID']}&pn={app.config['UPI_NAME'].replace(' ', '%20')}"
        f"&am={order.total:.2f}&cu=INR&tn=BITE%20THEORY%20Order%20{order.id}"
    )
    return render_template("order.html", order=order, upi_link=upi_link)


@app.route("/api/order/<int:order_id>/status")
def api_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    if not can_view_order(order):
        abort(403)
    return jsonify({
        "id": order.id,
        "status": order.status,
        "payment_status": order.payment_status
    })


@app.route("/order/<int:order_id>/pay", methods=["POST"])
def order_pay(order_id):
    """Customer confirms the UPI payment (or chooses to pay at the counter)."""
    order = Order.query.get_or_404(order_id)
    if not can_view_order(order):
        abort(403)
    if order.status == "Cancelled":
        flash("This order was cancelled.", "danger")
        return redirect(url_for("order_track", order_id=order.id))

    method = request.form.get("method", "upi")
    if method == "counter":
        order.payment_method = "Pay at Counter"
        flash("Please pay at the counter. The cashier will mark your bill as paid.", "info")
    elif order.payment_status != "Paid":
        order.payment_method = "UPI QR"
        order.payment_status = "Paid"
        flash(f"Payment of ₹{order.total:.2f} received. Thank you!", "success")
    db.session.commit()
    return redirect(url_for("order_track", order_id=order.id))


# ========================================================
# KITCHEN DISPLAY (STAFF)
# ========================================================

KITCHEN_NEXT = {"Pending": "Preparing", "Preparing": "Ready", "Ready": "Completed"}


@app.route("/kitchen")
@admin_required
def kitchen():
    return render_template("kitchen.html")


@app.route("/api/kitchen/orders")
@admin_required
def api_kitchen_orders():
    orders = Order.query.filter(Order.status.in_(["Pending", "Preparing", "Ready"])) \
        .order_by(Order.created_at.asc()).all()
    return jsonify([{
        "id": o.id,
        "table": o.table_number,
        "customer": o.customer_name,
        "status": o.status,
        "notes": o.notes or "",
        "payment_status": o.payment_status,
        "created_at": iso_utc(o.created_at),
        "items": [{"name": i.item_name, "qty": i.quantity, "custom": i.customizations or ""} for i in o.items]
    } for o in orders])


@app.route("/api/kitchen/order/<int:order_id>/status", methods=["POST"])
@admin_required
def api_kitchen_update(order_id):
    order = Order.query.get_or_404(order_id)
    data = request.get_json(silent=True) or {}
    new_status = data.get("status") or KITCHEN_NEXT.get(order.status)
    if new_status not in ["Pending", "Preparing", "Ready", "Completed", "Cancelled"]:
        return jsonify({"status": "error", "message": "Invalid status"}), 400
    order.status = new_status
    db.session.commit()
    return jsonify({"status": "success", "order_status": order.status})


@app.route("/orders")
def orders_view():
    user_id = session.get("user_id")
    if user_id:
        user = db.session.get(User, user_id)
        if user.is_admin:
            user_orders = Order.query.order_by(Order.created_at.desc()).all()
        else:
            user_orders = Order.query.filter(
                (Order.user_id == user_id) | (Order.customer_email == user.email)
            ).order_by(Order.created_at.desc()).all()
    else:
        ids = session.get("my_orders", [])
        user_orders = Order.query.filter(Order.id.in_(ids)).order_by(Order.created_at.desc()).all() if ids else []

    return render_template("orders.html", orders=user_orders)


# ========================================================
# HISTORY (ORDERS + RESERVATIONS) & REORDER
# ========================================================

@app.route("/history")
@login_required
def history():
    user = db.session.get(User, session["user_id"])

    orders = Order.query.filter(
        (Order.user_id == user.id) | (Order.customer_email == user.email)
    ).order_by(Order.created_at.desc()).all()
    bookings = Reservation.query.filter(
        (Reservation.user_id == user.id) | (Reservation.email == user.email)
    ).order_by(Reservation.created_at.desc()).all()

    valid_orders = [o for o in orders if o.status != "Cancelled"]
    stats = {
        "total_orders": len(orders),
        "completed_orders": sum(1 for o in orders if o.status == "Completed"),
        "total_spent": round(sum(o.total for o in valid_orders), 2),
        "total_bookings": len(bookings),
    }

    # Most frequently ordered dishes
    dish_counts = {}
    for o in valid_orders:
        for it in o.items:
            dish_counts[it.item_name] = dish_counts.get(it.item_name, 0) + it.quantity
    favourites = sorted(dish_counts.items(), key=lambda x: x[1], reverse=True)[:3]

    return render_template(
        "history.html",
        orders=orders,
        bookings=bookings,
        stats=stats,
        favourites=favourites
    )


@app.route("/order/<int:order_id>/reorder", methods=["POST"])
@login_required
def reorder(order_id):
    order = Order.query.get_or_404(order_id)
    user = db.session.get(User, session["user_id"])
    if order.user_id != user.id and order.customer_email != user.email:
        abort(403)

    cart = session.get("cart", [])
    added = 0
    for it in order.items:
        menu_item = db.session.get(MenuItem, it.menu_item_id) if it.menu_item_id else None
        if not menu_item or not menu_item.is_available:
            continue
        extras = max(0.0, round(it.price - menu_item.price, 2))
        for c in cart:
            if c.get("id") == menu_item.id and c.get("customizations") == (it.customizations or ""):
                c["quantity"] = c.get("quantity", 1) + it.quantity
                break
        else:
            cart.append({
                "id": menu_item.id,
                "name": menu_item.name,
                "price": menu_item.price,
                "extras_price": extras,
                "quantity": it.quantity,
                "customizations": it.customizations or ""
            })
        added += 1

    session["cart"] = cart
    session.modified = True

    if added:
        flash(f"Items from Order #{order.id} added to your cart.", "success")
    else:
        flash("Those items are no longer available on the menu.", "warning")
    return redirect(url_for("cart"))


# ========================================================
# CONTACT FORM
# ========================================================

@app.route("/contact", methods=["POST"])
def contact():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    subject = request.form.get("subject", "General Inquiry").strip()
    message = request.form.get("message", "").strip()

    if not name or not email or not message:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"status": "error", "message": "Please fill in all required fields."}), 400
        flash("Please fill in Name, Email, and Message.", "danger")
        return redirect(url_for("home") + "#contact")

    msg = ContactMessage(
        name=name,
        email=email,
        phone=phone,
        subject=subject,
        message=message,
        status="Unread"
    )
    db.session.add(msg)
    db.session.commit()

    success_text = "Thank you! Your message has been sent successfully. We will get back to you shortly."
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"status": "success", "message": success_text})

    flash(success_text, "success")
    return redirect(url_for("home") + "#contact")


# ========================================================
# ADMIN PANEL (PROTECTED)
# ========================================================

@app.route("/admin")
@admin_required
def admin_dashboard():
    # Statistics
    total_orders = Order.query.count()
    total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0.0
    pending_orders = Order.query.filter_by(status="Pending").count()
    total_reservations = Reservation.query.count()
    pending_reservations = Reservation.query.filter_by(status="Pending").count()
    total_menu_items = MenuItem.query.count()
    total_users = User.query.count()
    unread_messages = ContactMessage.query.filter_by(status="Unread").count()

    # Lists
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(15).all()
    recent_reservations = Reservation.query.order_by(Reservation.created_at.desc()).limit(15).all()
    menu_list = MenuItem.query.order_by(MenuItem.category, MenuItem.name).all()
    users_list = User.query.order_by(User.created_at.desc()).all()
    messages_list = ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(15).all()
    categories = sorted(list(set(m.category for m in menu_list)))

    return render_template(
        "admin.html",
        stats={
            "total_orders": total_orders,
            "total_revenue": round(total_revenue, 2),
            "pending_orders": pending_orders,
            "total_reservations": total_reservations,
            "pending_reservations": pending_reservations,
            "total_menu_items": total_menu_items,
            "total_users": total_users,
            "unread_messages": unread_messages
        },
        orders=recent_orders,
        reservations=recent_reservations,
        menu=menu_list,
        users=users_list,
        messages=messages_list,
        categories=categories
    )


# Admin Menu Management
@app.route("/admin/menu/add", methods=["POST"])
@admin_required
def admin_menu_add():
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "Main").strip()
    price_raw = request.form.get("price", "0").strip()
    description = request.form.get("description", "").strip()
    image_url = request.form.get("image_url", "").strip()
    image_file = request.files.get("image_file")

    if not name or not category or not price_raw:
        flash("Name, category, and price are required.", "danger")
        return redirect(url_for("admin_dashboard") + "#menu")

    try:
        price = float(price_raw)
    except ValueError:
        flash("Invalid price value.", "danger")
        return redirect(url_for("admin_dashboard") + "#menu")

    # Image handling: file upload takes priority over URL
    image_path = "/static/images/restaurant.jpg"
    if image_file and image_file.filename != "":
        saved = save_image_file(image_file)
        if saved:
            image_path = saved
        else:
            flash("Invalid image file format. Allowed: PNG, JPG, JPEG, WEBP, GIF.", "warning")
    elif image_url:
        image_path = image_url

    new_item = MenuItem(
        name=name,
        category=category,
        price=price,
        description=description,
        image=image_path,
        is_available=True
    )
    db.session.add(new_item)
    db.session.commit()

    flash(f"Menu item '{name}' added successfully!", "success")
    return redirect(url_for("admin_dashboard") + "#menu")


@app.route("/admin/menu/<int:id>/edit", methods=["POST"])
@admin_required
def admin_menu_edit(id):
    item = MenuItem.query.get_or_404(id)
    item.name = request.form.get("name", item.name).strip()
    item.category = request.form.get("category", item.category).strip()
    price_raw = request.form.get("price", str(item.price)).strip()
    item.description = request.form.get("description", item.description).strip()
    item.is_available = "is_available" in request.form

    try:
        item.price = float(price_raw)
    except ValueError:
        pass

    # Check image upload or url
    image_file = request.files.get("image_file")
    image_url = request.form.get("image_url", "").strip()
    if image_file and image_file.filename != "":
        saved = save_image_file(image_file)
        if saved:
            item.image = saved
    elif image_url:
        item.image = image_url

    db.session.commit()
    flash(f"Menu item '{item.name}' updated successfully!", "success")
    return redirect(url_for("admin_dashboard") + "#menu")


@app.route("/admin/menu/<int:id>/delete", methods=["POST", "GET"])
@admin_required
def admin_menu_delete(id):
    item = MenuItem.query.get_or_404(id)
    name = item.name
    db.session.delete(item)
    db.session.commit()
    flash(f"Menu item '{name}' removed.", "info")
    return redirect(url_for("admin_dashboard") + "#menu")


# Admin Orders Management
@app.route("/admin/order/<int:id>/status", methods=["POST"])
@admin_required
def admin_order_status(id):
    order = Order.query.get_or_404(id)
    new_status = request.form.get("status")
    allowed_statuses = ["Pending", "Preparing", "Ready", "Completed", "Cancelled"]
    if new_status in allowed_statuses:
        order.status = new_status
        db.session.commit()
        flash(f"Order #{order.id} status updated to {new_status}.", "success")
    return redirect(url_for("admin_dashboard") + "#orders")


@app.route("/admin/order/<int:id>/paid", methods=["POST"])
@admin_required
def admin_order_paid(id):
    order = Order.query.get_or_404(id)
    order.payment_status = "Paid"
    if order.payment_method in (None, "", "Not paid yet", "Pay at Counter"):
        order.payment_method = "Cash / Counter"
    db.session.commit()
    flash(f"Order #{order.id} marked as paid.", "success")
    return redirect(url_for("admin_dashboard") + "#orders")


@app.route("/admin/tables")
@admin_required
def admin_tables():
    return render_template("admin_tables.html", tables=all_tables())


@app.route("/admin/tables/add", methods=["POST"])
@admin_required
def admin_table_add():
    try:
        n = int(request.form.get("number", ""))
    except ValueError:
        n = 0
    if n < 1:
        flash("Enter a valid table number.", "danger")
    elif RestaurantTable.query.filter_by(number=n).first():
        flash(f"Table {n} already exists.", "warning")
    else:
        db.session.add(RestaurantTable(number=n, seats=4))
        db.session.commit()
        flash(f"Table {n} added.", "success")
    return redirect(url_for("admin_tables"))


@app.route("/admin/tables/<int:id>/delete", methods=["POST"])
@admin_required
def admin_table_delete(id):
    t = RestaurantTable.query.get_or_404(id)
    db.session.delete(t)
    db.session.commit()
    flash(f"Table {t.number} removed.", "info")
    return redirect(url_for("admin_tables"))


@app.route("/admin/order/<int:id>/delete", methods=["POST", "GET"])
@admin_required
def admin_order_delete(id):
    order = Order.query.get_or_404(id)
    order_id = order.id
    db.session.delete(order)
    db.session.commit()
    flash(f"Order #{order_id} deleted successfully.", "info")
    return redirect(url_for("admin_dashboard") + "#orders")


# Admin Reservations Management
@app.route("/admin/reservation/<int:id>/status", methods=["POST"])
@admin_required
def admin_reservation_status(id):
    reservation = Reservation.query.get_or_404(id)
    new_status = request.form.get("status")
    if new_status in ["Pending", "Confirmed", "Cancelled"]:
        reservation.status = new_status
        db.session.commit()
        flash(f"Reservation #{reservation.id} status updated to {new_status}.", "success")
    return redirect(url_for("admin_dashboard") + "#reservations")


@app.route("/admin/reservation/<int:id>/delete", methods=["POST", "GET"])
@admin_required
def admin_reservation_delete(id):
    res = Reservation.query.get_or_404(id)
    db.session.delete(res)
    db.session.commit()
    flash("Reservation deleted.", "info")
    return redirect(url_for("admin_dashboard") + "#reservations")


# Admin Users Management
@app.route("/admin/user/<int:id>/delete", methods=["POST", "GET"])
@admin_required
def admin_user_delete(id):
    if id == session.get("user_id"):
        flash("You cannot delete your own admin account while logged in.", "danger")
        return redirect(url_for("admin_dashboard") + "#users")

    user = User.query.get_or_404(id)
    name = user.fullname
    db.session.delete(user)
    db.session.commit()
    flash(f"User '{name}' has been deleted.", "info")
    return redirect(url_for("admin_dashboard") + "#users")


# Admin Contact Messages
@app.route("/admin/message/<int:id>/status", methods=["POST"])
@admin_required
def admin_message_status(id):
    msg = ContactMessage.query.get_or_404(id)
    msg.status = request.form.get("status", "Read")
    db.session.commit()
    flash("Message status updated.", "success")
    return redirect(url_for("admin_dashboard") + "#messages")


@app.route("/admin/message/<int:id>/delete", methods=["POST", "GET"])
@admin_required
def admin_message_delete(id):
    msg = ContactMessage.query.get_or_404(id)
    db.session.delete(msg)
    db.session.commit()
    flash("Message deleted.", "info")
    return redirect(url_for("admin_dashboard") + "#messages")


# Admin Password Change
@app.route("/admin/change-password", methods=["POST"])
@admin_required
def admin_change_password():
    current_user = db.session.get(User, session["user_id"])
    old_pw = request.form.get("old_password", "")
    new_pw = request.form.get("new_password", "")
    confirm_pw = request.form.get("confirm_password", "")

    if not check_password_hash(current_user.password, old_pw):
        flash("Current password incorrect.", "danger")
        return redirect(url_for("admin_dashboard") + "#settings")

    if len(new_pw) < 6:
        flash("New password must be at least 6 characters.", "danger")
        return redirect(url_for("admin_dashboard") + "#settings")

    if new_pw != confirm_pw:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("admin_dashboard") + "#settings")

    current_user.password = generate_password_hash(new_pw)
    db.session.commit()
    flash("Admin password updated successfully!", "success")
    return redirect(url_for("admin_dashboard") + "#settings")


# ========================================================
# BACKWARD COMPATIBLE ROUTES
# ========================================================

@app.route("/delete_menu/<int:id>")
@admin_required
def legacy_delete_menu(id):
    return admin_menu_delete(id)


@app.route("/delete_order/<int:id>")
@admin_required
def legacy_delete_order(id):
    return admin_order_delete(id)


@app.route("/delete_user/<int:id>")
@admin_required
def legacy_delete_user(id):
    return admin_user_delete(id)


@app.route("/delete_reservation/<int:id>")
@admin_required
def legacy_delete_reservation(id):
    return admin_reservation_delete(id)


@app.route("/users")
@admin_required
def legacy_users():
    return render_template("users.html", users=User.query.all())


@app.route("/api/health")
def health():
    return {
        "status": "ok",
        "database": "sqlite",
        "menu_items_count": MenuItem.query.count(),
        "users_count": User.query.count()
    }


# Initialize DB on load
init_database()


if __name__ == "__main__":
    # host="0.0.0.0" lets phones on the same Wi-Fi open the site (needed to scan table QR codes)
    app.run(debug=True, host="0.0.0.0", port=5000)
