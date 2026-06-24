"""
High School Management System API

A simple FastAPI application that allows students to view and sign up
for extracurricular activities and manage personal schedules.
"""

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

app = FastAPI(
    title="Mergington High School API",
    description="API for viewing and signing up for extracurricular activities and managing personal schedules",
)

# Mount the static files directory
current_dir = Path(__file__).parent
app.mount(
    "/static",
    StaticFiles(directory=current_dir / "static"),
    name="static",
)

db_path = current_dir / "schedule.db"


class ScheduleItemInput(BaseModel):
    name: str = Field(..., title="Schedule item name")
    schedule: str = Field(..., title="Time or schedule description")
    location: str | None = Field(None, title="Optional location")
    notes: str | None = Field(None, title="Optional notes")


class ScheduleItem(BaseModel):
    id: int
    email: EmailStr
    weekday: int
    item_type: str
    name: str
    schedule: str
    location: str | None
    notes: str | None
    created_at: str


def get_db() -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = get_db()
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            weekday INTEGER NOT NULL CHECK(weekday BETWEEN 1 AND 7),
            item_type TEXT NOT NULL CHECK(item_type IN ('lesson', 'extra')),
            name TEXT NOT NULL,
            schedule TEXT NOT NULL,
            location TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(email) REFERENCES users(email) ON DELETE CASCADE
        )
        """
    )
    connection.commit()
    connection.close()


def ensure_user(email: str) -> None:
    db = get_db()
    db.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (email,))
    db.commit()
    db.close()


def validate_weekday(weekday: int) -> None:
    if weekday < 1 or weekday > 7:
        raise HTTPException(status_code=400, detail="Weekday must be between 1 and 7")


def create_schedule_item(email: str, weekday: int, item_type: str, item: ScheduleItemInput) -> ScheduleItem:
    ensure_user(email)
    validate_weekday(weekday)
    db = get_db()
    result = db.execute(
        """
        INSERT INTO schedule_items (email, weekday, item_type, name, schedule, location, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (email, weekday, item_type, item.name, item.schedule, item.location, item.notes),
    )
    db.commit()
    item_id = result.lastrowid
    row = db.execute(
        "SELECT * FROM schedule_items WHERE id = ?", (item_id,),
    ).fetchone()
    db.close()
    return ScheduleItem(**dict(row))


def list_schedule_items(email: str, weekday: int | None = None) -> list[ScheduleItem]:
    ensure_user(email)
    db = get_db()
    if weekday is None:
        rows = db.execute(
            "SELECT * FROM schedule_items WHERE email = ? ORDER BY weekday, created_at",
            (email,),
        ).fetchall()
    else:
        validate_weekday(weekday)
        rows = db.execute(
            "SELECT * FROM schedule_items WHERE email = ? AND weekday = ? ORDER BY created_at",
            (email, weekday),
        ).fetchall()
    db.close()
    return [ScheduleItem(**dict(row)) for row in rows]


def delete_schedule_item(item_id: int, email: str) -> None:
    db = get_db()
    row = db.execute(
        "SELECT id FROM schedule_items WHERE id = ? AND email = ?",
        (item_id, email),
    ).fetchone()
    if row is None:
        db.close()
        raise HTTPException(status_code=404, detail="Schedule item not found")
    db.execute("DELETE FROM schedule_items WHERE id = ?", (item_id,))
    db.commit()
    db.close()


initialize_database()


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/static/index.html")


@app.get("/activities")
def get_activities() -> dict[str, Any]:
    return activities


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(activity_name: str, email: EmailStr):
    """Sign up a student for an activity"""
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    activity = activities[activity_name]

    if email in activity["participants"]:
        raise HTTPException(status_code=400, detail="Student is already signed up")

    activity["participants"].append(email)
    return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(activity_name: str, email: EmailStr):
    """Unregister a student from an activity"""
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    activity = activities[activity_name]

    if email not in activity["participants"]:
        raise HTTPException(status_code=400, detail="Student is not signed up for this activity")

    activity["participants"].remove(email)
    return {"message": f"Unregistered {email} from {activity_name}"}


@app.get("/schedule/{email}/week")
def get_week_schedule(email: EmailStr) -> list[ScheduleItem]:
    return list_schedule_items(email)


@app.get("/schedule/{email}/day/{weekday}")
def get_day_schedule(email: EmailStr, weekday: int) -> list[ScheduleItem]:
    return list_schedule_items(email, weekday)


@app.post("/schedule/{email}/day/{weekday}/lessons")
def add_lesson(email: EmailStr, weekday: int, item: ScheduleItemInput) -> ScheduleItem:
    return create_schedule_item(email, weekday, "lesson", item)


@app.post("/schedule/{email}/day/{weekday}/extras")
def add_extra(email: EmailStr, weekday: int, item: ScheduleItemInput) -> ScheduleItem:
    return create_schedule_item(email, weekday, "extra", item)


@app.delete("/schedule/{email}/item/{item_id}")
def remove_schedule_item(email: EmailStr, item_id: int):
    delete_schedule_item(item_id, email)
    return {"message": f"Deleted schedule item {item_id}"}


# In-memory activity database preserved for compatibility
activities = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"],
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"],
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"],
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"],
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"],
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"],
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"],
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"],
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"],
    },
}
