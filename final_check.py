import os
import pandas as pd
import cohere
from twilio.rest import Client
from dotenv import load_dotenv
from datetime import datetime

# Load .env
load_dotenv()

# Cohere API
co = cohere.Client(os.getenv("COHERE_API_KEY"))

# Twilio API
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
LOG_FILE = "chore_log.csv"


# --- PHONE CLEANUP ---
def clean_phone(phone):
    phone = str(phone).strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone.startswith("0"):
        phone = phone[1:]
    if not phone.startswith("+91"):  # Default India code
        phone = "+91" + phone
    return phone


# --- AI MESSAGE GENERATION ---
def generate_message(name, work):
    prompt = (
        f"You are a cheerful flatmate reminding another flatmate named {name} "
        f"about their daily chore: {work}. Write a short WhatsApp message "
        f"under 40 words that is friendly and motivating."
    )
    try:
        response = co.chat(
            model="command-r-plus",
            message=prompt,
            temperature=0.7
        )
        return response.text.strip()
    except Exception as e:
        print(f"⚠ Cohere error, using fallback message: {e}")
        return f"Hey {name}, quick reminder: today your chore is '{work}'. Let's get it done! 💪"


# --- SEND MESSAGE ---
def send_whatsapp(phone, message):
    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=message,
            to=f"whatsapp:{phone}"
        )
    except Exception as e:
        print(f"❌ Twilio send failed for {phone}: {e}")


# --- LOG MANAGEMENT ---
def load_sent_log():
    if os.path.exists(LOG_FILE):
        return pd.read_csv(LOG_FILE, dtype=str)
    return pd.DataFrame(columns=["Day", "Name", "Phone", "Work", "Message", "Timestamp"])


def save_to_log(day, name, phone, work, message):
    log_df = load_sent_log()
    new_entry = pd.DataFrame([{
        "Day": day,
        "Name": name,
        "Phone": phone,
        "Work": work,
        "Message": message,
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    log_df = pd.concat([log_df, new_entry], ignore_index=True)
    log_df.to_csv(LOG_FILE, index=False)


# --- MAIN LOGIC ---
def process_chores(csv_file="source.csv", dry_run=False):
    today = datetime.now().strftime("%A")
    print(f"📅 Today is {today}")

    chores = pd.read_csv(csv_file, dtype=str).fillna("")
    chores.columns = chores.columns.str.strip().str.lower()

    required_cols = {"day", "number", "name", "work"}
    if not required_cols.issubset(chores.columns):
        raise ValueError(f"CSV must contain columns: {required_cols}")

    chores.rename(columns={
        'day': 'Day',
        'number': 'Phone',
        'name': 'Name',
        'work': 'Work'
    }, inplace=True)

    todays_tasks = chores[chores['Day'].str.lower() == today.lower()]
    if todays_tasks.empty:
        print(f"No chores for {today}.")
        return []

    sent_log = load_sent_log()
    logs = []

    for _, task in todays_tasks.iterrows():
        phone = clean_phone(task['Phone'])

        if ((sent_log["Phone"] == phone) & (sent_log["Day"] == today)).any():
            logs.append({
                "Name": task['Name'],
                "Phone": phone,
                "Work": task['Work'],
                "Status": "Skipped - Already Sent"
            })
            continue

        msg = generate_message(task['Name'], task['Work'])
        print(f"Generated for {task['Name']} ({phone}): {msg}")

        if not dry_run:
            send_whatsapp(phone, msg)
            save_to_log(today, task['Name'], phone, task['Work'], msg)

        logs.append({
            "Name": task['Name'],
            "Phone": phone,
            "Work": task['Work'],
            "Message": msg,
            "Status": "Sent" if not dry_run else "Preview Only"
        })

    return logs


if __name__ == "__main__":
    confirm = input("⚠ This will send WhatsApp messages. Type 'YES' to confirm: ")
    if confirm.strip().upper() == "YES":
        process_chores("source.csv", dry_run=False)
    else:
        print("❌ Cancelled sending.")
