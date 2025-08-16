# In ai_parser.py

import google.generativeai as genai
import json
import datetime

# --- PASTE YOUR GOOGLE AI API KEY HERE ---
API_KEY = os.environ.get('GOOGLE_AI_API_KEY')

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-pro')

def parse_tasks_from_text(text):
    """
    Sends user text to the Gemini AI to extract a list of scheduling tasks.
    """
    # This is our new, highly detailed prompt.
    prompt = f"""
    You are a sophisticated scheduling assistant. Analyze the user's request and convert it into a JSON array of task objects. Each object must have the following fields:

    1.  `task_name`: (string) A concise description of the task.
    2.  `duration_minutes`: (integer) The task's total length in minutes.
    3.  `priority`: (integer) 1 (low), 2 (medium), or 3 (high). Default to 2 if not specified.
    4.  `category`: (string) "work" or "personal". Default to "work" if not specified.
    5.  `deadline`: (string or null) The absolute deadline in ISO 8601 format (YYYY-MM-DDTHH:MM:SS). Default to 7 days from now if not specified.
    6.  `recurrence`: (string or null) An RRULE string. For "every thursday and friday", use "FREQ=WEEKLY;BYDAY=TH,FR". For "daily", use "FREQ=DAILY". Default is null.
    7.  `splittable`: (boolean) Whether the task can be split. Default to true.
    8.  `min_block_duration`: (integer or null) Smallest chunk size in minutes if splittable. Default to 30.

    Analyze the entire message. If multiple tasks are mentioned, create a separate JSON object for each in the array.
    Today's date is {datetime.datetime.now().isoformat()}.

    User Request: "{text}"

    JSON Output:
    """

    try:
        print(f"Sending to AI: {text}")
        response = model.generate_content(prompt)
        
        cleaned_response = response.text.strip().replace('`', '').replace('json', '')
        print(f"AI Response: {cleaned_response}")
        
        # The AI now returns an array of tasks
        return json.loads(cleaned_response)
    except Exception as e:
        print(f"Error parsing AI response: {e}")
        # Return an empty list if parsing fails

        return []

