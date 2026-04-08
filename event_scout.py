"""
FlowTribes Scout - Event Finder Module
Discovers movement, fitness, and flow events across India and globally.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional
import json
import re
import time
import yaml


@dataclass
class Event:
    """Represents a discovered movement/fitness event."""
    name: str
    date: str
    location: str
    city: str
    country: str
    event_type: str
    url: str
    source: str
    description: str = ""
    organizer: str = ""
    contact_email: str = ""
    application_url: str = ""
    deadline: str = ""
    status: str = "discovered"  # discovered, interested, applied, accepted, rejected
    notes: str = ""
    discovered_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return asdict(self)


class EventScout:
    """Searches for movement and fitness events across multiple platforms."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        self.search_config = self.config["search"]
        self.events = []

    def search_all(self):
        """Run all search strategies and return combined results."""
        self.events = []
        self._search_eventbrite()
        self._search_insider_in()
        self._search_animal_flow_official()
        self._search_meetup()
        self._search_generic_fitness_events()
        return self.events

    def search_by_region(self, region="India"):
        """Search events filtered by region."""
        all_events = self.search_all()
        return [e for e in all_events if region.lower() in e.location.lower()
                or region.lower() in e.country.lower()]

    def _safe_request(self, url, params=None, timeout=15):
        """Make a safe HTTP request with error handling."""
        try:
            resp = requests.get(url, headers=self.HEADERS, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            print(f"  [!] Request failed for {url}: {e}")
            return None

    def _search_eventbrite(self):
        """Search Eventbrite for movement/fitness events in India."""
        print("  Searching Eventbrite...")
        queries = [
            "animal+flow+workshop",
            "movement+workshop",
            "functional+fitness+event",
            "calisthenics+workshop",
            "flow+arts+festival",
            "bodyweight+training",
        ]
        for city in self.search_config["india_cities"][:5]:
            for query in queries[:3]:
                url = f"https://www.eventbrite.com/d/india--{city.lower()}/{query}/"
                resp = self._safe_request(url)
                if not resp:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("[data-testid='event-card']") or soup.select(".eds-event-card-content__content")
                for card in cards[:5]:
                    title_el = card.select_one("h2, h3, .eds-event-card-content__title")
                    link_el = card.select_one("a[href]")
                    date_el = card.select_one("[data-testid='event-card-date'], .eds-event-card-content__sub-title")
                    if title_el:
                        self.events.append(Event(
                            name=title_el.get_text(strip=True),
                            date=date_el.get_text(strip=True) if date_el else "TBA",
                            location=city,
                            city=city,
                            country="India",
                            event_type="workshop",
                            url=link_el["href"] if link_el else url,
                            source="Eventbrite",
                            description="",
                        ))
                time.sleep(0.5)

    def _search_insider_in(self):
        """Search Insider.in for fitness events in India."""
        print("  Searching Insider.in...")
        queries = ["fitness", "workshop", "yoga", "wellness"]
        for query in queries:
            url = f"https://insider.in/search?q={query}"
            resp = self._safe_request(url)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(".card, .event-card, [class*='EventCard']")
            for card in cards[:5]:
                title_el = card.select_one("h3, h4, .card-title, [class*='title']")
                link_el = card.select_one("a[href]")
                if title_el:
                    self.events.append(Event(
                        name=title_el.get_text(strip=True),
                        date="TBA",
                        location="India",
                        city="",
                        country="India",
                        event_type="fitness event",
                        url=f"https://insider.in{link_el['href']}" if link_el and not link_el["href"].startswith("http") else (link_el["href"] if link_el else url),
                        source="Insider.in",
                    ))
            time.sleep(0.5)

    def _search_animal_flow_official(self):
        """Search official Animal Flow site for workshops."""
        print("  Searching Animal Flow Official...")
        url = "https://animalflow.com/events/category/india/"
        resp = self._safe_request(url)
        if not resp:
            return
        soup = BeautifulSoup(resp.text, "html.parser")
        events = soup.select(".tribe-events-calendar-list__event, .type-tribe_events, .tribe-common-g-row")
        for event in events[:10]:
            title_el = event.select_one("h3, .tribe-events-calendar-list__event-title, a.tribe-event-url")
            date_el = event.select_one("time, .tribe-events-calendar-list__event-datetime, .tribe-event-schedule-details")
            link_el = event.select_one("a[href*='animalflow']")
            loc_el = event.select_one(".tribe-events-calendar-list__event-venue, .tribe-venue")
            if title_el:
                name = title_el.get_text(strip=True)
                self.events.append(Event(
                    name=name,
                    date=date_el.get_text(strip=True) if date_el else "TBA",
                    location=loc_el.get_text(strip=True) if loc_el else "India",
                    city="",
                    country="India",
                    event_type="Animal Flow Workshop",
                    url=link_el["href"] if link_el else url,
                    source="Animal Flow Official",
                    organizer="Animal Flow",
                ))

    def _search_meetup(self):
        """Search Meetup for movement-related groups and events."""
        print("  Searching Meetup...")
        queries = ["animal-flow", "functional-fitness", "calisthenics", "movement-culture"]
        for query in queries:
            url = f"https://www.meetup.com/find/?keywords={query}&location=India"
            resp = self._safe_request(url)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("[data-testid='categoryResults-eventCard'], .eventCard, [id*='event']")
            for card in cards[:5]:
                title_el = card.select_one("h2, h3, [class*='title']")
                link_el = card.select_one("a[href]")
                if title_el:
                    self.events.append(Event(
                        name=title_el.get_text(strip=True),
                        date="TBA",
                        location="India",
                        city="",
                        country="India",
                        event_type="meetup",
                        url=link_el["href"] if link_el else url,
                        source="Meetup",
                    ))
            time.sleep(0.5)

    def _search_generic_fitness_events(self):
        """Search for major fitness expos and festivals globally."""
        print("  Searching global fitness events...")
        known_events = [
            Event(
                name="FIBO Global Fitness",
                date="April 2026",
                location="Cologne, Germany",
                city="Cologne",
                country="Germany",
                event_type="fitness expo",
                url="https://www.fibo.com/",
                source="Known Events DB",
                description="World's largest fitness trade show. Great for workshop submissions.",
            ),
            Event(
                name="India Fitness Expo",
                date="2026",
                location="Mumbai, India",
                city="Mumbai",
                country="India",
                event_type="fitness expo",
                url="https://www.indiafitnessexpo.com/",
                source="Known Events DB",
                description="India's premier fitness industry trade show.",
            ),
            Event(
                name="Goa Flow Festival",
                date="2026",
                location="Goa, India",
                city="Goa",
                country="India",
                event_type="flow arts festival",
                url="",
                source="Known Events DB",
                description="Flow arts and movement community gathering in Goa.",
            ),
            Event(
                name="International Yoga Festival Rishikesh",
                date="March 2026",
                location="Rishikesh, India",
                city="Rishikesh",
                country="India",
                event_type="yoga festival",
                url="https://www.internationalyogafestival.org/",
                source="Known Events DB",
                description="Annual yoga festival — great venue for movement workshops.",
            ),
            Event(
                name="Bangalore Fitness Expo",
                date="2026",
                location="Bangalore, India",
                city="Bangalore",
                country="India",
                event_type="fitness expo",
                url="",
                source="Known Events DB",
                description="South India's fitness and wellness expo.",
            ),
            Event(
                name="Asia Fitness Conference",
                date="2026",
                location="Bangkok, Thailand",
                city="Bangkok",
                country="Thailand",
                event_type="fitness conference",
                url="https://www.asiafitconf.com/",
                source="Known Events DB",
                description="Asia's biggest fitness conference. Workshop presenter applications open.",
            ),
            Event(
                name="Flow Fest",
                date="2026",
                location="Fort Lauderdale, USA",
                city="Fort Lauderdale",
                country="USA",
                event_type="flow arts festival",
                url="https://flowfests.com/",
                source="Known Events DB",
                description="Flow arts community festival — fire, movement, dance.",
            ),
            Event(
                name="Movement Culture Workshop Series",
                date="Various 2026",
                location="Various, India",
                city="",
                country="India",
                event_type="movement workshop",
                url="",
                source="Known Events DB",
                description="Ido Portal-inspired movement culture workshops across India.",
            ),
        ]
        self.events.extend(known_events)

    def deduplicate(self):
        """Remove duplicate events based on name similarity."""
        seen = set()
        unique = []
        for event in self.events:
            key = re.sub(r'\s+', ' ', event.name.lower().strip())
            if key not in seen:
                seen.add(key)
                unique.append(event)
        self.events = unique
        return self.events

    def filter_events(self, country=None, event_type=None, keyword=None):
        """Filter events by criteria."""
        results = self.events
        if country:
            results = [e for e in results if country.lower() in e.country.lower()]
        if event_type:
            results = [e for e in results if event_type.lower() in e.event_type.lower()]
        if keyword:
            results = [e for e in results if keyword.lower() in e.name.lower()
                       or keyword.lower() in e.description.lower()]
        return results

    def export_json(self, filepath="events.json"):
        """Export all events to JSON."""
        with open(filepath, "w") as f:
            json.dump([e.to_dict() for e in self.events], f, indent=2)
        return filepath
