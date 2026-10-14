# 📻 Office Jukebox

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.x-darkgreen.svg)](https://www.djangoproject.com/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%20(Neon)%20%7C%20SQLite-indigo.svg)](https://neon.tech/)
[![Frontend](https://img.shields.io/badge/Frontend-Vanilla%20JS%20%2B%20CSS3-yellow.svg)]()
[![Deployment](https://img.shields.io/badge/Deployment-Render-black.svg)](https://render.com/)

A modern, production-ready, centralized web application designed to resolve office music disputes. All colleagues on the same office network share a single collaborative queue, vote on tracks, and enjoy music through a designated office speaker without fighting over playlist control.

---

## 🌟 Key Features

1. **Automatic Office Room Resolution by IP**
   - Detects the client's public network IP respecting trusted reverse proxies.
   - Automatically groups all employees on the same office Wi-Fi or subnet into the same shared office room.
   - Manual room code support for VPNs, remote employees, or multiple office branches.

2. **YouTube Music Search (Data API v3)**
   - Search millions of songs by title, artist, album, or direct YouTube URL.
   - Embeddability and availability verified server-side.
   - In-memory result caching (15-minute TTL) and per-user rate limiting to protect API quota.
   - No audio downloading or extraction — uses official YouTube IFrame Player API.

3. **Democratic Shared Queue & Fair-Play Algorithm**
   - **Vote Priority**: Songs with higher upvotes get priority.
   - **Fair-Turn Tie-Breaker**: When votes are tied, prioritize colleagues who have had fewer recent plays.
   - **FIFO Ordering**: Earlier added tracks play first when votes and plays are equal.
   - **Active Song Limits**: Configurable cap (default 3) on simultaneous active tracks per user.
   - **Cooldown Timer**: Prevents an employee from flooding the queue.
   - **Duplicate Prevention**: Rejects duplicate songs while active or playing.

4. **Dedicated Speaker Player Mode**
   - Designed for the designated office PC connected to the office sound system.
   - Embeds YouTube IFrame Player with full autoplay policy compliance (one-click gesture initialization).
   - Auto-recovers from broken, restricted, or deleted videos by skipping to the next song.
   - Live heartbeat reporting so all office computers can see if the office speaker is active.

5. **Moderator Panel & Audit Logs**
   - Optional PIN protection for room administration.
   - Force-skip inappropriate or disruptive tracks.
   - Adjust fair-play settings (limits, cooldowns, polling intervals) on the fly.
   - Tamper-evident audit log tracking every skip, delete, and settings change.

6. **Real-Time Polling Synchronization**
   - Efficient state hashing: clients poll every 3 seconds (configurable) and only re-render the DOM when queue or player state changes.
   - Row-level database transactions (`select_for_update`) to prevent race conditions during concurrent voting or track advancement.

7. **Modern Dark Theme UI**
   - Responsive design for mobile phones, laptops, and large TV displays.
   - Animated audio equalizer bars, modal video preview, glassmorphism badges, and toast alerts.

---

## 🏗️ Tech Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Backend** | Python 3.10+, Django 5.x | High-performance ORM, CSRF protection, sessions, transaction control |
| **Frontend** | Django Templates, HTML5, CSS3, Vanilla JS | Zero npm/React dependencies, lightweight, responsive dark mode |
| **Database** | PostgreSQL (Neon / Supabase) | Managed Postgres with pooling; automatic SQLite fallback for local development |
| **Search API** | YouTube Data API v3 | Server-side video metadata, duration parsing, embed checks |
| **Playback** | YouTube IFrame Player API | Official client-side player adhering to YouTube Terms of Service |
| **Static Files** | WhiteNoise | Compressed, hash-cached static file serving directly through WSGI |
| **Deployment** | Render (Procfile, `build.sh`, `render.yaml`) | Gunicorn WSGI server ready for cloud containers |

---

## 📁 Project Structure

```
office_jukebox/
├── manage.py                   # Django CLI management
├── requirements.txt            # Python dependencies
├── Procfile                    # Web process command for Render/Heroku
├── build.sh                    # Build script (pip install, collectstatic, migrate)
├── render.yaml                 # Infrastructure-as-code Blueprint for Render
├── .env.example                # Sample environment configuration
├── .gitignore                  # Git ignore rules
├── README.md                   # Full documentation
├── jukebox/
│   ├── __init__.py
│   ├── settings.py             # Database URL, WhiteNoise, Security, YouTube config
│   ├── urls.py                 # Root URL router
│   ├── wsgi.py                 # WSGI application entry point
│   └── asgi.py                 # ASGI application entry point
├── music/
│   ├── __init__.py
│   ├── models.py               # Room, Settings, Participant, QueueItem, Vote, PlayerState, AuditLog
│   ├── views.py                # Template views and JSON REST API endpoints
│   ├── urls.py                 # URL patterns (/room/, /player/, /api/...)
│   ├── services.py             # YouTubeService (API v3) and QueueService (fair-play logic)
│   ├── forms.py                # Join, Create Room, Settings, and Moderator PIN forms
│   ├── admin.py                # Django admin registration
│   ├── utils.py                # IP detection, IP masking, ISO 8601 duration parser
│   ├── context_processors.py   # Global template context (identity, detected IP)
│   ├── tests.py                # 17 automated unit and integration tests
│   └── migrations/
│       └── 0001_initial.py     # Initial database schema
├── templates/
│   ├── base.html               # App shell, navigation, toasts, status badges
│   ├── welcome.html            # Display name onboarding & IP room auto-join
│   ├── create_room.html        # Custom room creation
│   ├── dashboard.html          # Main search, live queue, upvoting, and preview
│   ├── player.html             # Dedicated speaker player mode
│   └── moderator.html          # Moderator controls, settings, and audit log
└── static/
    ├── css/
    │   └── style.css           # Modern dark theme styles
    └── js/
        ├── app.js              # Dashboard polling, search debouncing, voting
        └── player.js           # YouTube IFrame player integration & heartbeats
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10, 3.11, 3.12, 3.13, or 3.14
- Git
- (Optional) Free Neon PostgreSQL database account
- (Optional) Free Google Cloud Console YouTube Data API v3 key

---

### 2. Local Installation

#### **On Windows (PowerShell):**
```powershell
# 1. Clone repository and enter directory
git clone https://github.com/gitmanhimanshu/office-jukebox.git
cd office-jukebox

# 2. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment file
cp .env.example .env

# 5. Apply migrations (defaults to SQLite if DATABASE_URL is empty)
python manage.py migrate

# 6. Run the automated test suite
python manage.py test

# 7. Start the development server
python manage.py runserver
```

#### **On macOS / Linux:**
```bash
# 1. Clone repository and enter directory
git clone https://github.com/gitmanhimanshu/office-jukebox.git
cd office-jukebox

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment file
cp .env.example .env

# 5. Apply migrations
python manage.py migrate

# 6. Run tests
python manage.py test

# 7. Start server
python manage.py runserver
```

Open your browser at **`http://localhost:8000/`**.

---

## 🔑 Configuration & Environment Variables

Create a `.env` file in the project root:

```env
# Security
SECRET_KEY=generate-a-strong-random-key-in-production
DEBUG=True
ALLOWED_HOSTS=*

# Database: Leave blank for local SQLite fallback.
# For Neon PostgreSQL:
DATABASE_URL=postgresql://neondb_owner:YOUR_PASSWORD@ep-cool-pond-123456.us-east-2.aws.neon.tech/neondb?sslmode=require

# YouTube Data API v3 Key (Obtain from Google Cloud Console)
YOUTUBE_API_KEY=AIzaSyYourYouTubeDataApiKeyHere

# Reverse Proxy (Set to 1 on Render, Cloudflare, NGINX)
NUM_PROXIES=1

# CSRF Trusted Origins (comma-separated, include https://)
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,https://office-jukebox.onrender.com

# Timezone
TIME_ZONE=UTC
```

---

## ☁️ Neon PostgreSQL Setup

1. Sign up for free at [neon.tech](https://neon.tech).
2. Create a new project (e.g. `office-jukebox`).
3. In the Neon Dashboard, copy the connection string under **Connection Details**.
4. Select **PostgreSQL** connection string (ensure `sslmode=require` is present):
   ```
   postgresql://user:password@ep-sample-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
5. Paste it into your `.env` or cloud provider environment settings as `DATABASE_URL`.
6. Run `python manage.py migrate`. Django automatically detects Postgres and applies migrations cleanly.

---

## 🎥 YouTube Data API v3 Setup

1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g. `Office Jukebox`).
3. Go to **APIs & Services** > **Library**.
4. Search for **YouTube Data API v3** and click **Enable**.
5. Go to **APIs & Services** > **Credentials**.
6. Click **Create Credentials** > **API Key**.
7. *(Recommended)* Click **Edit API Key** and restrict usage to **YouTube Data API v3**.
8. Copy the key and paste it as `YOUTUBE_API_KEY` in your `.env`.

> 💡 **Free Tier Note**: Google provides 10,000 free quota units per day for YouTube Data API v3. Search queries consume 100 units. Office Jukebox caches search results for 15 minutes, allowing approximately 100-300 unique searches daily on the free tier.

---

## 🚢 Render Deployment (Step-by-Step)

### Option A: 1-Click Blueprint (Recommended)
1. Fork or push this repository to your GitHub account.
2. In [Render Dashboard](https://dashboard.render.com/), click **New** > **Blueprint**.
3. Select this repository. Render will automatically read `render.yaml`.
4. Fill in the prompted environment variables:
   - `DATABASE_URL` (your Neon connection string)
   - `YOUTUBE_API_KEY` (your Google API key)
5. Click **Apply**. Render will run `build.sh` and start the web app with `gunicorn`.

### Option B: Manual Web Service
1. In Render, select **New** > **Web Service**.
2. Connect your GitHub repository.
3. Settings:
   - **Environment**: `Python 3`
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn jukebox.wsgi:application`
4. In **Environment Variables**, add:
   - `SECRET_KEY`: (Click generate)
   - `DEBUG`: `False`
   - `ALLOWED_HOSTS`: `.onrender.com`
   - `CSRF_TRUSTED_ORIGINS`: `https://your-service-name.onrender.com`
   - `DATABASE_URL`: `postgresql://...`
   - `YOUTUBE_API_KEY`: `AIza...`
   - `NUM_PROXIES`: `1`
5. Click **Create Web Service**.

---

## ⚖️ Queue Priority & Fair-Play Deep Dive

```
Queue Sorting Logic:
1. Primary: Net Votes DESC (-vote_count)
2. Secondary (Fair-Turn Mode): Recent Plays ASC (users with fewer played songs in the last 2h play first)
3. Tertiary (Tie-Breaker): FIFO ASC (created_at)
```

- **Fairness Example**:
  - Alice adds Song A (1 vote). Alice has had 2 songs played in the last hour.
  - Bob adds Song B (1 vote). Bob has had 0 songs played today.
  - *Result*: Bob's Song B is placed before Alice's Song A even though Alice added hers first.
- **Vote Override**:
  - If Alice's song receives a second vote from Charlie (2 votes), Alice's song immediately overtakes Bob's (1 vote). Democratic popularity always trumps fairness tie-breakers.

---

## 🔒 Security Architecture

1. **Session-Based Identity**:
   - Each visitor is assigned a secure random UUID stored in an HTTP-only Django cookie.
   - We do **NOT** use public IP addresses for authentication or user permissions.
2. **Reverse Proxy Protection**:
   - `NUM_PROXIES` ensures that untrusted client-supplied `X-Forwarded-For` spoofing is rejected.
3. **CSRF Enforcement**:
   - Every state-altering API call (`POST`) requires a valid CSRF token header (`X-CSRFToken`).
4. **Moderator PIN**:
   - Rooms can be secured with a PIN so that only authorized team members can force-skip tracks or modify settings.

---

## 🧪 Running Automated Tests

Run the full automated test suite with:

```bash
python manage.py test
```

Test coverage includes:
- IP auto-detection and room code fallback
- Mocked YouTube search with embed check and duration conversion
- Missing API key graceful handling
- Duplicate song prevention
- Max active songs cap per user
- Cooldown timer enforcement
- Vote toggling and score recalculation
- FIFO tie-breaking and fair-turn mode priority
- Track advancement and player state lifecycle
- Moderator authorization and security permissions

---

## 📄 License

MIT License. Designed with care for harmonious workspaces everywhere.
