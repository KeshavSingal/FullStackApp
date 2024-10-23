import os
import logging
import random
import shutil
import smtplib
import json
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, HTTPException, Response, Query, UploadFile, File, WebSocket, \
    WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from bson import ObjectId
from datetime import datetime
from typing import Dict
from fastapi.responses import PlainTextResponse


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
app = FastAPI()

# MongoDB setup
uri = os.getenv("MONGO_URI")
client = MongoClient(uri, server_api=ServerApi('1'))

try:
    client.admin.command('ping')
    logger.info("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB. Error details: {str(e)}")
    raise RuntimeError("Failed to connect to MongoDB") from e

# MongoDB Database and Collection references
db = client["marketplace_db"]
products_collection = db["products"]
users_collection = db["users"]
carts_collection = db["carts"]
chat_messages_collection = db["chat_messages"]

# File paths setup
ROOT_DIR = Path(__file__).parent.parent
STATIC_DIR = ROOT_DIR / "frontend" / "static"
TEMPLATE_DIR = ROOT_DIR / "frontend" / "templates"
UPLOAD_DIR = STATIC_DIR / "uploads"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# OTP and SMTP setup
OTP_STORE = {}
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

manager = ConnectionManager()

# WebSocket endpoint
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            # Store the message in MongoDB
            chat_message = {
                "sender": message_data["sender"],
                "receiver": message_data["receiver"],
                "message": message_data["message"],
                "timestamp": datetime.utcnow().isoformat()
            }
            chat_messages_collection.insert_one(chat_message)

            # Send the message to the recipient
            await manager.send_personal_message(json.dumps(message_data), message_data["receiver"])
    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {str(e)}")
        manager.disconnect(user_id)

# Chat page
@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    users = list(users_collection.find({}, {"username": 1, "_id": 0}))
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "username": username,
        "users": users
    })

# Get chat messages
@app.get("/get-messages")
async def get_messages(user1: str, user2: str):
    messages = chat_messages_collection.find({
        "$or": [
            {"sender": user1, "receiver": user2},
            {"sender": user2, "receiver": user1}
        ]
    }).sort("timestamp", 1)

    # Convert ObjectId to string for JSON serialization
    messages_list = []
    for msg in messages:
        msg['_id'] = str(msg['_id'])
        messages_list.append(msg)

    return messages_list

# Existing functions

def send_otp(email: str, otp: str):
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = email
        msg['Subject'] = "Your OTP for Registration"
        body = f"Your OTP for registration is: {otp}"
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, email, msg.as_string())
        server.quit()
    except Exception as e:
        logger.error(f"Failed to send OTP: {e}")
        raise HTTPException(status_code=500, detail="Failed to send OTP. Please try again.")

@app.post("/generate-otp")
async def generate_otp(email: str = Form(...)):
    if not email.endswith("@gmail.com"):
        raise HTTPException(status_code=400, detail="Only Gmail addresses are allowed.")
    otp = str(random.randint(100000, 999999))
    OTP_STORE[email] = otp
    try:
        send_otp(email, otp)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to send OTP. Please try again.")
    return {"message": "OTP sent to your email."}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, search: str = Query("", min_length=0)):
    username = request.cookies.get("username")
    cart = carts_collection.find_one({"username": username})
    cart_count = len(cart["items"]) if cart else 0
    query = {"name": {"$regex": search, "$options": "i"}} if search else {}
    filtered_products = list(products_collection.find(query))
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
async def register_user(request: Request, username: str = Form(...), password: str = Form(...), email: str = Form(...),
                        otp: str = Form(...)):
    error_message = None

    if not email.endswith("@gmail.com"):
        error_message = "Only Gmail addresses are allowed."
    elif email not in OTP_STORE or OTP_STORE[email] != otp:
        error_message = "Invalid OTP. Please try again."
    elif users_collection.find_one({"username": username}):
        error_message = "Username already exists."
    elif users_collection.find_one({"email": email}):
        error_message = "Email already registered."

    if error_message:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error_message": error_message,
            "username": username,
            "email": email
        })

    new_user = {
        "username": username,
        "password": password,  # Note: Passwords should be hashed for security reasons
        "email": email,
        "reviews": [],
        "ratings": [],
        "description": "No description added yet."
    }
    users_collection.insert_one(new_user)

    if email in OTP_STORE:
        del OTP_STORE[email]

    return RedirectResponse("/", status_code=303)


@app.get("/sellers", response_class=HTMLResponse)
async def list_sellers(request: Request):
    seller_usernames = set(products_collection.distinct("added_by"))
    sellers = list(users_collection.find({"username": {"$in": list(seller_usernames)}}))

    return templates.TemplateResponse("sellers.html", {
        "request": request,
        "sellers": sellers
    })


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, response: Response, username: str = Form(...), password: str = Form(...)):
    user = users_collection.find_one({"username": username, "password": password})
    if user:
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(key="username", value=username)
        return response

    error_message = "Invalid username or password"
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error_message": error_message,
        "username": username
    })


@app.get("/logout", response_class=HTMLResponse)
async def logout(response: Response):
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("username")
    return response


@app.get("/seller-profile/{username}", response_class=HTMLResponse)
async def seller_profile(request: Request, username: str):
    current_username = request.cookies.get("username")
    if not current_username:
        return RedirectResponse("/login", status_code=303)

    seller = users_collection.find_one({"username": username})
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")

    ratings = seller.get("ratings", [])
    average_rating = round(sum(ratings) / len(ratings), 2) if ratings else "No ratings yet"

    return templates.TemplateResponse("seller_profile.html", {
        "request": request,
        "seller": seller,
        "username": current_username,
        "average_rating": average_rating
    })


@app.get("/seller-dashboard", response_class=HTMLResponse)
async def seller_dashboard(request: Request):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    # Get all products added by this seller
    seller_products = list(products_collection.find({"added_by": username}))

    return templates.TemplateResponse("seller_dashboard.html", {
        "request": request,
        "username": username,
        "products": seller_products
    })


@app.post("/delete-product/{product_id}")
async def delete_product(product_id: str, request: Request):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    # Verify the product belongs to the seller before deleting
    product = products_collection.find_one({"_id": ObjectId(product_id)})
    if not product or product["added_by"] != username:
        raise HTTPException(status_code=403, detail="Unauthorized to delete this product")

    # Delete the product
    products_collection.delete_one({"_id": ObjectId(product_id)})

    return RedirectResponse("/seller-dashboard", status_code=303)

@app.post("/review-seller")
async def review_seller(request: Request, username: str = Form(...), review: str = Form(...), rating: int = Form(...)):
    current_username = request.cookies.get("username")
    if not current_username:
        return RedirectResponse("/login", status_code=303)

    if current_username == username:
        raise HTTPException(status_code=400, detail="You cannot review yourself.")

    seller = users_collection.find_one({"username": username})
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")

    existing_review = next((r for r in seller.get("reviews", []) if r["reviewer"] == current_username), None)
    if existing_review:
        raise HTTPException(status_code=400, detail="You have already reviewed this seller.")

    new_review = {"reviewer": current_username, "review": review, "rating": rating}
    users_collection.update_one(
        {"username": username},
        {
            "$push": {"reviews": new_review, "ratings": rating},
            "$set": {"average_rating": {"$avg": "$ratings"}}
        }
    )

    return RedirectResponse(f"/seller-profile/{username}", status_code=303)


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

    upload_dir = STATIC_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    image_path = upload_dir / image_file.filename

    with open(image_path, "wb") as buffer:
        shutil.copyfileobj(image_file.file, buffer)
    image = f"/static/uploads/{image_file.filename}"

    new_product = {
        "name": name,
        "price": price,
        "image": image,
        "added_by": username
    }

    products_collection.insert_one(new_product)

    return RedirectResponse("/", status_code=303)


@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, username: str = None):
    if not username:
        username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    user = users_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    ratings = user.get("ratings", [])
    average_rating = round(sum(ratings) / len(ratings), 2) if ratings else "No ratings yet"

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "username": username,
        "user_email": user.get("email", "Not provided"),
        "user_description": user.get("description", "No description added yet."),
        "average_rating": average_rating,
        "user_reviews": user.get("reviews", [])
    })


@app.get("/product/{product_id}", response_class=HTMLResponse)
async def product_profile(request: Request, product_id: str):
    username = request.cookies.get("username")
    product = products_collection.find_one({"_id": ObjectId(product_id)})

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Calculate average rating
    ratings = product.get("ratings", [])
    average_rating = round(sum(ratings) / len(ratings), 2) if ratings else "No ratings yet"

    return templates.TemplateResponse("product_profile.html", {
        "request": request,
        "product": product,
        "username": username,
        "average_rating": average_rating,
        "product_reviews": product.get("reviews", [])
    })


@app.post("/rate-product")
async def rate_product(request: Request, product_id: str = Form(...), rating: int = Form(...), review: str = Form(...)):
    username = request.cookies.get("username")
    if not username:
        raise HTTPException(status_code=403, detail="You must be logged in to leave a review.")

    product = products_collection.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product["added_by"] == username:
        raise HTTPException(status_code=400, detail="You cannot rate your own product.")

    if not (1 <= rating <= 5):
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    new_review = {"reviewer": username, "review": review, "rating": rating}
    products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {
            "$push": {"reviews": new_review, "ratings": rating},
            "$set": {"average_rating": {"$avg": "$ratings"}}
        }
    )

    return RedirectResponse(f"/product/{product_id}", status_code=303)

@app.get("/edit-profile", response_class=HTMLResponse)
async def edit_profile(request: Request):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    user = users_collection.find_one({"username": username})
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

    if email.endswith("@gmail.com"):
        users_collection.update_one(
            {"username": current_username},
            {"$set": {"username": username, "email": email}}
        )

    response = RedirectResponse("/profile", status_code=303)
    response.set_cookie(key="username", value=username)
    return response


@app.post("/rate-user")
async def rate_user(request: Request, username: str = Form(...), rating: int = Form(...), review: str = Form(...)):
    current_username = request.cookies.get("username")
    if not current_username:
        raise HTTPException(status_code=403, detail="You must be logged in to leave a review.")

    if username == current_username:
        raise HTTPException(status_code=400, detail="You cannot rate yourself.")

    if not (1 <= rating <= 5):
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    user = users_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_review = {"reviewer": current_username, "review": review, "rating": rating}
    users_collection.update_one(
        {"username": username},
        {
            "$push": {"reviews": new_review, "ratings": rating},
            "$set": {"average_rating": {"$avg": "$ratings"}}
        }
    )

    return RedirectResponse(f"/profile?username={username}", status_code=303)


@app.get("/cart", response_class=HTMLResponse)
async def view_cart(request: Request):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    cart = carts_collection.find_one({"username": username})
    cart_items = cart["items"] if cart else []
    return templates.TemplateResponse("cart.html", {
        "request": request,
        "cart_items": cart_items,
        "username": username
    })


@app.post("/clear-userbase", response_class=HTMLResponse)
async def clear_userbase(request: Request):
    products_collection.delete_many({})
    users_collection.delete_many({})
    carts_collection.delete_many({})

    if UPLOAD_DIR.exists():
        for file in UPLOAD_DIR.iterdir():
            if file.is_file():
                file.unlink()
            elif file.is_dir():
                shutil.rmtree(file)

    return HTMLResponse(content="All databases and uploads have been cleared successfully.", status_code=200)


@app.post("/add-to-cart", response_class=HTMLResponse)
async def add_to_cart(request: Request, product_id: str = Form(...)):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    product = products_collection.find_one({"_id": ObjectId(product_id)})
    if product:
        carts_collection.update_one(
            {"username": username},
            {"$addToSet": {"items": product}},
            upsert=True
        )

    return RedirectResponse("/cart", status_code=303)

@app.post("/remove-from-cart")
async def remove_from_cart(request: Request, product_id: str = Form(...)):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    carts_collection.update_one(
        {"username": username},
        {"$pull": {"items": {"_id": ObjectId(product_id)}}}
    )

    return RedirectResponse("/cart", status_code=303)

@app.post("/edit-description")
async def edit_description(request: Request, description: str = Form(...)):
    current_username = request.cookies.get("username")
    if not current_username:
        return RedirectResponse("/login", status_code=303)

    users_collection.update_one(
        {"username": current_username},
        {"$set": {"description": description}}
    )

    return RedirectResponse(f"/profile?username={current_username}", status_code=303)

# Error handling
@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc: HTTPException):
    return PlainTextResponse(str(exc.detail), status_code=404)

@app.exception_handler(500)
async def server_error_exception_handler(request: Request, exc: HTTPException):
    return PlainTextResponse("Internal Server Error", status_code=500)



# Run the application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
