import json
from pathlib import Path
from fastapi import FastAPI, Request, Form, HTTPException, Response, Query, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import shutil
import os

app = FastAPI()

# Get the root directory dynamically
ROOT_DIR = Path(__file__).parent.parent

# Define paths to static and template folders
STATIC_DIR = ROOT_DIR / "frontend" / "static"
TEMPLATE_DIR = ROOT_DIR / "frontend" / "templates"

# Check if static and templates directories exist
if not STATIC_DIR.exists():
    raise RuntimeError(f"Directory '{STATIC_DIR}' does not exist. Please create this directory to proceed.")

if not TEMPLATE_DIR.exists():
    raise RuntimeError(f"Template directory '{TEMPLATE_DIR}' does not exist. Please create this directory to proceed.")

# Mount static files for CSS and images
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Set up templates
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# File paths for product storage, user data, and carts
PRODUCT_FILE = ROOT_DIR / "data" / "products.json"
USER_FILE = ROOT_DIR / "data" / "users.json"
CART_FILE = ROOT_DIR / "data" / "carts.json"


# Helper functions to load and save data
def load_products():
    if PRODUCT_FILE.exists():
        with open(PRODUCT_FILE, "r") as f:
            return json.load(f)
    return []


def save_products(data):
    with open(PRODUCT_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_users():
    if USER_FILE.exists():
        with open(USER_FILE, "r") as f:
            return json.load(f)
    return []


def save_users(data):
    with open(USER_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_carts():
    if CART_FILE.exists():
        with open(CART_FILE, "r") as f:
            return json.load(f)
    return {}


def save_carts(data):
    with open(CART_FILE, "w") as f:
        json.dump(data, f, indent=4)


products = load_products()
users = load_users()
carts = load_carts()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, search: str = Query("", min_length=0)):
    username = request.cookies.get("username")
    cart_count = len(carts.get(username, [])) if username else 0
    # Filter products by the search term if provided
    filtered_products = [product for product in products if search.lower() in product["name"].lower()]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "products": filtered_products,
        "username": username,
        "search": search,
        "cart_count": cart_count
    })


@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
async def register_user(username: str = Form(...), password: str = Form(...), email: str = Form(...)):
    # Validate that the email is from the University of Toronto
    if not email.endswith("@mail.utoronto.ca"):
        raise HTTPException(status_code=400, detail="Only University of Toronto email addresses are allowed.")

    # Check if the username or email already exists
    if any(user["username"] == username for user in users):
        raise HTTPException(status_code=400, detail="Username already exists.")
    if any(user.get("email") == email for user in users):
        raise HTTPException(status_code=400, detail="Email already registered.")

    # Register the user
    users.append({
        "username": username,
        "password": password,  # Note: Passwords should be hashed for security reasons
        "email": email
    })
    save_users(users)

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
async def add_product(
        name: str = Form(...),
        price: float = Form(...),
        image_file: UploadFile = File(...),
        request: Request = None
):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    # Handle Image File Upload
    upload_dir = STATIC_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)  # Ensure the upload directory exists
    image_path = upload_dir / image_file.filename

    # Save the uploaded file to the static/uploads directory
    with open(image_path, "wb") as buffer:
        shutil.copyfileobj(image_file.file, buffer)
    image = f"/static/uploads/{image_file.filename}"

    # Create a new product dictionary
    new_product = {
        "id": len(products) + 1,
        "name": name,
        "price": price,
        "image": image,
        "added_by": username  # Store the username of the user who added the product
    }

    # Add product to the list and save it
    products.append(new_product)
    save_products(products)

    return RedirectResponse("/", status_code=303)


@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, username: str = None):
    # If no username is provided, use the logged-in user's username
    if not username:
        username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    # Find the user
    user = next((user for user in users if user["username"] == username), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Calculate average rating if ratings exist
    ratings = user.get("ratings", [])
    average_rating = round(sum(ratings) / len(ratings), 2) if ratings else "No ratings yet"

    user_email = user.get("email", "Not provided")

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "username": username,
        "user_email": user_email,
        "average_rating": average_rating
    })


@app.get("/edit-profile", response_class=HTMLResponse)
async def edit_profile(request: Request):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    user = next((user for user in users if user["username"] == username), None)
    user_email = user.get("email", "example@example.com") if user else "example@example.com"

    return templates.TemplateResponse("edit_profile.html", {
        "request": request,
        "username": username,
        "user_email": user_email
    })


@app.post("/edit-profile")
async def edit_profile_post(request: Request, username: str = Form(...), email: str = Form(...)):
    current_username = request.cookies.get("username")
    if not current_username:
        return RedirectResponse("/login", status_code=303)

    # Update user information logic here
    for user in users:
        if user["username"] == current_username:
            user["username"] = username
            # Update email if changed, assuming it still meets requirements
            if email.endswith("@mail.utoronto.ca"):
                user["email"] = email
            save_users(users)
            break

    # Update the cookie with the new username if it has changed
    response = RedirectResponse("/profile", status_code=303)
    response.set_cookie(key="username", value=username)
    return response


@app.post("/rate-user")
async def rate_user(request: Request, username: str = Form(...), rating: int = Form(...)):
    if not (1 <= rating <= 5):
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    # Find the user being rated
    user = next((user for user in users if user["username"] == username), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Add the rating
    if "ratings" not in user:
        user["ratings"] = []
    user["ratings"].append(rating)

    # Save the updated users
    save_users(users)

    return RedirectResponse(f"/profile?username={username}", status_code=303)


# Shopping cart mechanism
@app.get("/cart", response_class=HTMLResponse)
async def view_cart(request: Request):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    cart_items = carts.get(username, [])
    return templates.TemplateResponse("cart.html", {
        "request": request,
        "cart_items": cart_items,
        "username": username
    })


@app.post("/add-to-cart", response_class=HTMLResponse)
async def add_to_cart(request: Request, product_id: int = Form(...)):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    # Add product to user's cart only if it isn't already there
    if username not in carts:
        carts[username] = []

    product = next((product for product in products if product["id"] == product_id), None)
    if product:
        # Check if the product is already in the user's cart
        if product_id not in [item["id"] for item in carts[username]]:
            carts[username].append(product)
            save_carts(carts)

    # Redirect to the cart page after adding the product
    return RedirectResponse("/cart", status_code=303)


@app.post("/remove-from-cart", response_class=HTMLResponse)
async def remove_from_cart(request: Request, product_id: int = Form(...)):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    # Remove product from user's cart
    if username in carts:
        carts[username] = [item for item in carts[username] if item["id"] != product_id]
        save_carts(carts)

    # Redirect to the cart page after removing the product
    return RedirectResponse("/cart", status_code=303)
