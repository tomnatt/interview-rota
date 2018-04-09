from bank_holidays import BankHolidays
from calendar_fetcher import CalendarCache, Event
import datetime
import os
import pytz

from common import appointment_calendar_name


utc = pytz.timezone("UTC")
local_time = pytz.timezone("Europe/London")


class Slot(object):
    def __init__(self, date, time, length, new):
        start_localtz = local_time.localize(datetime.datetime(
            year = date.year,
            month = date.month,
            day = date.day,
            hour = int(time[:2]),
            minute = int(time[3:]),
        ))
        self.start = utc.normalize(start_localtz)
        self.end = self.start + datetime.timedelta(minutes = length)
        self.isoweek = self.start.isocalendar()[1]
        self.new = new
        self.event = None

    def __repr__(self):
        return "{} to {} {} {}".format(self.start, self.end, "new" if self.new else "old", self.event)

    def people(self):
        return reduce(lambda x, y: x + y, self.event.attendees.values(), [])

    def can_do_frontend(self):
        return any(person.can_do_frontend_test for person in self.people())

    def placeholder_invitation(self):
        return {
            "summary": "Interview placeholder - keep free - ({})".format(
                "front/backend developer"
                if self.can_do_frontend()
                else "backend developer"
            ),
            "location": "",
            "visibility": "private",
            "anyoneCanAddSelf": True,
            "description": """
Chair: {}

DEVELOPER INTERVIEW SLOT

This is a slot for a developer onsite or telephone interview. This slot has been generated from the list of volunteers and has been selected based on your calendar.

Please confirm your ability to attend now by accepting this invitation.

Recruitment is a priority for GDS, so we expect you to make reasonable efforts to attend interviews as a priority over other activities.

If you really cannot attend, please follow the rearranging interviews process: https://docs.google.com/document/d/1xW8jsK4Cb5MP9mgzZxzgYWzpfJVl_ABpRLliCEr5NcU/edit?usp=sharing

Please keep your calendar up to date; we will try to avoid conflicts when booking the meetings, so it's easier for everyone if you do this.

INTERVIEW FORMAT

Slots are for 2.5 hours, but you may not be required for the full time.

For the face to face interviews, the chair and one other interviewer are required for the first 60 minutes: the third member will join after 60 minutes to complete the panel.

You will receive a calendar invitation from Jobvite closer to the time with details of the interview.

INTERVIEW TRAINING

If you haven't completed at least the unconscious bias e-learning, now's a good time to do so. It only takes about 30 minutes. See https://civilservicelearning.civilservice.gov.uk/learning-opportunities/unconscious-bias-e-learning

If you haven't been on an interview panel for these roles before, please contact the chair of this interview, or if that fails Daniel Wilson or Tom Natt, for an introduction to the process.

            """.strip().format(
                self.people()[0].name,
            ),
            "start": {
                "dateTime": self.event.start.isoformat(),
                "timeZone": "Europe/London",
            },
            "end": {
                "dateTime": self.event.end.isoformat(),
                "timeZone": "Europe/London",
            },
            "attendees": [
                {"email": person.email} for person in self.people()
            ]
        }


class SlotGenerator(object):
    def __init__(self, calendar_fetcher, date_min, min_new_slot_date, date_max, cache_dir):
        self.calendar_fetcher = calendar_fetcher
        self.date_min = date_min
        self.min_new_slot_date = min_new_slot_date
        self.date_max = date_max
        self.bank_holidays = BankHolidays(cache_dir).dates()

    def generate(self):
        self.booked = self.calendar_fetcher.get(appointment_calendar_name)

        for date in self._generate_dates():
            new = (date >= self.min_new_slot_date)
            yield self.associate_event(Slot(date, "10:15", 150, new))
            yield self.associate_event(Slot(date, "14:15", 150, new))

    def associate_event(self, slot):
        for event in self.booked.events:
            if not "interview" in event.summary.lower() and not "booked" in event.summary.lower():
                continue
            if event.intersects_with(slot.start, slot.end):
                slot.event = event

        if slot.new:
            if slot.event is None:
                slot.event = self.make_placeholder_event(slot)
            else:
                slot.new = False
        return slot

    def make_placeholder_event(self, slot):
        event = Event({
            "start": {"dateTime": slot.start.isoformat()},
            "end": {"dateTime": slot.end.isoformat()},
            "summary": "Interview placeholder",
            "description": "",
        }, False)
        event.optional = False
        return event

    def _generate_dates(self):
        date = self.date_min
        while date <= self.date_max:
            if (
                date.weekday() not in (5, 6) and
                date not in self.bank_holidays
            ):
                yield date
            date = date + datetime.timedelta(days=1)


def fetch_slots(calendar_service, cache_dir, days_back, days_forward,
                minimum_warning):
    today = datetime.date.today()
    date_min = today - datetime.timedelta(days=days_back)
    date_max = today + datetime.timedelta(days=days_forward)
    min_new_slot_date = today + datetime.timedelta(days=minimum_warning)

    calendar_fetcher = CalendarCache(
        calendar_service, date_min, date_max, os.path.join(cache_dir, "calendars")
    )

    return list(SlotGenerator(
        calendar_fetcher, date_min, min_new_slot_date, date_max,
        os.path.join(cache_dir, "slots"),
    ).generate())
