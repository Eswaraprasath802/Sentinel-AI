from fastapi import FastAPI
from sentinel_sdk import Sentinel

app = FastAPI()

Sentinel(
    api_key     = "YOUR_GEMINI_API_KEY",
    app_name    = "MyFastAPIApp",
    email_to    = "you@example.com",
    smtp_user   = "alerts@gmail.com",
    smtp_pass   = "app_password",
    whatsapp_to = "whatsapp:+919876543210",
    twilio_sid  = "ACxxxxxxxx",
    twilio_token= "xxxxxxxx",
).attach(app)

@app.get("/")
def index():
    return {"status": "ok"}

@app.get("/simulate/error")
def sim_error():
    raise RuntimeError("Simulated crash for testing Sentinel")
