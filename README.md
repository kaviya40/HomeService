# HomeServe – Home Service Booking (Flask + MongoDB)

Two separate portals:

| | Customer portal | Provider portal |
|---|---|---|
| Login | `/customer/login` | `/provider/login` |
| Sign up | `/customer/register` | `/provider/register` (creates profile + account) |
| Pages | Find Services (search / category / sort), provider details + map, Book (date, time slot, hours), My Bookings (filter, cancel, track), Review after completed job, Notifications, Profile | Dashboard (stats, earnings), Requests (Accept / Reject / Complete), Gallery (photos + 1 video), Reviews, Profile (price, availability, location), Notifications, Delete account |

A customer cannot open provider pages and a provider cannot open customer pages. Every booking is checked so users only see their own data.

## 1. Install
    pip install -r requirements.txt

## 2. Connect MongoDB
1. Copy `.env.example` to `.env`
2. Fill `MONGO_USER`, `MONGO_PASSWORD`, `MONGO_HOST` (your Atlas cluster host, e.g. `cluster0.abcde.mongodb.net`).
   Special characters in the password are handled automatically.
   Or paste a full `MONGO_URI`. For a local MongoDB, leave MONGO_USER empty.
3. Atlas: Network Access → allow your IP address.

## 3. Run
    python seed.py        # optional demo data (prints demo logins)
    python app.py         # open http://127.0.0.1:5000

Collections (visible in MongoDB Compass under database `homeserve_db`): users, providers, bookings, reviews, notifications.
If you used an older version of this project, keep `MONGO_DB=homeserve_db` (a fresh database) so old data does not mix in.
