import os
import logging
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# ============== GitHub OAuth Configuration ==============
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "YOUR_GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "YOUR_GITHUB_CLIENT_SECRET")
# 端口与 uvicorn 实际监听一致（8001）；可由环境变量覆盖
GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_REDIRECT_URI", "http://localhost:8001/api/auth/github/callback"
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Base path for the actual project (nested structure)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "web_app", "data")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)

app = FastAPI(title="FinPilot AI", version="2.0.0")

# Mount static files and templates
app.mount("/static", StaticFiles(directory=os.path.join(PROJECT_ROOT, "web_app", "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(PROJECT_ROOT, "web_app", "templates"))

# ============== Database Integration ==============
from .database.connection import init_db  # noqa: E402
from .auth import (  # noqa: E402
    get_current_user, create_user_session, delete_user_session,
    authenticate_user, register_user, get_or_create_github_user,
    change_user_password, init_default_admin
)
from .middleware import RequestLoggerMiddleware  # noqa: E402
from .admin_routes import router as admin_router  # noqa: E402

# Initialize database
init_db()
init_default_admin()

# Add middleware for request logging（先加，确保最先执行日志记录）
app.add_middleware(RequestLoggerMiddleware)

# Include admin routes
app.include_router(admin_router)

# ============== FinPilot AI 企业财务智能API ==============
from finpilot.api import create_router, configure_middleware  # noqa: E402
from finpilot.database import init_db as init_finpilot_db  # noqa: E402
from finpilot.database.connection import SessionLocal as FinPilotSessionLocal  # noqa: E402
from finpilot.database.seed import seed_financial_data  # noqa: E402

# 初始化 FinPilot 数据库 + 示例财务数据
init_finpilot_db()
with FinPilotSessionLocal() as _fp_session:
    seed_financial_data(_fp_session)

# 统一挂载全部中间件（CORS + Tenant + RateLimit + trace + lifespan/subscription_scheduler）
# 解决双 App 架构断裂：此前仅挂载 CORS，缺失 TenantMiddleware / SlowAPIMiddleware / lifespan
configure_middleware(app)
# 挂载 /api/v1 路由
app.include_router(create_router())

# Auth Models
class LoginRequest(BaseModel):
    email: str
    password: str
    remember: bool = False

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str

class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str

# ============== Auth Routes ==============

@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request, response: Response):
    user = authenticate_user(req.email, req.password)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Create session
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]
    session_id = create_user_session(
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        remember=req.remember
    )

    # Set cookie
    max_age = 30 * 24 * 60 * 60 if req.remember else 7 * 24 * 60 * 60
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        max_age=max_age,
        samesite="lax"
    )

    return {"success": True, "user": {"email": user.email, "name": user.name}}

@app.post("/api/auth/register")
async def register(req: RegisterRequest, request: Request, response: Response):
    user = register_user(req.email, req.password, req.name)

    if not user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Auto login after register
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]
    session_id = create_user_session(
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        samesite="lax"
    )

    return {"success": True, "user": {"email": user.email, "name": user.name}}

@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id:
        delete_user_session(session_id)

    response.delete_cookie("session_id")
    return {"success": True}

@app.get("/api/auth/me")
async def get_me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"email": user["email"], "name": user["name"]}

@app.post("/api/auth/change-password")
async def change_password_route(req: ChangePasswordRequest, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # GitHub users cannot change password
    if user.get("provider") == "github" or user["email"].startswith("github:"):
        raise HTTPException(status_code=400, detail="GitHub users cannot change password")

    success = change_user_password(user["id"], req.currentPassword, req.newPassword)

    if not success:
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    return {"success": True, "message": "Password changed successfully"}

# ============== GitHub OAuth Routes ==============

@app.get("/api/auth/github")
async def github_login():
    """Redirect to GitHub OAuth authorization page"""
    if GITHUB_CLIENT_ID == "YOUR_GITHUB_CLIENT_ID":
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured. Please set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.")

    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        f"&scope=user:email"
    )
    return RedirectResponse(url=github_auth_url)

@app.get("/api/auth/github/callback")
async def github_callback(code: str, response: Response):
    """Handle GitHub OAuth callback"""
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")

    # Lazy import httpx (only required for GitHub OAuth)
    try:
        import httpx
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="httpx not installed; GitHub OAuth unavailable") from exc

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI
            },
            headers={"Accept": "application/json"}
        )
        token_data = token_response.json()

        if "error" in token_data:
            raise HTTPException(status_code=400, detail=token_data.get("error_description", "Failed to get access token"))

        access_token = token_data.get("access_token")

        # Get user info from GitHub
        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
        )
        github_user = user_response.json()

        # Get user email (might be private)
        email_response = await client.get(
            "https://api.github.com/user/emails",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
        )
        emails = email_response.json()

        # Find primary email
        primary_email = None
        for email_obj in emails:
            if email_obj.get("primary"):
                primary_email = email_obj.get("email")
                break

        if not primary_email:
            primary_email = github_user.get("email") or f"{github_user['login']}@github.local"

        # Create or update user in database
        user = get_or_create_github_user(
            email=primary_email,
            name=github_user.get("name") or github_user.get("login"),
            avatar_url=github_user.get("avatar_url"),
            github_id=github_user.get("id")
        )

        # Create session
        session_id = create_user_session(user_id=user.id)

        # Create redirect response with cookie
        redirect_response = RedirectResponse(url="/", status_code=302)
        redirect_response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=7 * 24 * 60 * 60,
            samesite="lax"
        )

        return redirect_response

# ============== Page Routes ==============

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    user = get_current_user(request)
    if not user:
        response = RedirectResponse(url="/login", status_code=303)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    return templates.TemplateResponse(request, "index.html", {"user": user})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        response = RedirectResponse(url="/", status_code=303)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    return templates.TemplateResponse(request, "login.html")

# ============== Chrome DevTools Route ==============

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools():
    """Handle Chrome DevTools configuration request"""
    return Response(content="", status_code=204)
