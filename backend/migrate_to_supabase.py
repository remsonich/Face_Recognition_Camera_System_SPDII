"""
Helper script to migrate all trained users and face encodings
from local SQLite (sql_app.db) to Supabase Cloud Database.
"""
import sqlite3
from app import database, models


def migrate():
    print("Connecting to local SQLite database (sql_app.db)...")
    con = sqlite3.connect("sql_app.db")
    users = con.execute("SELECT id, username, role, thumbnail, is_active FROM users").fetchall()
    encodings = con.execute("SELECT id, user_id, encoding_data FROM face_encodings").fetchall()
    con.close()

    print(f"Found {len(users)} users and {len(encodings)} face encodings in SQLite.")

    if "sqlite" in database.SQLALCHEMY_DATABASE_URL:
        print("⚠️ Warning: Your DATABASE_URL is currently pointing to local SQLite, not Supabase.")
        print("Please set your real Supabase connection URI in backend/.env first!")
        return

    print(f"Target Database: {database.SQLALCHEMY_DATABASE_URL.split('@')[-1] if '@' in database.SQLALCHEMY_DATABASE_URL else 'Cloud'}")
    print("Pushing data to Supabase...")

    models.Base.metadata.create_all(bind=database.engine)
    db = database.SessionLocal()

    user_id_map = {}
    try:
        for old_id, username, role, thumbnail, is_active in users:
            existing = db.query(models.User).filter(models.User.username == username).first()
            if not existing:
                new_user = models.User(
                    username=username,
                    role=role,
                    thumbnail=thumbnail,
                    is_active=bool(is_active)
                )
                db.add(new_user)
                db.flush()
                user_id_map[old_id] = new_user.id
                print(f"  + Added user: {username} (new ID: {new_user.id})")
            else:
                user_id_map[old_id] = existing.id
                print(f"  = User already in Supabase: {username}")

        for _, old_user_id, encoding_data in encodings:
            if old_user_id in user_id_map:
                new_user_id = user_id_map[old_user_id]
                new_enc = models.FaceEncoding(
                    user_id=new_user_id,
                    encoding_data=encoding_data
                )
                db.add(new_enc)

        db.commit()
        print(f"✅ Successfully migrated {len(users)} users and {len(encodings)} face encodings to Supabase!")

    except Exception as e:
        db.rollback()
        print(f"❌ Migration error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
