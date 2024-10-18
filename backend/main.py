import json
from pathlib import Path
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Response, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

# Mount static files for CSS and images
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Set up templates
templates = Jinja2Templates(directory="frontend/templates")

# File path for product storage
PRODUCT_FILE = Path("data/products.json")

# Helper functions to load and save data
def load_products():
    if PRODUCT_FILE.exists():
        with open(PRODUCT_FILE, "r") as f:
            return json.load(f)
    return []

def save_products(data):
    with open(PRODUCT_FILE, "w") as f:
        json.dump(data, f, indent=4)

# In-memory user storage for demo purposes
users = [{"username": "keshav", "password": "password123"}]
products = load_products()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, search: str = Query("", min_length=0)):
    username = request.cookies.get("username")
    # Filter products by the search term if provided
    filtered_products = [product for product in products if search.lower() in product["name"].lower()]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "products": filtered_products,
        "username": username,
        "search": search
    })

@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register_user(username: str = Form(...), password: str = Form(...)):
    users.append({"username": username, "password": password})
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
async def logout(request: Request):
    username = request.cookies.get("username")
    response = templates.TemplateResponse("logout.html", {"request": request, "username": username})
    response.delete_cookie("username")
    return response

@app.get("/add-product", response_class=HTMLResponse)
async def add_product_form(request: Request):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("add_product.html", {"request": request, "username": username})

@app.post("/add-product")
async def add_product(request: Request, name: str = Form(...), price: float = Form(...), image: str = Form(...)):
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
    save_products(products)
    return RedirectResponse("/", status_code=303)
