import json
from pathlib import Path
from fastapi import FastAPI, Request, Form, HTTPException, Response, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

app = FastAPI()

# Get the root directory dynamically
ROOT_DIR = Path(__file__).parent.parent

# Define paths to static, template, product, user, and cart folders
STATIC_DIR = ROOT_DIR / "frontend" / "static"
TEMPLATE_DIR = ROOT_DIR / "frontend" / "templates"
PRODUCT_FILE = ROOT_DIR / "data" / "products.json"
USER_FILE = ROOT_DIR / "data" / "users.json"
CART_FILE = ROOT_DIR / "data" / "cart.json"

# Check if static and templates directories exist
if not STATIC_DIR.exists():
    raise RuntimeError(f"Directory '{STATIC_DIR}' does not exist. Please create this directory to proceed.")

if not TEMPLATE_DIR.exists():
    raise RuntimeError(f"Template directory '{TEMPLATE_DIR}' does not exist. Please create this directory to proceed.")

# Mount static files for CSS and images
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Set up templates
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Helper functions to load and save data
def load_json(file_path):
    if file_path.exists():
        with open(file_path, "r") as f:
            return json.load(f)
    return []

def save_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

products = load_json(PRODUCT_FILE)
users = load_json(USER_FILE)

# Initialize empty cart if not present
if not CART_FILE.exists():
    save_json(CART_FILE, {})

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, search: str = Query("", min_length=0)):
    username = request.cookies.get("username")
    cart = load_json(CART_FILE).get(username, []) if username else []
    filtered_products = [product for product in products if search.lower() in product["name"].lower()]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "products": filtered_products,
        "username": username,
        "search": search,
        "cart_count": len(cart),
    })

@app.post("/add-to-cart")
async def add_to_cart(request: Request, product_id: int = Form(...)):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    cart_data = load_json(CART_FILE)  # Load existing cart data
    cart = cart_data.get(username, [])

    # Find the product by ID
    product = next((p for p in products if p["id"] == product_id), None)
    if product:
        cart.append(product)
        cart_data[username] = cart
        save_json(CART_FILE, cart_data)  # Save updated cart to file

    return RedirectResponse("/", status_code=303)

@app.get("/cart", response_class=HTMLResponse)
async def view_cart(request: Request):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    cart_data = load_json(CART_FILE)
    cart = cart_data.get(username, [])

    return templates.TemplateResponse("cart.html", {
        "request": request,
        "cart_items": cart,
        "username": username
    })

@app.post("/remove-from-cart")
async def remove_from_cart(request: Request, product_id: int = Form(...)):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    cart_data = load_json(CART_FILE)
    cart = cart_data.get(username, [])

    # Remove product by ID
    cart = [item for item in cart if item["id"] != product_id]
    cart_data[username] = cart
    save_json(CART_FILE, cart_data)

    return RedirectResponse("/cart", status_code=303)

@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register_user(username: str = Form(...), password: str = Form(...)):
    if any(user["username"] == username for user in users):
        raise HTTPException(status_code=400, detail="Username already exists.")
    users.append({"username": username, "password": password})
    save_json(USER_FILE, users)
    return RedirectResponse("/", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(response: Response, username: str = Form(...), password: str = Form(...)):
    for user in users:
        if user["username"] == username and user["password"] == password:
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(key="username", value=username)
            return response
    raise HTTPException(status_code=400, detail="Invalid username or password")

@app.get("/logout", response_class=HTMLResponse)
async def logout(response: Response):
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("username")
    return response

@app.get("/add-product", response_class=HTMLResponse)
async def add_product_form(request: Request):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("add_product.html", {"request": request, "username": username})

@app.post("/add-product")
async def add_product(name: str = Form(...), price: float = Form(...), image: str = Form(...), request: Request = None):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)
    new_product = {
        "id": len(products) + 1,
        "name": name,
        "price": price,
        "image": image
    }
    products.append(new_product)
    save_json(PRODUCT_FILE, products)
    return RedirectResponse("/", status_code=303)
