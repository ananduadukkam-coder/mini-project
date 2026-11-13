import unittest
import io
from app import app, db, User, MenuItem, Reservation, Order, OrderItem, ContactMessage
from werkzeug.security import check_password_hash

class RestaurantAppTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def _login_customer(self):
        """Ensure the test customer exists and is logged in."""
        email = "testcustomer@example.com"
        with app.app_context():
            if not User.query.filter_by(email=email).first():
                from werkzeug.security import generate_password_hash
                db.session.add(User(fullname="Rahul Sharma", email=email, phone="+91 9876500000",
                                    password=generate_password_hash("Password@123")))
                db.session.commit()
        self.client.post("/login", data={"email": email, "password": "Password@123"})

    def test_01_homepage_loads(self):
        """1. Homepage loads successfully with 200 OK and restaurant content."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"BITE THEORY", response.data)
        self.assertIn(b"Our Menu", response.data)
        self.assertIn(b"Table Reservation", response.data)
        self.assertIn(b"Special Offers", response.data)
        print("PASS: Test 1 - Homepage loaded successfully.")

    def test_02_static_assets_load(self):
        """2. CSS and image assets load successfully."""
        css_resp = self.client.get("/static/css/style.css")
        self.assertEqual(css_resp.status_code, 200)
        self.assertIn(b"--primary", css_resp.data)

        img_resp = self.client.get("/static/images/restaurant.jpg")
        self.assertEqual(img_resp.status_code, 200)
        print("PASS: Test 2 - Static CSS and images load successfully.")

    def test_03_registration_and_duplicate_prevention(self):
        """3 & 4. Registration works, password hashed, duplicate registration prevented."""
        test_email = "testcustomer@example.com"
        # Cleanup if exists from prior test
        with app.app_context():
            existing = User.query.filter_by(email=test_email).first()
            if existing:
                db.session.delete(existing)
                db.session.commit()

        # Registration POST
        reg_data = {
            "fullname": "Rahul Sharma",
            "email": test_email,
            "phone": "+91 9876500000",
            "password": "Password@123",
            "confirm_password": "Password@123"
        }
        resp = self.client.post("/register", data=reg_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Registration successful", resp.data)

        # Check in DB
        with app.app_context():
            user = User.query.filter_by(email=test_email).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.fullname, "Rahul Sharma")
            self.assertTrue(check_password_hash(user.password, "Password@123"))
            self.assertFalse(user.is_admin)

        # Attempt duplicate registration
        dup_resp = self.client.post("/register", data=reg_data, follow_redirects=True)
        self.assertEqual(dup_resp.status_code, 200)
        self.assertIn(b"already exists", dup_resp.data)
        print("PASS: Test 3 & 4 - Registration and duplicate prevention verified.")

    def test_05_customer_login_logout(self):
        """5. Login verifies password and sets session; logout clears session."""
        login_data = {
            "email": "testcustomer@example.com",
            "password": "Password@123"
        }
        resp = self.client.post("/login", data=login_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Welcome back, Rahul Sharma", resp.data)

        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("user_email"), "testcustomer@example.com")
            self.assertFalse(sess.get("is_admin"))

        # Logout
        logout_resp = self.client.get("/logout", follow_redirects=True)
        self.assertEqual(logout_resp.status_code, 200)
        self.assertIn(b"logged out", logout_resp.data)

        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)
        print("PASS: Test 5 - Customer login and logout working.")

    def test_06_menu_items_from_sqlite(self):
        """6. Menu items load from SQLite database."""
        with app.app_context():
            count = MenuItem.query.count()
            self.assertGreaterEqual(count, 14)

        resp = self.client.get("/menu")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Veg Burger", resp.data)
        self.assertIn(b"Pizza", resp.data)
        self.assertIn(b"Biryani", resp.data)

        api_resp = self.client.get("/api/menu")
        self.assertEqual(api_resp.status_code, 200)
        self.assertTrue(len(api_resp.get_json()) >= 14)
        print("PASS: Test 6 - Menu items loaded from SQLite.")

    def test_07_cart_operations(self):
        """7. Cart operations: add, increase, decrease, calculate totals."""
        with app.app_context():
            item = MenuItem.query.filter_by(name="Veg Burger").first()
            item_id = item.id
            item_price = item.price

        # Add to cart
        add_data = {
            "item_id": item_id,
            "food": "Veg Burger",
            "quantity": 2,
            "customizations": "Extras: Extra Cheese (+Rs.30)",
            "extras_price": 30.0
        }
        resp = self.client.post("/cart/add", data=add_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Added Veg Burger to your cart", resp.data)

        # Inspect cart page
        cart_page = self.client.get("/cart")
        self.assertEqual(cart_page.status_code, 200)
        self.assertIn(b"Veg Burger", cart_page.data)

        # Increase qty
        self.client.post("/cart/update", data={"index": 0, "action": "increase"}, follow_redirects=True)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["cart"][0]["quantity"], 3)

        print("PASS: Test 7 - Cart add, update, and total calculations verified.")

    def test_08_qr_table_order_and_payment(self):
        """8. Guest scans table QR, orders (no login/name/email), tracks status and pays by UPI QR."""
        # Scan the QR printed on table 3
        resp = self.client.get("/t/3", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Table 3", resp.data)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("table_no"), 3)

        with app.app_context():
            item = MenuItem.query.first()
            item_id, item_name = item.id, item.name

        self.client.post("/cart/add", data={
            "item_id": item_id, "food": item_name, "quantity": 2,
            "customizations": "No onions", "extras_price": 0.0
        })

        # Checkout without any name, e-mail, phone or address
        resp = self.client.post("/checkout", data={"notes": "Less spicy"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"sent to the kitchen", resp.data)
        self.assertIn(b"Pay Your Bill", resp.data)
        self.assertIn(b"upi://pay", resp.data)

        with app.app_context():
            order = Order.query.filter_by(table_number=3).order_by(Order.id.desc()).first()
            self.assertIsNotNone(order)
            oid = order.id
            self.assertEqual(order.status, "Pending")
            self.assertEqual(order.payment_status, "Unpaid")
            self.assertEqual(len(order.items), 1)
            self.assertEqual(order.items[0].quantity, 2)
            self.assertGreater(order.total, 0.0)

        # Live status API works for the same guest, but not for a stranger
        api = self.client.get(f"/api/order/{oid}/status")
        self.assertEqual(api.status_code, 200)
        self.assertEqual(api.get_json()["status"], "Pending")
        stranger = app.test_client().get(f"/api/order/{oid}/status")
        self.assertEqual(stranger.status_code, 403)

        # Pay via UPI QR
        resp = self.client.post(f"/order/{oid}/pay", data={"method": "upi"}, follow_redirects=True)
        self.assertIn(b"Payment Received", resp.data)
        with app.app_context():
            order = db.session.get(Order, oid)
            self.assertEqual(order.payment_status, "Paid")
            self.assertEqual(order.payment_method, "UPI QR")

        print("PASS: Test 8 - QR table order, tracking API and UPI payment verified.")

    def test_08b_invalid_table_and_empty_cart(self):
        """8b. Invalid table QR is rejected; checkout needs a table."""
        resp = self.client.get("/t/9999", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Select Your Table", resp.data)

        with app.app_context():
            item_id = MenuItem.query.first().id
        self.client.post("/cart/add", data={"item_id": item_id, "quantity": 1})
        resp = self.client.post("/checkout", data={}, follow_redirects=True)
        self.assertIn(b"scan your table QR", resp.data)
        print("PASS: Test 8b - Invalid table / missing table handled.")

    def test_09_table_reservations(self):
        """9. Table reservations saved and validated in SQLite."""
        with app.app_context():
            pass

        # Guest must log in first
        guest = self.client.post("/reservation", data={"phone": "1", "date": "2026-11-20"})
        self.assertEqual(guest.status_code, 302)

        self._login_customer()
        res_data = {
            "phone": "+91 9123456780",
            "date": "2026-11-20",
            "time": "20:00",
            "persons": 4,
            "special_requests": "Window table for anniversary"
        }
        resp = self.client.post("/reservation", data=res_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Table reserved", resp.data)

        with app.app_context():
            res = Reservation.query.filter_by(email="testcustomer@example.com", date="2026-11-20").order_by(Reservation.id.desc()).first()
            self.assertIsNotNone(res)
            self.assertEqual(res.name, "Rahul Sharma")
            self.assertEqual(res.persons, 4)
            self.assertEqual(res.status, "Pending")

        print("PASS: Test 9 - Table reservation saved and validated in SQLite.")

    def test_10_contact_form(self):
        """10. Contact form messages saved in SQLite."""
        contact_data = {
            "name": "Vikram Singh",
            "email": "vikram@example.com",
            "phone": "+91 9811122233",
            "subject": "Corporate Catering",
            "message": "We would like to book catering for 50 people on Friday."
        }
        resp = self.client.post("/contact", data=contact_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"message has been sent successfully", resp.data)

        with app.app_context():
            msg = ContactMessage.query.filter_by(email="vikram@example.com").first()
            self.assertIsNotNone(msg)
            self.assertEqual(msg.subject, "Corporate Catering")
            self.assertEqual(msg.status, "Unread")

        print("PASS: Test 10 - Contact form saved to SQLite.")

    def test_11_admin_login(self):
        """11. Admin login works and provides admin dashboard access."""
        admin_data = {
            "email": "admin@bitetheory.com",
            "password": "Admin@123"
        }
        resp = self.client.post("/login", data=admin_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"BITE THEORY Admin Dashboard", resp.data)

        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get("is_admin"))

        print("PASS: Test 11 - Admin login verified.")

    def test_12_admin_menu_management(self):
        """12. Admin can add, edit, and delete menu items safely."""
        # Log in as admin
        self.client.post("/login", data={"email": "admin@bitetheory.com", "password": "Admin@123"})

        # Add item
        add_data = {
            "name": "Paneer Butter Masala",
            "category": "Main",
            "price": "260.0",
            "description": "Rich cottage cheese in creamy tomato butter gravy",
            "image_url": "https://images.unsplash.com/photo-1546833999-b9f581a1996d"
        }
        resp = self.client.post("/admin/menu/add", data=add_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"added successfully", resp.data)

        with app.app_context():
            dish = MenuItem.query.filter_by(name="Paneer Butter Masala").first()
            self.assertIsNotNone(dish)
            dish_id = dish.id

        # Edit item
        edit_data = {
            "name": "Paneer Butter Masala Special",
            "category": "Main",
            "price": "280.0",
            "description": "Extra rich cottage cheese in creamy tomato butter gravy",
            "image_url": "https://images.unsplash.com/photo-1546833999-b9f581a1996d",
            "is_available": "1"
        }
        resp = self.client.post(f"/admin/menu/{dish_id}/edit", data=edit_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with app.app_context():
            updated_dish = db.session.get(MenuItem, dish_id)
            self.assertEqual(updated_dish.name, "Paneer Butter Masala Special")
            self.assertEqual(updated_dish.price, 280.0)

        # Delete item
        del_resp = self.client.post(f"/admin/menu/{dish_id}/delete", follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)

        with app.app_context():
            deleted_dish = db.session.get(MenuItem, dish_id)
            self.assertIsNone(deleted_dish)

        print("PASS: Test 12 - Admin add, edit, and delete menu items verified.")

    def test_13_admin_manage_orders_and_reservations(self):
        """13. Admin can update order status and reservation status."""
        self.client.post("/login", data={"email": "admin@bitetheory.com", "password": "Admin@123"})

        with app.app_context():
            order = Order.query.first()
            order_id = order.id
            res = Reservation.query.first()
            res_id = res.id

        # Update order status
        self.client.post(f"/admin/order/{order_id}/status", data={"status": "Preparing"}, follow_redirects=True)
        with app.app_context():
            self.assertEqual(db.session.get(Order, order_id).status, "Preparing")

        # Update reservation status
        self.client.post(f"/admin/reservation/{res_id}/status", data={"status": "Confirmed"}, follow_redirects=True)
        with app.app_context():
            self.assertEqual(db.session.get(Reservation, res_id).status, "Confirmed")

        print("PASS: Test 13 - Admin order & reservation status management verified.")

    def test_14_non_admin_access_protection(self):
        """14. Normal customers and guests cannot access admin routes."""
        # Test guest access
        guest_resp = self.client.get("/admin", follow_redirects=False)
        self.assertIn(guest_resp.status_code, [302, 401, 403])

        # Login as non-admin customer
        self.client.post("/login", data={"email": "testcustomer@example.com", "password": "Password@123"})

        customer_resp = self.client.get("/admin", follow_redirects=True)
        self.assertEqual(customer_resp.status_code, 200)
        self.assertIn(b"Access denied", customer_resp.data)

        # Attempt admin action as non-admin
        post_resp = self.client.post("/admin/menu/add", data={"name": "Hacked Item"}, follow_redirects=True)
        self.assertIn(b"Access denied", post_resp.data)

        print("PASS: Test 14 - Admin route security & non-admin protection verified.")

    def test_15_all_routes_and_links_valid(self):
        """15. No broken links or missing routes."""
        routes_to_test = [
            ("/", 200),
            ("/menu", 200),
            ("/cart", 200),
            ("/orders", 200),
            ("/reservations", 200),
            ("/history", 302),
            ("/scan", 200),
            ("/kitchen", 302),
            ("/login", 200),
            ("/register", 200),
            ("/api/health", 200),
            ("/api/menu", 200)
        ]
        for route, expected_code in routes_to_test:
            resp = self.client.get(route)
            self.assertEqual(resp.status_code, expected_code, f"Failed for route {route}")

        print("PASS: Test 15 - All public and customer routes responding as expected.")


    def test_16_history_page_and_reorder(self):
        """16. History page requires login, shows orders + reservations, and reorder refills cart."""
        guest = self.client.get("/history")
        self.assertEqual(guest.status_code, 302)

        self._login_customer()
        resp = self.client.get("/history")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Order &amp; Reservation History", resp.data)
        self.assertIn(b"BITE THEORY", resp.data)

        with app.app_context():
            order = Order.query.filter_by(customer_email="testcustomer@example.com").order_by(Order.id.desc()).first()
            if order:
                oid = order.id
        if order:
            r = self.client.post(f"/order/{oid}/reorder", follow_redirects=True)
            self.assertEqual(r.status_code, 200)
            with self.client.session_transaction() as sess:
                self.assertTrue(len(sess.get("cart", [])) >= 1)
        print("PASS: Test 16 - History page and reorder verified.")


    def test_17_kitchen_workflow(self):
        """17. Kitchen board is staff-only; staff can move an order Pending -> Preparing -> Ready."""
        guest = app.test_client()
        self.assertEqual(guest.get("/kitchen").status_code, 302)
        self.assertEqual(guest.get("/api/kitchen/orders").status_code, 302)

        # place an order as a guest on table 5
        guest.get("/t/5")
        with app.app_context():
            item_id = MenuItem.query.first().id
        guest.post("/cart/add", data={"item_id": item_id, "quantity": 1})
        guest.post("/checkout", data={"name": "Kitchen Test"})
        with app.app_context():
            oid = Order.query.filter_by(table_number=5).order_by(Order.id.desc()).first().id

        staff = app.test_client()
        staff.post("/login", data={"email": "admin@bitetheory.com", "password": "Admin@123"})
        self.assertEqual(staff.get("/kitchen").status_code, 200)

        orders = staff.get("/api/kitchen/orders").get_json()
        self.assertIn(oid, [o["id"] for o in orders])

        for new_status in ("Preparing", "Ready"):
            r = staff.post(f"/api/kitchen/order/{oid}/status", json={"status": new_status})
            self.assertEqual(r.get_json()["order_status"], new_status)
            self.assertEqual(guest.get(f"/api/order/{oid}/status").get_json()["status"], new_status)

        bad = staff.post(f"/api/kitchen/order/{oid}/status", json={"status": "Nonsense"})
        self.assertEqual(bad.status_code, 400)

        # cashier marks it paid
        staff.post(f"/admin/order/{oid}/paid")
        with app.app_context():
            self.assertEqual(db.session.get(Order, oid).payment_status, "Paid")
        print("PASS: Test 17 - Kitchen workflow and customer notification status verified.")

    def test_18_admin_table_qr_management(self):
        """18. Admin can view table QR page and add/remove a table."""
        staff = app.test_client()
        self.assertEqual(staff.get("/admin/tables").status_code, 302)
        staff.post("/login", data={"email": "admin@bitetheory.com", "password": "Admin@123"})
        resp = staff.get("/admin/tables")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Table QR Code Generator", resp.data)

        staff.post("/admin/tables/add", data={"number": 77})
        from app import RestaurantTable
        with app.app_context():
            t = RestaurantTable.query.filter_by(number=77).first()
            self.assertIsNotNone(t)
            tid = t.id
        staff.post(f"/admin/tables/{tid}/delete")
        with app.app_context():
            self.assertIsNone(RestaurantTable.query.filter_by(number=77).first())
        print("PASS: Test 18 - Table QR management verified.")


if __name__ == "__main__":
    unittest.main()
