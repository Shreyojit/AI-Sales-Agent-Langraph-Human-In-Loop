import sqlite3

DB_NAME = "pizza_orders.db"

def setup_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS food_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            food_item_id INTEGER,
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivery_address TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (food_item_id) REFERENCES food_items(id)
        )
    """)

    # Insert menu items
    menu_items = [
        ("Margherita Pizza", 8.99, "Pizza"),
        ("Pepperoni Pizza", 10.99, "Pizza"),
        ("BBQ Chicken Pizza", 12.49, "Pizza"),
        ("Cheese Garlic Bread", 5.99, "Sides"),
        ("Coca-Cola", 1.99, "Drinks"),
    ]
    
    cursor.executemany("INSERT OR IGNORE INTO food_items (name, price, category) VALUES (?, ?, ?)", menu_items)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    setup_database()
    print("✅ Database initialized with menu items!")
