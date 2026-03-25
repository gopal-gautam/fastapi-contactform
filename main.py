from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
import logging
import os
import requests
from dotenv import load_dotenv
from mail_services import MailService, MailServiceError, get_mail_service, validate_mail_service_config

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("contact-backend")

app = FastAPI()

TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "")
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "")
mail_service: MailService | None = None


def _parse_allowed_origins(origins: str) -> list[str]:
    values = [origin.strip() for origin in origins.split(",") if origin.strip()]
    return values


allowed_origins = _parse_allowed_origins(CORS_ALLOWED_ORIGINS)

if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

class ContactForm(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    subject: str = Field(..., min_length=2, max_length=150)
    message: str = Field(..., min_length=5, max_length=5000)
    turnstileToken: str

def verify_turnstile(token: str, remoteip: str | None = None) -> bool:
    resp = requests.post(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data={
            "secret": TURNSTILE_SECRET,
            "response": token,
            "remoteip": remoteip or "",
        },
        timeout=10,
    )
    data = resp.json()
    if not data.get("success", False):
        logger.warning(
            "Turnstile verification failed",
            extra={
                "remote_ip": remoteip,
                "error_codes": data.get("error-codes", []),
                "status_code": resp.status_code,
            },
        )
    return data.get("success", False)


def validate_app_config() -> None:
    missing = []

    if not TURNSTILE_SECRET.strip():
        missing.append("TURNSTILE_SECRET")

    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    validate_mail_service_config()


@app.on_event("startup")
async def startup_event() -> None:
    global mail_service

    try:
        validate_app_config()
        mail_service = get_mail_service()
        logger.info("Application startup validation completed")
    except MailServiceError as exc:
        logger.exception("Mail service configuration validation failed")
        raise RuntimeError(f"Invalid mail service configuration: {exc}") from exc
    except RuntimeError:
        logger.exception("Application configuration validation failed")
        raise

@app.post("/contact")
async def contact(form: ContactForm, request: Request):
    if mail_service is None:
        logger.error("Mail service is not initialized")
        raise HTTPException(status_code=500, detail="Mail service is not initialized")

    client_ip = request.client.host if request.client else None
    logger.info(
        "Received contact form submission",
        extra={
            "client_ip": client_ip,
            "sender_email": str(form.email),
            "subject": form.subject,
        },
    )

    if not verify_turnstile(form.turnstileToken, client_ip):
        raise HTTPException(status_code=400, detail="Bot verification failed")

    try:
        mail_service.send_contact_email(
            name=form.name,
            email=str(form.email),
            subject=form.subject,
            message=form.message,
        )
        logger.info(
            "Mail provider accepted contact email",
            extra={"sender_email": str(form.email), "subject": form.subject},
        )
    except MailServiceError:
        logger.exception(
            "Mail provider failed to send contact email",
            extra={"sender_email": str(form.email), "subject": form.subject},
        )
        raise HTTPException(status_code=500, detail="Failed to send email")

    return {"success": True}