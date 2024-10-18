from fastapi import FastAPI, Request, Form, Depends, HTTPException, Response, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

# Mount static files for CSS and images
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Set up templates
templates = Jinja2Templates(directory="frontend/templates")

# In-memory storage for demo purposes
users = [{"username": "keshav", "password": "password123"}]
products = [
    {"id": 1, "name": "Math Gr. 6-8", "price": 100, "image": "https://picsum.photos/200/300?random=1"},
    {"id": 2, "name": "English Gr. 6-8", "price": 90, "image": "https://picsum.photos/200/300?random=2"},
    {"id": 3, "name": "Science Gr. 6-8", "price": 110, "image": "https://picsum.photos/200/300?random=3"},
    {"id": 4, "name": "Computers Gr. 6-8", "price": 120, "image": "https://picsum.photos/200/300?random=4"},
    {"id": 5, "name": "Math Gr. 1-5", "price": 80, "image": "https://picsum.photos/200/300?random=5"},
    {"id": 6, "name": "English Gr. 1-5", "price": 70, "image": "https://picsum.photos/200/300?random=6"},
    {"id": 7, "name": "Science Gr. 1-5", "price": 85, "image": "https://picsum.photos/200/300?random=7"},
    {"id": 8, "name": "Computers Gr. 1-5", "price": 95, "image": "https://picsum.photos/200/300?random=8"},
]

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
