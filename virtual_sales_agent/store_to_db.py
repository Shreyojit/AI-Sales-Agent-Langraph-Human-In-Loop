import sqlite3

# Define the SQL schema and sample data
sql_schema = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    order_date TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- Sample Data
INSERT INTO products (name, category, description, price, quantity)
VALUES
    ('Laptop', 'Electronics', 'High-performance laptop', 999.99, 10),
    ('Smartphone', 'Electronics', 'Latest model smartphone', 699.99, 15),
    ('Desk Chair', 'Furniture', 'Ergonomic office chair', 249.99, 5);
    ('Wireless Headphones', 'Electronics', 'Noise-cancelling headphones', 199.99, 8),
    ('Office Desk', 'Furniture', 'Large wooden desk', 399.99, 3),
    ('Mechanical Keyboard', 'Electronics', 'RGB gaming keyboard', 129.99, 12);
"""

# Connect to the SQLite database (or create it if it doesn't exist)
conn = sqlite3.connect('local_store.db')
cursor = conn.cursor()

# Execute the SQL schema and sample data
cursor.executescript(sql_schema)
conn.commit()

# Verify the tables and data
def verify_tables_and_data():
    # Verify products table
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()
    print("Products Table:")
    for product in products:
        print(product)

    # Verify orders table
    cursor.execute("SELECT * FROM orders")
    orders = cursor.fetchall()
    print("\nOrders Table:")
    for order in orders:
        print(order)

    # Verify order_items table
    cursor.execute("SELECT * FROM order_items")
    order_items = cursor.fetchall()
    print("\nOrder Items Table:")
    for item in order_items:
        print(item)

# Call the verification function
verify_tables_and_data()

# Close the connection
conn.close()
