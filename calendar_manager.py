import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# This defines what our script is allowed to do.
# We're saying we want to read and write calendar events.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_calendar_service():
    """
    Connects to the Google Calendar API and returns a service object.
    This handles the entire authentication flow.
    """
    creds = None
    # The file token.json stores your access tokens.
    # It's created automatically when you run this for the first time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This will look for your 'credentials.json' file.
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            # This line will automatically open a browser window for you to log in
            # and grant permission to your script.
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run so you don't have to log in again.
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    # Build the service object that allows us to make API calls.
    service = build("calendar", "v3", credentials=creds)
    return service

def get_upcoming_events(service, num_events=10):
    """
    Gets the next 'num_events' from your primary calendar and prints them.
    """
    # 'Z' indicates UTC time
    now = datetime.datetime.utcnow().isoformat() + "Z"
    
    print(f"Getting the upcoming {num_events} events")
    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now,
            maxResults=num_events,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = events_result.get("items", [])

    if not events:
        print("No upcoming events found.")
        return

    # Prints the start and name of the upcoming events.
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(start, event["summary"])


# This is the main part that runs when you execute this script directly.
if __name__ == "__main__":
    print("Attempting to connect to Google Calendar...")
    # Get the service object. The first time you run this, it will ask for authentication.
    calendar_service = get_calendar_service() 
    print("Successfully connected to Google Calendar!")
    
    # Now, let's test it by getting your upcoming events.
    get_upcoming_events(calendar_service)