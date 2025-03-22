import sqlite3
import ollama
from langchain.tools import Tool
from langchain_community.llms import Ollama
from langchain.agents import initialize_agent, AgentType
from langchain.memory import ConversationBufferMemory
from langgraph.graph import StateGraph, END

# Load Ollama Model
llm = Ollama(model="llama3:latest")

# Connect to SQLite
DB_NAME = "local_orders.db"

def get_menu():
    """Fetch the full menu from the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, category FROM food_items ORDER BY category, name")
    menu = cursor.fetchall()
    conn.close()
    
    menu_str = "\n".join([f"{name} - ${price:.2f} ({category})" for name, price, category in menu])
    return f"Here is the menu:\n{menu_str}"

def get_top_selling():
    """Fetch top-selling items."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.name, COUNT(o.food_item_id) as sales
        FROM orders o 
        JOIN food_items f ON o.food_item_id = f.id 
        GROUP BY f.name 
        ORDER BY sales DESC 
        LIMIT 3
    """)
    top_items = cursor.fetchall()
    conn.close()
    
    if not top_items:
        return "No top-selling items yet."
    
    return "\n".join([f"{name} - Ordered {sales} times" for name, sales in top_items])

def create_order_tool(order_details):
    """Create a new order in the database based on details."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    customer_name = order_details.get("customer_name", "Unknown")
    food_items = order_details.get("food_items", [])
    delivery_address = order_details.get("delivery_address", "Unknown")
    
    # Get or create customer
    cursor.execute("INSERT OR IGNORE INTO customers (name) VALUES (?)", (customer_name,))
    cursor.execute("SELECT id FROM customers WHERE name = ?", (customer_name,))
    customer_id = cursor.fetchone()[0]
    
    # Insert order details
    for food_id in food_items:
        cursor.execute("""
            INSERT INTO orders (customer_id, food_item_id, order_date, delivery_address)
            VALUES (?, ?, datetime('now'), ?)
        """, (customer_id, food_id, delivery_address))
    
    conn.commit()
    conn.close()
    
    return f"Order placed successfully for {customer_name} at {delivery_address}."

# Define Tools
menu_tool = Tool(name="MenuTool", func=get_menu, description="Gets the full menu")
top_selling_tool = Tool(name="TopSellingTool", func=get_top_selling, description="Gets the top-selling food items")
order_tool = Tool(name="OrderTool", func=create_order_tool, description="Places an order")

