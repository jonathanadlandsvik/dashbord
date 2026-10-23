# Privacy Policy – Hverdagsdashbord

*Last updated: 23 October 2026*

Hverdagsdashbord is a personal dashboard built and used only by its developer, Jonathan Ward Ådlandsvik. It is not offered to other users.

## What data the app accesses
- **Google Calendar (read-only):** the app reads the titles and times of today's events from the developer's own Google calendars, using the scope `https://www.googleapis.com/auth/calendar.readonly`. It cannot create, change or delete events.
- **Public data:** weather forecasts from MET Norway and bike availability from Trondheim Bysykkel. These contain no personal data.

## How the data is used
Calendar data is only shown on the dashboard. It is fetched when the page loads and is not saved to disk, sold or shared with anyone.

## Storage of credentials
The OAuth tokens are stored as secrets in the hosting platform (Streamlit Community Cloud) and are never committed to the source code repository.

## Revoking access
Access can be revoked at any time at <https://myaccount.google.com/permissions>.

## Contact
jonathan.adlandsvik@gmail.com
