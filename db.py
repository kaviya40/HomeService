"""MongoDB connection. Collections: users, providers, bookings, reviews, notifications."""
from pymongo import MongoClient, ASCENDING, GEOSPHERE


class Mongo:
    users = providers = bookings = reviews = notifications = None


mongo = Mongo()


def init_db(uri, db_name):
    client = MongoClient(uri, serverSelectionTimeoutMS=6000)
    try:
        client.admin.command("ping")
    except Exception as e:                       # noqa: BLE001
        raise SystemExit(
            "\n❌ Could not connect to MongoDB.\n"
            "   • Check MONGO_USER / MONGO_PASSWORD / MONGO_HOST in your .env file\n"
            "   • On MongoDB Atlas: Network Access must allow your IP address\n"
            f"   Details: {e}\n")
    database = client[db_name]
    print(f"✅ Connected to MongoDB. Database: {db_name}")
    mongo.users = database["users"]
    mongo.providers = database["providers"]
    mongo.bookings = database["bookings"]
    mongo.reviews = database["reviews"]
    mongo.notifications = database["notifications"]

    def safe_index(coll, keys, **kw):
        """Create an index; if old data in the collection blocks it, warn instead of crashing."""
        try:
            coll.create_index(keys, **kw)
        except Exception as e:                   # noqa: BLE001
            print(f"⚠️  Could not create index on {coll.name}: {e}")

    safe_index(mongo.users, [("phone", ASCENDING), ("role", ASCENDING)], unique=True)
    safe_index(mongo.providers, [("user_id", ASCENDING)], unique=True,
               partialFilterExpression={"user_id": {"$type": "objectId"}})
    safe_index(mongo.providers, [("location", GEOSPHERE)])
    safe_index(mongo.bookings, [("customer_id", ASCENDING), ("created_at", -1)])
    safe_index(mongo.bookings, [("provider_id", ASCENDING), ("created_at", -1)])
    safe_index(mongo.reviews, [("provider_id", ASCENDING)])
    safe_index(mongo.notifications, [("recipient_id", ASCENDING), ("created_at", -1)])
    return database
