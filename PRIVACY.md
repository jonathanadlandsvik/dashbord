# Privacy Policy – Hverdagsdashbord

*Last updated: 4 November 2026*

Hverdagsdashbord is a personal dashboard built and used only by its developer,
Jonathan Ward Ådlandsvik. It is not offered to other users, and only the developer
can sign in.

## What data the app processes

- **Google Calendar (read-only):** the titles and times of today's events from the
  developer's own Google calendars, using the scope
  `https://www.googleapis.com/auth/calendar.readonly`. The app cannot create,
  change or delete events. Calendar data is fetched when the dashboard is opened,
  shown, and not stored. The short-lived access token is kept in memory only.
- **Health data:** once a day, a shortcut on the developer's iPhone sends the
  previous day's totals from Apple Health: steps, active energy, exercise minutes
  and minutes stood per hour (used to count stand hours). These daily totals are
  stored in the app's database. No raw samples, heart rate, location or other
  health data is sent.
- **Habit tracking:** which of the developer's own habits were completed each day,
  the weekly average screen time and an optional short weekly note, all entered by
  the developer.
- **Sign-in data:** the public keys of the developer's passkeys, SHA-256 hashes of
  session tokens and recovery codes, and the time of failed sign-in attempts
  (deleted after one day). No passwords are stored.
- **Public data:** weather forecasts from MET Norway (cached in the database
  according to MET's terms) and bike availability from Trondheim Bysykkel. These
  contain no personal data.

## Where the data is stored

- The app runs on **Vercel**, with server functions in Frankfurt, Germany (`fra1`).
  Vercel keeps short-lived request logs. The app never writes secrets or
  personal data to these logs.
- The database is **Neon** Postgres in Frankfurt, Germany (AWS `eu-central-1`).

All data stays within the EU.

## How the data is used

The data is only shown to the developer on the dashboard. It is not sold, shared
or used for anything else, and it is not used to train any model.

## Retention

Health data, habits and weekly notes are kept until the developer deletes them.
Sessions expire after 90 days without use. Sign-in challenges expire after five
minutes.

## Storage of credentials

Database URLs, the Google OAuth client and refresh token, and the session secret
are stored as encrypted environment variables in Vercel and are never committed
to the source code repository. The API key used by the iPhone shortcut is stored
only as a hash and can be revoked at any time.

## Revoking access

Access to Google Calendar can be revoked at any time at
<https://myaccount.google.com/permissions>.

## Contact

jonathan.adlandsvik@gmail.com
