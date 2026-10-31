# MySQL Database Setup Guide for Face Recognition System

## Step 1: MySQL Server Installation & Setup

### On macOS (using Homebrew):
```bash
# Install MySQL
brew install mysql

# Start MySQL service
brew services start mysql

# Secure installation (optional but recommended)
mysql_secure_installation
```

### On Windows:
- Download from: https://dev.mysql.com/downloads/mysql/
- Run the installer and follow setup wizard

### On Linux (Ubuntu/Debian):
```bash
sudo apt-get install mysql-server
sudo mysql_secure_installation
```

---

## Step 2: Create Database & User

```bash
# Login to MySQL with root
mysql -u root -p

# When prompted, enter your MySQL root password (default is blank for fresh install)
```

In MySQL console, run:
```sql
-- Create Database
CREATE DATABASE face_recognition_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create dedicated user (recommended for security)
CREATE USER 'face_user'@'localhost' IDENTIFIED BY 'secure_password_here';

-- Grant privileges to user
GRANT ALL PRIVILEGES ON face_recognition_db.* TO 'face_user'@'localhost';

-- Apply changes
FLUSH PRIVILEGES;

-- Exit MySQL
EXIT;
```

---

## Step 3: Update Backend Configuration

### Edit `.env` file in `/backend/` directory:

```env
DATABASE_USER=face_user
DATABASE_PASSWORD=secure_password_here
DATABASE_HOST=localhost
DATABASE_PORT=3306
DATABASE_NAME=face_recognition_db
```

**Important:** Replace `secure_password_here` with the actual password you set in Step 2.

---

## Step 4: Install Python Dependencies

```bash
cd backend/

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install packages
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Step 5: Create Database Tables

Run this Python script to create all tables:

```bash
python -c "
from app.database import Base, engine
from app.models import User, FaceEmbedding, AccessLog

# Create all tables
Base.metadata.create_all(bind=engine)
print('✓ Database tables created successfully!')
"
```

---

## Step 6: Setup DBeaver Connection

### DBeaver Download:
- Visit: https://dbeaver.io/download/
- Download and install DBeaver Community Edition

### Connect to MySQL in DBeaver:

1. **Open DBeaver** → Click "File" → "New Database Connection"
2. **Select MySQL** → Click "Next"
3. **Enter Connection Details:**
   - **Server Host:** `localhost`
   - **Port:** `3306`
   - **Database:** `face_recognition_db`
   - **Username:** `face_user` (or `root`)
   - **Password:** Your MySQL password
   - **Save password locally** ✓

4. **Click "Test Connection"** (if successful, you'll see ✓)
5. **Click "Finish"**

### Verify Tables in DBeaver:

Navigate to:
```
MySQL → face_recognition_db → Tables
```

You should see three tables:
- `users`
- `face_embeddings`
- `access_logs`

---

## Step 7: Run Backend Server

```bash
# Make sure virtual environment is activated
source venv/bin/activate  # or: venv\Scripts\activate on Windows

# Start FastAPI server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

---

## Step 8: Test API Connection

### In Browser:
- Open: http://127.0.0.1:8000/docs

You'll see interactive Swagger documentation where you can test endpoints.

### Test Database Connection:
In Swagger, click on `/api/v1/health` → "Try it out" → "Execute"

---

## Troubleshooting

### Error: "Access denied for user 'face_user'@'localhost'"
- Verify username and password in `.env` file
- Check that user was created correctly in MySQL

### Error: "Can't connect to MySQL server"
- Ensure MySQL is running: `brew services list` (macOS)
- Check if port 3306 is open
- Try: `mysql -u root -p` to verify MySQL works

### Error: "No module named 'pymysql'"
- Reinstall requirements: `pip install -r requirements.txt`

### Tables not created:
```bash
python -c "from app.database import Base, engine; from app.models import *; Base.metadata.create_all(bind=engine)"
```

---

## Database Schema Overview

### `users` Table
```
id (VARCHAR, PK)
full_name (VARCHAR, NOT NULL)
role (VARCHAR, default: 'Employee')
is_active (BOOLEAN, default: True)
created_at (DATETIME)
```

### `face_embeddings` Table
```
id (VARCHAR, PK)
user_id (VARCHAR, FK)
embedding_data (JSON) - Face vector array
created_at (DATETIME)
```

### `access_logs` Table
```
id (VARCHAR, PK)
user_id (VARCHAR, nullable)
match_status (VARCHAR) - SUCCESS/UNKNOWN/NO_FACE
confidence (FLOAT)
timestamp (DATETIME)
```

---

## Next Steps

1. ✓ Database configured and connected
2. Test API endpoints
3. Integrate frontend with backend
4. Test face recognition pipeline
5. Deploy to production

**Questions?** Refer to the main documentation: `face_recognition_camera_system_backend_documentation.md`
