# Room Booking System

Generated from a whiteboard photo by Whiteboard2Repo (Meta Muse Spark Open).

```mermaid
flowchart LR
  web_app(["Web App"])
  booking_api["Booking API"]
  payments_api(("Payments API"))
  notifier["Notifier"]
  email(("Email"))
  rooms_db[("Rooms DB")]
  web_app --> booking_api
  booking_api -->|"charge / REST"| payments_api
  booking_api -.->|"booking.created"| notifier
  notifier --> email
  booking_api -->|"SQL"| rooms_db
```

## Invariants from the board
- The system must reject a new booking if the user already has 3 active bookings
- The system must prevent overlapping bookings for the same room - a room cannot be booked twice for the same time slot
