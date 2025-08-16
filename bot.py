# In bot.py

import datetime
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PicklePersistence

from calendar_manager import get_calendar_service
from ai_parser import parse_tasks_from_text

# --- CONFIGURATION ---
BOT_TOKEN = "BOT_API_HERE"
LOCAL_TIMEZONE = pytz.timezone("Asia/Manila") # Philippines Timezone
WORK_HOURS = {"start": 6, "end": 21}      # 6 AM to 9 PM
PERSONAL_HOURS = {"start": 22, "end": 5}   # 10 PM to 5 AM


# --- Helper Function to create calendar events ---
def create_calendar_event(service, name, start_time, end_time, recurrence=None):
    event_body = {
        'summary': name,
        'start': {'dateTime': start_time.isoformat()},
        'end': {'dateTime': end_time.isoformat()},
        'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 10}]},
    }
    if recurrence:
        event_body['recurrence'] = [f'RRULE:{recurrence}']
    
    return service.events().insert(calendarId='primary', body=event_body).execute()


# --- THE ADVANCED SCHEDULING ENGINE ---
def find_and_schedule_slots(service, task):
    duration = task.get('duration_minutes')
    category = task.get('category', 'work')
    priority = task.get('priority', 2)
    deadline_str = task.get('deadline')
    min_block = task.get('min_block_duration', 30)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    deadline_utc = (datetime.datetime.fromisoformat(deadline_str).astimezone(datetime.timezone.utc) if deadline_str 
                    else now_utc + datetime.timedelta(days=7))

    busy_events = service.events().list(
        calendarId='primary', timeMin=now_utc.isoformat(), timeMax=deadline_utc.isoformat(),
        singleEvents=True, orderBy='startTime'
    ).execute().get('items', [])

    free_slots = []
    check_start = now_utc
    for event in busy_events:
        event_start = datetime.datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
        if check_start < event_start:
            free_slots.append({'start': check_start, 'end': event_start})
        check_start = datetime.datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
    if check_start < deadline_utc:
        free_slots.append({'start': check_start, 'end': deadline_utc})

    # This logic is complex to handle your overnight personal hours
    if category == 'personal':
        allowed_hours = PERSONAL_HOURS
    else: # Default to work
        allowed_hours = WORK_HOURS

    valid_slots = []
    for slot in free_slots:
        # This part is tricky; we just check if the start falls in the valid range for simplicity
        slot_start_local = slot['start'].astimezone(LOCAL_TIMEZONE)
        
        is_in_hours = False
        if allowed_hours['start'] > allowed_hours['end']: # Overnight case (e.g., 22:00 to 05:00)
            if slot_start_local.hour >= allowed_hours['start'] or slot_start_local.hour < allowed_hours['end']:
                is_in_hours = True
        else: # Daytime case
            if allowed_hours['start'] <= slot_start_local.hour < allowed_hours['end']:
                is_in_hours = True
        
        if is_in_hours and (slot['end'] - slot['start']).total_seconds() / 60 >= min_block:
             valid_slots.append(slot)

    if priority >= 2:
        valid_slots.sort(key=lambda s: s['start'])
    else:
        valid_slots.sort(key=lambda s: s['start'], reverse=True)

    for slot in valid_slots:
        if (slot['end'] - slot['start']).total_seconds() / 60 >= duration:
            event_start = slot['start']
            event_end = event_start + datetime.timedelta(minutes=duration)
            created_event = create_calendar_event(service, task['task_name'], event_start, event_end, task.get('recurrence'))
            return "SUCCESS", [created_event]

    if not task.get('splittable', True):
        return "CANNOT_FIT", []

    remaining_duration = duration
    created_events = []
    chunk_num = 1
    total_chunks = (duration // min_block) + 1

    for slot in valid_slots:
        slot_duration = (slot['end'] - slot['start']).total_seconds() / 60
        duration_to_schedule = min(remaining_duration, slot_duration)
        
        if duration_to_schedule >= min_block:
            chunk_name = f"{task['task_name']} ({chunk_num}/{total_chunks})"
            event_start = slot['start']
            event_end = event_start + datetime.timedelta(minutes=duration_to_schedule)
            
            created_event = create_calendar_event(service, chunk_name, event_start, event_end)
            created_events.append(created_event)
            
            remaining_duration -= duration_to_schedule
            chunk_num += 1
            if remaining_duration < min_block:
                break
    
    if remaining_duration < min_block:
        return "SUCCESS_SPLIT", created_events
    else:
        if deadline_utc.date() == now_utc.date():
            return "CANNOT_FIT_TODAY", []
        return "CANNOT_FIT", []


# --- Main Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    start_text = """
    Hello! I am your AI scheduling assistant.
    - Send me a task to schedule.
    - Use /upcoming to see your next 10 events.
    - I'll send you a daily briefing every morning at 5 AM.
    """
    await update.message.reply_text(start_text)

async def upcoming_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Let me check your calendar for upcoming events...")
    service = get_calendar_service()
    now = datetime.datetime.utcnow().isoformat() + "Z"
    
    events_result = service.events().list(
        calendarId="primary", timeMin=now, maxResults=10, singleEvents=True, orderBy="startTime"
    ).execute()
    events = events_result.get("items", [])

    if not events:
        await update.message.reply_text("You have no upcoming events. Looks clear!")
        return

    reply_text = "Here are your next 10 upcoming events:\n\n"
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        dt_obj = datetime.datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(LOCAL_TIMEZONE)
        formatted_start = dt_obj.strftime("%a, %b %d at %I:%M %p")
        reply_text += f"🗓️ {formatted_start} - {event['summary']}\n"
        
    await update.message.reply_text(reply_text)

async def daily_briefing(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    
    print(f"Running daily briefing for chat_id: {chat_id}")
    service = get_calendar_service()
    
    now = datetime.datetime.now(LOCAL_TIMEZONE)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + datetime.timedelta(days=1)
    
    events_result = service.events().list(
        calendarId="primary", timeMin=start_of_day.isoformat(), timeMax=end_of_day.isoformat(),
        singleEvents=True, orderBy="startTime"
    ).execute()
    events = events_result.get("items", [])
    
    if not events:
        message = "Good morning! ☀️ You have no events scheduled for today."
    else:
        message = "Good morning! ☀️ Here is your schedule for today:\n\n"
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            dt_obj = datetime.datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(LOCAL_TIMEZONE)
            formatted_start = dt_obj.strftime("%I:%M %p") if 'T' in start else "All day"
            message += f"⏰ {formatted_start} - {event['summary']}\n"
            
    await context.bot.send_message(chat_id=chat_id, text=message)

async def schedule_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text("Roger that. Analyzing your request and building your optimal schedule...")

    tasks = parse_tasks_from_text(user_text)
    if not tasks:
        await update.message.reply_text("I'm sorry, I couldn't understand any tasks from your message.")
        return

    service = get_calendar_service()
    final_reply = ""

    for task in tasks:
        task_name = task.get('task_name', 'Unnamed Task')
        status, events = find_and_schedule_slots(service, task)
        
        if status == "SUCCESS":
            event_time = datetime.datetime.fromisoformat(events[0]['start']['dateTime'].replace('Z', '+00:00')).astimezone(LOCAL_TIMEZONE)
            friendly_time = event_time.strftime("%A, %b %d at %I:%M %p")
            final_reply += f"✅ Scheduled '{task_name}' for you on {friendly_time}.\n"
        elif status == "SUCCESS_SPLIT":
            final_reply += f"✅ Your schedule is tight! I've split '{task_name}' into {len(events)} parts for you.\n"
        elif status == "CANNOT_FIT_TODAY":
            final_reply += f"❌ I tried, but I could not fit '{task_name}' into your schedule today, even by splitting it.\n"
        else:
            final_reply += f"❌ I could not find a suitable time for '{task_name}' before its deadline.\n"

    await update.message.reply_text(final_reply)

def main():
    print("Advanced AI Scheduling Bot is starting...")
    
    persistence = PicklePersistence(filepath="./bot_data.pkl")
    
    application = Application.builder().token(BOT_TOKEN).persistence(persistence).build()

    job_queue = application.job_queue
    # A robust way to schedule the job after the bot has the user's chat_id
    if 'chat_id' in application.user_data:
       chat_id = application.user_data['chat_id']
       briefing_time = datetime.time(hour=5, minute=0, tzinfo=LOCAL_TIMEZONE)
       job_queue.run_daily(daily_briefing, time=briefing_time, name=f"daily_{chat_id}", chat_id=chat_id)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("upcoming", upcoming_events))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_tasks_handler))

    application.run_polling()

if __name__ == '__main__':

    main()
