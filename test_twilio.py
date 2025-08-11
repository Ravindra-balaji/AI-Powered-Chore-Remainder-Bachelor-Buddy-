import os
import random
from twilio.rest import Client
from dotenv import load_dotenv
import cohere

# Load environment variables
load_dotenv()

# ---- CONFIG ----
TEST_NUMBER = "+919515175300"  # Change if needed
NAME = "Ravindra Balaji"
CHORES = [
    "Wash the dishes",
    "Clean the living room",
    "Take out the trash",
    "Cook dinner",
    "Do the laundry",
    "Water the plants",
    "Organize your desk"
]

# Pick a random work
work = random.choice(CHORES)

# Cohere API setup
co = cohere.Client(os.getenv("COHERE_API_KEY"))

# Twilio setup
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ---- Generate AI message ----
prompt = f"""
You are a friendly roommate.
Send a short and casual WhatsApp reminder to {NAME} that their chore for today is: {work}.
Make it friendly, less than 30 words, and a bit playful.
"""

try:
    ai_response = co.chat(
        model="command-r-plus",
        message=prompt,
        temperature=0.8
    )
    message_text = ai_response.text.strip()
except Exception as e:
    print(f"❌ Cohere Error: {e}")
    message_text = f"Hey {NAME}, reminder: today's chore is '{work}' 🙂"

# ---- Send WhatsApp message ----
try:
    msg = twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        body=message_text,
        to=f"whatsapp:{TEST_NUMBER}"
    )
    print(f"✅ Message sent! SID: {msg.sid}")
    print(f"📩 Content: {message_text}")
except Exception as e:
    print(f"❌ Twilio Error: {e}")
