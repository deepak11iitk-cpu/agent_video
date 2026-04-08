"""
FlowTribes Scout - Workshop Proposal Generator
Generates professional workshop proposals for event applications.
"""

import yaml
from datetime import datetime


class ProposalGenerator:
    """Generates workshop proposals tailored to specific events."""

    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        self.profile = self.config["profile"]
        self.workshop_types = self.config["proposal"]["workshop_types"]

    def get_workshop_types(self):
        """Return available workshop types."""
        return self.workshop_types

    def generate_proposal(self, event, workshop_type_name=None):
        """
        Generate a full workshop proposal for an event.

        Args:
            event: dict with event details (name, location, date, etc.)
            workshop_type_name: name of workshop type from config, or None for default
        """
        # Find the matching workshop type
        workshop = None
        if workshop_type_name:
            for wt in self.workshop_types:
                if wt["name"].lower() == workshop_type_name.lower():
                    workshop = wt
                    break
        if not workshop:
            workshop = self.workshop_types[0]  # Default to first

        proposal = self._build_proposal(event, workshop)
        return proposal

    def _build_proposal(self, event, workshop):
        """Build the full proposal text."""
        brand = self.profile["brand_name"]
        instructor = self.profile["instructor_name"]
        instagram = self.profile["instagram"]
        email = self.profile.get("email", "[your email]")
        phone = self.profile.get("phone", "[your phone]")
        bio = self.profile["bio"].strip()

        event_name = event.get("name", "[Event Name]")
        event_date = event.get("date", "[Event Date]")
        event_location = event.get("location", "[Event Location]")

        proposal = f"""
{'='*70}
WORKSHOP PROPOSAL — {brand.upper()}
{'='*70}

Date: {datetime.now().strftime('%B %d, %Y')}

To: The Organizers of {event_name}
Re: Workshop Proposal — {workshop['name']}

{'—'*70}

Dear Event Team,

I'm {instructor} from {brand} ({instagram}), and I'd love to bring a
{workshop['name']} workshop to {event_name} ({event_location}, {event_date}).

{brand} specializes in flow-based functional training — a dynamic approach
to movement that combines Animal Flow, Row Flow, and Maze Flow into an
engaging, accessible experience for all fitness levels.

{'—'*70}

WORKSHOP DETAILS
{'—'*70}

  Workshop:     {workshop['name']}
  Duration:     {workshop['duration']}
  Capacity:     {workshop['capacity']}
  Level:        {workshop['level']}

DESCRIPTION:
{workshop['description'].strip()}

{'—'*70}

WHAT PARTICIPANTS WILL LEARN
{'—'*70}

  - Fundamental ground-based movement patterns
  - How to link movements into flowing, creative sequences
  - Mobility and stability techniques for everyday life
  - Bodyweight strength training without equipment
  - How to build their own movement flows

{'—'*70}

REQUIREMENTS
{'—'*70}

  Space:        Indoor or outdoor flat surface (~400 sq ft for 20 people)
  Equipment:    None required (bodyweight only)
  Participants: Comfortable clothing, bare feet or grip socks preferred
  AV:           Small speaker for background music (optional)

{'—'*70}

ABOUT {brand.upper()}
{'—'*70}

{bio}

Connect with us:
  Instagram:  {instagram}
  Email:      {email}
  Phone:      {phone}

{'—'*70}

I'd be happy to discuss scheduling, pricing, and any customization to fit
your event's theme and audience. Looking forward to hearing from you!

Warm regards,
{instructor}
{brand}
{instagram}

{'='*70}
"""
        return proposal.strip()

    def generate_email(self, event, workshop_type_name=None):
        """Generate a concise email pitch (shorter than full proposal)."""
        workshop = None
        if workshop_type_name:
            for wt in self.workshop_types:
                if wt["name"].lower() == workshop_type_name.lower():
                    workshop = wt
                    break
        if not workshop:
            workshop = self.workshop_types[0]

        brand = self.profile["brand_name"]
        instructor = self.profile["instructor_name"]
        instagram = self.profile["instagram"]
        email = self.profile.get("email", "[your email]")

        event_name = event.get("name", "[Event Name]")

        email_text = f"""Subject: Workshop Proposal — {workshop['name']} at {event_name}

Hi there,

I'm {instructor} from {brand} ({instagram}). We run flow-based functional
training workshops combining Animal Flow, Row Flow, and Maze Flow.

I'd love to propose a "{workshop['name']}" session for {event_name}:

  - Duration: {workshop['duration']}
  - Capacity: {workshop['capacity']}
  - Level: {workshop['level']}
  - Equipment: None (bodyweight only)

{workshop['description'].strip()}

We've conducted workshops across India and our sessions are always
high-energy, inclusive, and leave participants with skills they can
practice on their own.

Would love to discuss this further. Happy to share videos of our
past workshops and adapt the format to your event's needs.

Best,
{instructor}
{brand} | {instagram}
{email}
"""
        return email_text.strip()

    def generate_all_proposals(self, event):
        """Generate proposals for all workshop types for a given event."""
        proposals = {}
        for wt in self.workshop_types:
            proposals[wt["name"]] = self.generate_proposal(event, wt["name"])
        return proposals
