from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, EmailStr, Field
import os
import requests

app = FastAPI()

TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
TO_EMAIL = os.getenv("TO_EMAIL", "")

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
    return data.get("success", False)

def send_email(form: ContactForm):
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "personalizations": [
            {
                "to": [{"email": TO_EMAIL}],
                "subject": f"Contact Form: {form.subject}",
            }
        ],
        "from": {"email": TO_EMAIL},
        "reply_to": {"email": form.email},
        "content": [
            {
                "type": "text/plain",
                "value": (
                    f"Name: {form.name}\n"
                    f"Email: {form.email}\n"
                    f"Subject: {form.subject}\n\n"
                    f"Message:\n{form.message}"
                ),
            }
        ],
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    if resp.status_code >= 300:
        raise Exception(f"SendGrid error: {resp.status_code} {resp.text}")

@app.post("/contact")
async def contact(form: ContactForm, request: Request):
    client_ip = request.client.host if request.client else None

    if not verify_turnstile(form.turnstileToken, client_ip):
        raise HTTPException(status_code=400, detail="Bot verification failed")

    try:
        send_email(form)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to send email")

    return {"success": True}