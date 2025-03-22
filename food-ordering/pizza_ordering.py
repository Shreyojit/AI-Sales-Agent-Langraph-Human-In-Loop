from dotenv import load_dotenv
load_dotenv()

import sqlite3
from typing import TypedDict, List
from datetime import datetime, timedelta
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END

def initialize_database():
    """Initialize database with tables and sample data"""
    conn = sqlite3.connect('local_orders.db')
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS food_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        food_item_id INTEGER,
        order_date TEXT,
        delivery_address TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(food_item_id) REFERENCES food_items(id)
    )''')

    cursor.executemany(
        'INSERT OR IGNORE INTO food_items (name, price) VALUES (?, ?)',
        [('Margherita Pizza', 12.99),
         ('Pepperoni Pizza', 14.99),
         ('Vegetarian Pizza', 13.99)]
    )

    cursor.executemany(
        'INSERT OR IGNORE INTO customers (name) VALUES (?)',
        [('John Doe',), ('Jane Smith',)]
    )

    conn.commit()
    conn.close()

llm = ChatOllama(
    model="llama3.2:latest",
    temperature=0.3,
    base_url="http://localhost:11434",
    num_gpu=1
)

class AgentState(TypedDict):
    messages: List[dict]
    customer_name: str
    tool_calls: List[dict]
    order_check: dict
    generation: str
    question: str

@tool
def create_order(customer_name: str, food_items: list, delivery_address: str, order_date: str):
    """Create new order in database"""
    conn = sqlite3.connect('local_orders.db')
    cursor = conn.cursor()
    try:
        def clean_food_name(food_name):
            size_terms = ['large', 'medium', 'small', 'extra', 'xl', 'lg', 'md', 'sm']
            parts = food_name.lower().split()
            cleaned = [part for part in parts if part not in size_terms]
            return ' '.join(cleaned).strip()

        cursor.execute("INSERT OR IGNORE INTO customers (name) VALUES (?)", (customer_name,))
        cursor.execute("SELECT id FROM customers WHERE name = ?", (customer_name,))
        customer_id = cursor.fetchone()[0]

        order_datetime = datetime.strptime(order_date, "%Y-%m-%d %H:%M").isoformat()

        for food_name in food_items:
            cleaned_name = clean_food_name(food_name)
            cursor.execute("SELECT id FROM food_items WHERE LOWER(name) LIKE ?", 
                          ('%' + cleaned_name + '%',))
            food_item = cursor.fetchone()
            if not food_item:
                return f"Food item {food_name} not found"

            cursor.execute('''
                INSERT INTO orders (customer_id, food_item_id, order_date, delivery_address)
                VALUES (?, ?, ?, ?)
            ''', (customer_id, food_item[0], order_datetime, delivery_address))

        conn.commit()
        return f"Order created for {customer_name}: {', '.join(food_items)}"
    except Exception as e:
        conn.rollback()
        return f"Error: {str(e)}"
    finally:
        conn.close()

@tool
def get_all_orders(customer_name: str):
    """Retrieve customer's order history"""
    conn = sqlite3.connect('local_orders.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT o.order_date, f.name, o.delivery_address
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
            JOIN food_items f ON o.food_item_id = f.id
            WHERE c.name = ?
        ''', (customer_name,))

        orders = cursor.fetchall()
        return "\n".join([f"{date}: {item} to {addr}" for date, item, addr in orders]) if orders else "No orders found"
    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        conn.close()

system_prompt = """You are a helpful pizza ordering assistant. Follow these rules:
1. Always use the customer's name
2. Verify these elements are present:
   - Food items
   - Delivery address (full address with street number)
   - Order time (in HH:MM AM/PM format)
3. Use tools for database operations
4. Confirm order details before finalizing

Current customer: {customer_name}
Current time: {current_time}"""

order_check_prompt = """Analyze this order request:
{question}

Check for:
- At least one food item (Yes/No)
- Complete delivery address (Yes/No)
- Specific time in HH:MM format (Yes/No)
Respond ONLY as: food:X,address:X,time:X"""

def create_prompt_chain():
    return (
        ChatPromptTemplate.from_template(system_prompt)
        .partial(current_time=datetime.now().strftime("%Y-%m-%d %H:%M"))
        | llm
        | StrOutputParser()
    )

order_check_chain = (
    ChatPromptTemplate.from_template(order_check_prompt)
    | llm
    | StrOutputParser()
)

def identify_intent(state: AgentState):
    messages = [HumanMessage(content=state["question"])]
    response = llm.bind_tools([create_order, get_all_orders]).invoke(messages)

    for tool_call in response.tool_calls:
        if tool_call["name"] == "create_order":
            args = tool_call["args"]
            time_str = args.get("order_date", "").strip()
            
            try:
                if not time_str:
                    raise ValueError("No time provided")
                
                parsed_time = datetime.strptime(time_str, "%I:%M %p") if ":" in time_str else datetime.strptime(time_str, "%I%p")
                order_datetime = datetime.now().replace(
                    hour=parsed_time.hour,
                    minute=parsed_time.minute,
                    second=0,
                    microsecond=0
                )
                
                if order_datetime < datetime.now():
                    order_datetime += timedelta(days=1)
                
                tool_call["args"]["order_date"] = order_datetime.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                return {"messages": [ToolMessage(
                    content="Invalid time format. Please use 'HH:MM AM/PM' format.",
                    tool_call_id=tool_call["id"]
                )]}
            
            tool_call["args"]["customer_name"] = state["customer_name"]

    return {"tool_calls": response.tool_calls}

def validate_order(state: AgentState):
    result = order_check_chain.invoke({"question": state["question"]})
    checks = dict([item.split(":") for item in result.split(",")])
    return {"order_check": checks}

def execute_tools(state: AgentState):
    tool_responses = []
    for tool_call in state["tool_calls"]:
        tool = {"create_order": create_order, "get_all_orders": get_all_orders}[tool_call["name"]]
        result = tool.invoke(tool_call["args"])
        tool_responses.append(ToolMessage(
            content=str(result),
            tool_call_id=tool_call["id"]
        ))
    return {"messages": tool_responses}

def generate_response(state: AgentState):
    prompt_chain = create_prompt_chain()
    response = prompt_chain.invoke({
        "customer_name": state["customer_name"],
        "messages": state["messages"]
    })
    return {"generation": response}

workflow = StateGraph(AgentState)

workflow.add_node("identify_intent", identify_intent)
workflow.add_node("validate_order", validate_order)
workflow.add_node("execute_tools", execute_tools)
workflow.add_node("generate_response", generate_response)

workflow.set_entry_point("identify_intent")
workflow.add_edge("identify_intent", "validate_order")
workflow.add_conditional_edges(
    "validate_order",
    lambda state: "complete" if all(v == "Yes" for v in state["order_check"].values()) else "incomplete",
    {
        "complete": "execute_tools",
        "incomplete": "generate_response"
    }
)
workflow.add_edge("execute_tools", "generate_response")
workflow.add_edge("generate_response", END)

app = workflow.compile()

def collect_order_details():
    print("🍕 Welcome to PizzaBot! 🍕")
    customer_name = input("Please enter your name: ").strip()
    
    while True:
        print("\nPlease enter your order details (e.g.: '2 large pepperoni pizzas to 123 Main St at 7:30 PM')")
        order_input = input("Your order: ").strip()
        
        state = {
            "question": order_input,
            "customer_name": customer_name,
            "messages": [],
            "tool_calls": [],
            "order_check": {},
            "generation": ""
        }
        
        result = app.invoke(state)
        
        if any("thank you" in msg.lower() for msg in result.values() if isinstance(msg, str)):
            print("\n" + "="*40)
            print(f"Thank you for your order, {customer_name}!")
            print("Your pizza is on its way! 🚀")
            print("="*40)
            break
            
        if result.get("generation"):
            print("\nAssistant:", result["generation"])

if __name__ == "__main__":
    initialize_database()
    collect_order_details()