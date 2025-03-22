import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def get_connection(self):
        return sqlite3.connect("local_store.db")

db_manager = DatabaseManager()

@tool
def get_available_categories() -> Dict[str, List[str]]:
    """Returns available product categories."""
    logger.info("Fetching available product categories.")
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM products WHERE quantity > 0")
        categories = {"categories": [row[0] for row in cursor.fetchall()]}
        logger.info(f"Available categories: {categories}")
        return categories

# In tools.py

@tool
def search_products(
    query: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Search products with filters."""
    logger.info(f"Searching products with query: {query}, category: {category}, min_price: {min_price}, max_price: {max_price}")
    conditions = ["quantity > 0"]
    params = []

    if query:
        conditions.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ?)")
        params.extend([f"%{query.lower()}%", f"%{query.lower()}%"])
    if category:
        conditions.append("LOWER(category) = ?")
        params.append(category.lower())
    if min_price is not None:
        conditions.append("price >= ?")
        params.append(float(min_price))
    if max_price is not None:
        conditions.append("price <= ?")
        params.append(float(max_price))

    query_str = f"SELECT * FROM products WHERE {' AND '.join(conditions)}"

    with db_manager.get_connection() as conn:
        conn.row_factory = sqlite3.Row  # Add this line
        cursor = conn.cursor()
        logger.info(f"Executing query: {query_str} with params: {params}")
        cursor.execute(query_str, params)
        products = cursor.fetchall()
        result = {
            "products": [dict(row) for row in products],
            "count": len(products)
        }
        logger.info(f"Search results: {result}")
        return result

@tool
def create_order(
    products: List[Dict[str, Any]], *, config: RunnableConfig
) -> Dict[str, str]:
    """Create a new order."""
    customer_id = config.get("configurable", {}).get("customer_id")
    if not customer_id:
        logger.error("Customer ID missing")
        return {"error": "Customer ID missing"}

    with db_manager.get_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION")

            # Create order
            cursor.execute(
                "INSERT INTO orders (customer_id, order_date, status) VALUES (?, ?, ?)",
                (customer_id, datetime.now().isoformat(), "pending")
            )
            order_id = cursor.lastrowid

            total = 0.0
            ordered_items = []

            for item in products:
                cursor.execute(
                    "SELECT id, price, quantity FROM products WHERE id = ?",
                    (item["product_id"],)
                )
                product = cursor.fetchone()

                if not product:
                    raise ValueError(f"Product {item['product_id']} not found")
                if product[2] < item["quantity"]:
                    raise ValueError(f"Insufficient stock for product {product[0]}")

                # Update inventory
                cursor.execute(
                    "UPDATE products SET quantity = quantity - ? WHERE id = ?",
                    (item["quantity"], product[0])
                )

                # Add order item
                cursor.execute(
                    """INSERT INTO order_items
                    (order_id, product_id, quantity, unit_price)
                    VALUES (?, ?, ?, ?)""",
                    (order_id, product[0], item["quantity"], product[1])
                )

                total += product[1] * item["quantity"]
                ordered_items.append({
                    "product_id": product[0],
                    "quantity": item["quantity"],
                    "unit_price": product[1]
                })

            conn.commit()
            logger.info(f"Order created successfully: {order_id}")
            return {
                "order_id": order_id,
                "total": round(total, 2),
                "items": ordered_items,
                "status": "success"
            }
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating order: {str(e)}")
            return {"error": str(e), "status": "failed"}

@tool
def check_order_status(
    order_id: Union[str, None], *, config: RunnableConfig
) -> Dict[str, Union[str, None]]:
    """Check order status."""
    customer_id = config.get("configurable", {}).get("customer_id")
    logger.info(f"Checking order status for order_id: {order_id}, customer_id: {customer_id}")

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()

        if order_id:
            cursor.execute(
                """SELECT o.id, o.status, SUM(oi.quantity * oi.unit_price) as total
                FROM orders o
                JOIN order_items oi ON o.id = oi.order_id
                WHERE o.id = ? AND o.customer_id = ?
                GROUP BY o.id""",
                (order_id, customer_id)
            )
            order = cursor.fetchone()
            if not order:
                logger.error("Order not found")
                return {"error": "Order not found"}
            logger.info(f"Order status: {dict(order)}")
            return dict(order)
        else:
            cursor.execute(
                """SELECT id, order_date, status
                FROM orders
                WHERE customer_id = ?""",
                (customer_id,)
            )
            orders = {"orders": [dict(row) for row in cursor.fetchall()]}
            logger.info(f"Orders for customer: {orders}")
            return orders

@tool
def search_products_recommendations(config: RunnableConfig) -> Dict[str, Any]:
    """Get personalized recommendations."""
    customer_id = config.get("configurable", {}).get("customer_id")
    logger.info(f"Fetching recommendations for customer_id: {customer_id}")

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()

        # Get customer's frequent categories
        cursor.execute(
            """SELECT category, COUNT(*) as count
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.customer_id = ?
            GROUP BY category
            ORDER BY count DESC
            LIMIT 3""",
            (customer_id,)
        )
        categories = [row[0] for row in cursor.fetchall()]

        if not categories:
            # Get popular products
            cursor.execute(
                """SELECT p.*
                FROM products p
                JOIN order_items oi ON p.id = oi.product_id
                GROUP BY p.id
                ORDER BY SUM(oi.quantity) DESC
                LIMIT 5"""
            )
        else:
            cursor.execute(
                f"""SELECT * FROM products
                WHERE category IN ({','.join(['?']*len(categories))})
                AND quantity > 0
                ORDER BY RANDOM()
                LIMIT 5""",
                categories
            )

        recommendations = {"recommendations": [dict(row) for row in cursor.fetchall()]}
        logger.info(f"Recommendations: {recommendations}")
        return recommendations
