import os
import pandas as pd
import cohere
from twilio.rest import Client
from dotenv import load_dotenv
from datetime import datetime

# Load .env
load_dotenv()

# Cohere API
COHERE_KEY = os.getenv("COHERE_API_KEY")
co = None
if COHERE_KEY:
    try:
        co = cohere.Client(COHERE_KEY)
    except Exception as e:
        print("⚠ Cohere init failed:", e)
        co = None

# Twilio API
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    except Exception as e:
        print("⚠ Twilio init failed:", e)
        twilio_client = None

LOG_FILE = "chore_log.csv"


# --- PHONE CLEANUP ---
def clean_phone(phone):
    phone = str(phone).strip()
    # remove common separators
    for ch in (" ", "-", "(", ")", "."):
        phone = phone.replace(ch, "")
    # remove leading zeros
    if phone.startswith("0"):
        phone = phone.lstrip("0")
    # heuristics: if already starts with +, keep; else add +91 default
    if phone.startswith("+"):
        return phone
    if phone.startswith("91") and len(phone) >= 11:  # already country code without +
        return "+" + phone
    # default to +91 if it's 9/10 digits
    if len(phone) in (9, 10):
        return "+91" + phone
    # otherwise return with + prefix fallback
    return "+91" + phone


# --- AI MESSAGE GENERATION (with fallback) ---
def generate_message(name, work, shift=None):
    # Build prompt
    shift_text = f" for the {shift} shift" if shift else ""
    prompt = (
        f"You are a cheerful flatmate. Send a short, friendly WhatsApp reminder to {name}{shift_text} "
        f"about their chore: {work}. Keep it under 35 words, casual and motivating."
    )

    # Use Cohere if available
    if co:
        try:
            resp = co.chat(model="command-r-plus", message=prompt, temperature=0.7)
            text = resp.text.strip()
            if text:
                return text
        except Exception as e:
            print("⚠ Cohere error:", e)

    # Fallback simple template
    return f"Hi {name}! Friendly reminder{shift_text}: {work}. Thanks 🙂"


# --- SEND MESSAGE (with error handling) ---
def send_whatsapp(phone, message):
    if not twilio_client:
        raise RuntimeError("Twilio client not configured")
    try:
        m = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=message,
            to=f"whatsapp:{phone}"
        )
        return {"ok": True, "sid": getattr(m, "sid", None)}
    except Exception as e:
        print(f"❌ Twilio send failed for {phone}: {e}")
        return {"ok": False, "error": str(e)}


# --- LOG MANAGEMENT (robust) ---
def load_sent_log():
    # ensure expected columns exist so KeyError never happens
    cols = ["Day", "Shift", "Name", "Phone", "Work", "Message", "Timestamp"]
    if os.path.exists(LOG_FILE):
        df = pd.read_csv(LOG_FILE, dtype=str)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df
    return pd.DataFrame(columns=cols)


def save_to_log(day, shift, name, phone, work, message):
    log_df = load_sent_log()
    new_entry = pd.DataFrame([{
        "Day": day,
        "Shift": shift,
        "Name": name,
        "Phone": phone,
        "Work": work,
        "Message": message,
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    log_df = pd.concat([log_df, new_entry], ignore_index=True)
    log_df.to_csv(LOG_FILE, index=False)


# --- MAIN LOGIC ---
def process_chores(csv_file, dry_run=False, prefer_shift=None):
    """
    csv_file: path or file-like (Flask uploaded file .stream works)
    dry_run: True -> don't send messages, just generate previews
    prefer_shift: "Lunch" or "Dinner" overrides auto detection (optional)
    """
    # detect day and shift
    today = datetime.now().strftime("%A")
    hour = datetime.now().hour
    auto_shift = "Lunch" if hour < 16 else "Dinner"
    shift = prefer_shift if prefer_shift in ("Lunch", "Dinner") else auto_shift

    print(f"📅 Today is {today} ({shift} shift)")

    # read CSV (accept path or file-like)
    chores = pd.read_csv(csv_file, dtype=str).fillna("")
    # normalize column names (robust matching)
    chores.columns = chores.columns.str.strip().str.lower()

    col_map = {}
    for col in chores.columns:
        c = col.lower()
        if "day" in c:
            col_map[col] = "Day"
        elif "shift" in c:
            col_map[col] = "Shift"
        elif "phone" in c or "number" in c or "contact" in c:
            col_map[col] = "Phone"
        elif "name" in c or "person" in c:
            col_map[col] = "Name"
        elif "work" in c or "task" in c or "chore" in c:
            col_map[col] = "Work"
    chores.rename(columns=col_map, inplace=True)

    # Ensure Day column exists
    if "Day" not in chores.columns:
        raise ValueError("CSV must contain a column for day (day, Day, etc.)")

    # optional shift filtering
    if "Shift" in chores.columns:
        mask = (chores["Day"].str.lower() == today.lower()) & (chores["Shift"].str.lower() == shift.lower())
    else:
        mask = chores["Day"].str.lower() == today.lower()

    todays_tasks = chores[mask].copy()
    if todays_tasks.empty:
        print(f"No chores for {today} ({shift}).")
        return []

    # ensure necessary columns exist in todays_tasks
    for req in ("Name", "Phone", "Work"):
        if req not in todays_tasks.columns:
            raise ValueError(f"CSV must contain a column for {req.lower()} (found columns: {list(chores.columns)})")

    sent_log = load_sent_log()
    logs = []

    for _, task in todays_tasks.iterrows():
        # robust access using get to avoid KeyError
        raw_phone = task.get("Phone", "")
        name = str(task.get("Name", "")).strip()
        work = str(task.get("Work", "")).strip()
        task_shift = task.get("Shift", shift) if "Shift" in task.index else shift

        phone = clean_phone(raw_phone)

        # duplicate check: same phone + day + shift
        dup_mask = (sent_log["Phone"] == phone) & (sent_log["Day"] == today) & (sent_log["Shift"] == task_shift)
        if not sent_log.empty and dup_mask.any():
            logs.append({
                "Day": today,
                "Shift": task_shift,
                "Name": name,
                "Phone": phone,
                "Work": work,
                "Message": "",
                "Status": "Skipped - Already Sent"
            })
            continue

        # generate message
        msg = generate_message(name, work, task_shift)
        print(f"Generated for {name} ({phone}): {msg}")

        if not dry_run:
            result = send_whatsapp(phone, msg)
            if result.get("ok"):
                save_to_log(today, task_shift, name, phone, work, msg)
                status = "Sent"
            else:
                status = f"Failed - {result.get('error')}"
        else:
            status = "Preview Only"

        logs.append({
            "Day": today,
            "Shift": task_shift,
            "Name": name,
            "Phone": phone,
            "Work": work,
            "Message": msg,
            "Status": status
        })

    return logs


# quick CLI testing helper
if __name__ == "__main__":
    # example: python main_logic.py source2.csv
    import sys
    fp = sys.argv[1] if len(sys.argv) > 1 else "source2.csv"
    out = process_chores(fp, dry_run=True)
    for r in out:
        print(r)
