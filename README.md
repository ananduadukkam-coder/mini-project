# BITE THEORY – Full-Stack Web Application

BITE THEORY is a **QR-based self-service dining system**: customers scan the QR code on their table, order from their phone, the order appears on the kitchen screen, the customer is notified when it is ready and pays the bill by UPI QR. Built built using **Python Flask**, **SQLite**, and **HTML5/CSS3/JavaScript**.

---

## 🍽️ Features

### Dine-in Self-Service Flow
1. **Scan** – each table has its own QR code (`/t/<table number>`). Scanning opens the menu already linked to that table.
2. **Order** – the customer adds dishes (with customizations) to the cart and taps **Send to Kitchen**. No login, name, e-mail or address is needed.
3. **Kitchen receives the ticket** – the **Kitchen Display** (`/kitchen`, staff login) shows New / Preparing / Ready columns, updates live, plays a sound for each new order and can print a ticket.
4. **Live notification** – the customer's order page updates automatically (Placed → Preparing → Ready → Served) and shows an alert, sound, vibration and optional phone notification when the food is ready.
5. **Pay by QR** – the order page shows a UPI QR code containing the exact bill amount (plus an *Open UPI App* button). The customer taps *I Have Paid*, or chooses *Pay at Counter* and the cashier marks it paid.

### Other Customer Features
- **Homepage**: hero, How It Works, special offers, dynamic menu with category filters, table reservation, gallery, reviews and contact form.
- **Optional Accounts**: register/login to keep an order history (`/history`) with statistics, favourite dishes, status filter and one-click **Reorder**.
- **Table Reservations**: logged-in customers book a table in advance.
- **Dark Mode** with local storage persistence.

### Admin Panel (`/admin`)
- **Table QR Codes** (`/admin/tables`): add/remove tables, generate and print a QR code for every table.
- **Kitchen Screen** (`/kitchen`): link in the admin menu bar.
- **Payments**: see Paid/Unpaid per order and mark counter payments as paid.
- **Protected Access**: Route-level protection requiring admin privileges. Unauthorized visitors are redirected to login.
- **Operations Dashboard**: Real-time business metrics (Total Orders, Total Revenue in ₹, Pending Orders, Reservations, Dishes count, Registered Customers, Unread Messages).
- **Order Management**: View all table orders with line items and payment status. Update status (`Pending`, `Preparing`, `Ready`, `Completed`, `Cancelled`) or delete orders.
- **Reservation Management**: Track dining reservations, update status (`Pending`, `Confirmed`, `Cancelled`), or remove entries.
- **Menu Management**:
  - Add new dishes with name, category, price, description, and image (safe local file upload or image URL).
  - Edit existing menu items (price, description, availability, image).
  - Delete dishes or mark as Sold Out.
- **Customer Management**: View registered user accounts, role badges, and manage customer records.
- **Contact Messages**: Read messages sent by customers, mark as read, or delete.
- **Security Settings**: Change admin password with hashing.

---

## 💻 Technology Stack

- **Backend**: Python Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Werkzeug 3.1.8
- **Database**: SQLite (`instance/restaurant.db`)
- **Frontend**: HTML5, CSS3, JavaScript (Fetch API)
- **Security**: Werkzeug password hashing (`pbkdf2:sha256`), Session-based authorization, server-side price validation, safe image file uploads.

---

## 📂 Project Structure

```
restaurant pp/
├── app.py                      # Main Flask application & routes
├── config.py                   # Application configuration & paths
├── requirements.txt            # Python dependencies
├── README.md                   # Documentation & setup instructions
│
├── instance/
│   └── restaurant.db           # SQLite database
│
├── templates/
│   ├── rest.html               # Main landing page
│   ├── history.html            # Order & reservation history
│   ├── order.html              # Live order status + UPI QR payment
│   ├── kitchen.html            # Kitchen display
│   ├── scan.html               # Manual table selection
│   ├── admin_tables.html       # Printable table QR codes
│   ├── login.html              # Customer & admin login page
│   ├── register.html           # Customer registration page
│   ├── menu.html               # Dedicated menu catalog page
│   ├── cart.html               # Full shopping cart & checkout page
│   ├── orders.html             # Customer order history & tracking
│   ├── reservations.html       # Customer table reservations
│   ├── users.html              # Admin customer management
│   └── admin.html              # Full administrative dashboard
│
└── static/
    ├── css/
    │   └── style.css           # Unified responsive stylesheet
    ├── images/
    │   ├── restaurant.jpg      # Hero & brand imagery
    │   └── uploads/            # Safe uploads folder for admin menu images
    └── js/                     # Static JavaScript assets
```

---

## 🚀 Setup & Execution (Windows)

### 1. Open Terminal & Navigate to Project
```powershell
cd "c:\Users\anand\Desktop\restaurant pp"
```

### 2. Activate Virtual Environment & Install Dependencies
```powershell
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run the Flask Application
```powershell
python app.py
```

### 4. Open in Browser
Visit: **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

### 5. Try the QR flow on a phone
1. Connect the phone and the PC to the **same Wi-Fi**.
2. Find the PC's IP address (`ipconfig` → IPv4, e.g. `192.168.1.5`).
3. Log in as admin → **Table QR Codes**, type `http://192.168.1.5:5000` in the box, click **Generate QR Codes**.
4. Scan a table QR with the phone camera, order, then open `/kitchen` on the PC to see the ticket.
5. Set the real UPI ID before the demo: `set UPI_ID=yourname@bank` (PowerShell: `$env:UPI_ID="yourname@bank"`), or edit `UPI_ID` in `config.py`.

---

## 🔐 Admin Credentials

A default administrator account is initialized automatically on first startup (an older `admin@restaurant.com` account in an existing database is renamed automatically):

- **Admin URL**: `http://127.0.0.1:5000/login` or `http://127.0.0.1:5000/admin`
- **Email**: `admin@bitetheory.com`
- **Password**: `Admin@123`

### How to Change the Admin Password
1. Log in with the default credentials above.
2. Go to the **Admin Dashboard** (`/admin`).
3. Click on the **Settings** tab in the navigation bar.
4. Enter current password (`Admin@123`), enter your new password, and click **Update Password**.

---

## 🧪 Testing Checklist

1. **Homepage**: Visit `http://127.0.0.1:5000`. Verify header, hero, offers, menu items, gallery, reviews, and footer load.
2. **Menu & Customizations**: Search for a dish or click category tabs (e.g. `Burger`, `Pizza`). Customize ingredients or check extras and click **Add To Cart**.
3. **Cart & Pricing**: Review cart item list, adjust quantities with `+` and `-`, verify subtotal, GST (5%), and total.
4. **Order**: Open `/t/3` (or scan a table QR), add dishes, tap **Send to Kitchen**. Watch the order page update when the kitchen changes the status in `/kitchen`, then pay with the UPI QR. You will be redirected to the **My Orders** page showing your order and status `Pending`.
5. **Reservations**: Fill out the Table Reservation form with date, time, and number of guests. Submit and verify confirmation in **My Bookings**.
6. **Contact Form**: Scroll to Contact Us on the homepage, submit a message, and verify the confirmation message.
7. **Registration**: Click **Register**, enter a new customer account, and verify successful redirect to Login. Attempting duplicate registration will display an error.
8. **History**: Open **History** in the menu bar, check statistics, filter orders by status, switch to Reservations, and click **Reorder**.
9. **Customer Login & Logout**: Sign in as the registered customer. Notice the greeting `👤 <Name>` and personal order history. Click **Logout**.
10. **Admin Panel Protection**: As a regular logged-in customer or guest, navigate to `http://127.0.0.1:5000/admin` — verify access is blocked and redirected to login.
11. **Admin Features**: Sign in as `admin@bitetheory.com`.
    - Check statistics cards.
    - Change order status from `Pending` to `Preparing` or `Completed`.
    - Confirm a reservation.
    - Add a new dish with an image.
    - Edit and delete dishes.
    - View contact messages.
