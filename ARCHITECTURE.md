# Room Booking System

Generated from a whiteboard photo by Whiteboard2Repo (Meta Muse Spark Open).

```mermaid
flowchart LR
  web_app(["Web App"])
  booking_api["Booking API"]
  rooms_db[("Rooms DB")]
  notifier["Notifier"]
  email(("Email"))
  web_app --> booking_api
  booking_api -->|"SQL"| rooms_db
  booking_api -.->|"booking.created"| notifier
  notifier --> email
```

## Invariants from the board
- The system must reject any booking that overlaps in time with an existing confirmed booking for the same room.
