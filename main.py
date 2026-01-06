MAX_PLAYERS_PER_TEE = 4  # max players allowed in a single tee time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List
from datetime import datetime, date, time, timedelta

app = FastAPI(
    title="TeeTime AI Backend – TeeSheet v1",
    description="Simple tee sheet backend for a golf-course AI phone agent.",
    version="1.1.0",
)

# Allow your HTML (file://) page to call the API in the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Course setup ----------

class Course(BaseModel):
    id: str
    name: str
    first_time: time
    last_time: time
    interval_minutes: int


COURSES: Dict[str, Course] = {
    "sterling_hills": Course(
        id="sterling_hills",
        name="Sterling Hills Golf Club",
        first_time=time(hour=7, minute=0),   # 7:00 AM
        last_time=time(hour=17, minute=0),   # 5:00 PM
        interval_minutes=8,                  # every 8 minutes
    )
}


# ---------- Booking models ----------

class Booking(BaseModel):
    booking_id: str
    course_id: str
    date_time: datetime
    players: int
    holes: int
    walk_ride: str
    name: str
    phone: str


BOOKINGS: Dict[str, Booking] = {}


class CreateBookingRequest(BaseModel):
    course_id: str = Field(example="sterling_hills")
    date_time: datetime = Field(
        description="ISO datetime like 2025-12-21T07:20:00",
        example="2025-12-21T07:20:00",
    )
    players: int = Field(gt=0, le=4, example=4)
    holes: int = Field(default=18, example=18)
    walk_ride: str = Field(default="riding", example="riding")
    name: str = Field(example="Raj Hundal")
    phone: str = Field(example="+18057960471")


class AvailabilityResponse(BaseModel):
    course_id: str
    date: date
    available_times: List[datetime]


# ---------- Helper to build tee sheet ----------

def _generate_slots_for_date(course: Course, d: date) -> List[datetime]:
    slots: List[datetime] = []
    current = datetime.combine(d, course.first_time)
    last_dt = datetime.combine(d, course.last_time)
    step = timedelta(minutes=course.interval_minutes)

    while current <= last_dt:
        slots.append(current)
        current += step

    return slots


# ---------- Endpoints ----------

@app.get("/availability", response_model=AvailabilityResponse)
def get_availability(
    course_id: str,
    date: date,
    time_window: str = "all",
    players: int = 4,
    holes: int = 18,
    walk_ride: str = "riding",
):
    """
    Return all available tee times for a date for one course.
    """
    if course_id not in COURSES:
        raise HTTPException(status_code=404, detail="Unknown course_id")

    course = COURSES[course_id]

       # How many players are already booked in each tee time
    players_by_time: dict[datetime, int] = {}
    for b in BOOKINGS.values():
        if b.course_id == course_id and b.date_time.date() == date:
            players_by_time[b.date_time] = players_by_time.get(b.date_time, 0) + b.players

    # Only keep tee times where this group still fits in capacity
    available = []
    for dt in all_slots:
        already = players_by_time.get(dt, 0)
        if already + players <= MAX_PLAYERS_PER_TEE:
            available.append(dt)

    # Optional time-window filter
    if time_window != "all":
        if time_window == "morning":
            available = [dt for dt in available if dt.hour < 12]
        elif time_window == "afternoon":
            available = [dt for dt in available if 12 <= dt.hour < 17]
        elif time_window == "evening":
            available = [dt for dt in available if dt.hour >= 17]
        else:
            raise HTTPException(status_code=400, detail="Invalid time_window")

    return AvailabilityResponse(
        course_id=course_id,
        date=date,
        available_times=available,
    )


@app.post("/booking", response_model=Booking)
def create_booking(req: CreateBookingRequest):
    """
    Create a booking for a specific tee time.
    Prevents double-booking the same course/date_time.
    """
    if req.course_id not in COURSES:
        raise HTTPException(status_code=404, detail="Unknown course_id")

       # How many players are already booked into this exact tee time
    current_players = 0
    for b in BOOKINGS.values():
        if b.course_id == req.course_id and b.date_time == req.date_time:
            current_players += b.players

    # Block if this booking would exceed capacity
    if current_players + req.players > MAX_PLAYERS_PER_TEE:
        raise HTTPException(
            status_code=400,
            detail="That tee time is full. Please choose another time.",
        )

    booking_id = f"BOOK-{len(BOOKINGS) + 1}"

    booking = Booking(
        booking_id=booking_id,
        **req.model_dump(),
    )
    BOOKINGS[booking_id] = booking

    return booking


@app.get("/bookings", response_model=List[Booking])
def list_bookings(course_id: str | None = None):
    """
    List all bookings, or bookings for a specific course if course_id is given.
    """
    if course_id:
        return [b for b in BOOKINGS.values() if b.course_id == course_id]
    return list(BOOKINGS.values())
