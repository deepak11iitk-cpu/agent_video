"""
FlowTribes AI Agent — the actual agent.

Uses Claude Opus 4.7 with web search and tool use to intelligently find,
reason about, and save movement events. This is what makes it an "agent"
vs. just a scraper — it decides what to search for, evaluates relevance,
extracts structured data, and takes actions.
"""

import os
import json
from typing import Optional

import anthropic
from anthropic import beta_tool

from tracker import EventTracker
from proposal import ProposalGenerator


# ---------------------------------------------------------------------------
# Tools the agent can call
# ---------------------------------------------------------------------------

_tracker = EventTracker()
_proposal_gen = ProposalGenerator()


@beta_tool
def save_event(
    name: str,
    date: str,
    location: str,
    country: str,
    event_type: str,
    description: str = "",
    url: str = "",
    organizer: str = "",
    contact_email: str = "",
) -> str:
    """Save a discovered movement, fitness, yoga, or flow event to the FlowTribes tracker database.

    Use this whenever you find a relevant event from web search. Only save events that
    are actually relevant to flow-based movement, fitness workshops, yoga festivals,
    calisthenics meetups, or similar — not generic concerts or unrelated events.

    Args:
        name: The official event name.
        date: Event date or date range (e.g., "March 15-17, 2026" or "2026").
        location: Full location (city, country).
        country: Country name only.
        event_type: Type (e.g., "yoga festival", "fitness expo", "movement workshop").
        description: Brief description — what happens, who it's for.
        url: Event website or listing URL.
        organizer: Organizer name if known.
        contact_email: Contact email if found.
    """
    city = location.split(",")[0].strip() if "," in location else location
    event_dict = {
        "name": name,
        "date": date,
        "location": location,
        "city": city,
        "country": country,
        "event_type": event_type,
        "description": description,
        "url": url,
        "organizer": organizer,
        "contact_email": contact_email,
        "source": "AI Agent (web search)",
        "status": "discovered",
    }
    ok = _tracker.add_event(event_dict)
    if ok:
        return f"Saved event '{name}' to tracker."
    return f"Event '{name}' already in tracker (skipped duplicate)."


@beta_tool
def list_saved_events(country: str = "", keyword: str = "") -> str:
    """List events already saved in the FlowTribes tracker. Use to check what's
    already been discovered before doing duplicate searches, or to retrieve event
    IDs for proposal generation.

    Args:
        country: Filter by country name (empty = all countries).
        keyword: Keyword filter on name/description (empty = no filter).
    """
    events = _tracker.get_all_events()
    if country:
        events = [e for e in events if country.lower() in e.get("country", "").lower()]
    if keyword:
        kw = keyword.lower()
        events = [
            e for e in events
            if kw in e.get("name", "").lower() or kw in e.get("description", "").lower()
        ]

    if not events:
        return "No events found matching those filters."

    lines = [f"Found {len(events)} events:"]
    for e in events[:30]:
        lines.append(
            f"  #{e['id']} | {e['name']} | {e['date']} | {e['location']} "
            f"| {e['event_type']} | status={e['status']}"
        )
    return "\n".join(lines)


@beta_tool
def generate_proposal_for_event(event_id: int, workshop_type: str = "Flow Fusion Workshop") -> str:
    """Generate a workshop proposal for a specific saved event.

    Args:
        event_id: The event ID from the tracker.
        workshop_type: One of: "Intro to Animal Flow", "Flow Fusion Workshop",
            "Advanced Flow Lab", "Corporate Wellness - Movement Break".
    """
    event = _tracker.get_event(event_id)
    if not event:
        return f"Event #{event_id} not found."
    proposal = _proposal_gen.generate_email(event, workshop_type)
    _tracker.save_application(event_id, workshop_type, proposal)
    return f"Proposal drafted for '{event['name']}':\n\n{proposal}"


# ---------------------------------------------------------------------------
# The agent itself
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the FlowTribes Scout Agent — an autonomous AI agent helping Deepak
(Instagram: @flowtribes) find workshop opportunities for his movement practice.

WHAT FLOWTRIBES DOES:
- Animal Flow (ground-based quadrupedal movement)
- Row Flow (flow-based rowing/pulling patterns)
- Maze Flow (complex multi-directional movement patterns)
- Corporate wellness sessions
- Workshops for all skill levels

YOUR JOB:
When the user asks you to find events, you should:
1. Use web_search to find REAL, CURRENT events matching their criteria
2. Focus on: movement workshops, yoga festivals, fitness expos, wellness retreats,
   flow arts gatherings, calisthenics meetups, functional training events
3. Prioritize events in India, then Asia, then global
4. For each relevant event you find, CALL save_event to add it to the tracker
5. Extract concrete details: real dates, real locations, real URLs
6. Skip events that aren't relevant (unrelated concerts, general tourism, etc.)

WHEN FINDING EVENTS:
- Do multiple searches with different keywords for thoroughness
- Try city-specific searches (e.g., "Mumbai yoga festival 2026")
- Try category searches (e.g., "animal flow workshop India 2026")
- Look for events with open applications for workshop facilitators

BE PROACTIVE:
- If the user asks generally ("find events"), search broadly across India + global
- If they specify a city/type, focus there
- Always save what you find, then summarize the results at the end

STYLE:
- Conversational, warm (use Deepak's name occasionally)
- Brief summaries with bullet points
- If you save events, tell the user how many and highlight the most interesting ones
- Use emojis sparingly (🌍 🇮🇳 📅 📍 are fine)
"""


class FlowTribesAgent:
    """AI agent using Claude + web search + tools to find movement events."""

    def __init__(self, api_key: Optional[str] = None):
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = "claude-opus-4-7"

    def run(self, user_message: str, max_iterations: int = 10) -> str:
        """Run the agent on a user message and return its final text response.

        Uses the tool runner which handles the agentic loop automatically —
        web search, tool calls, and iteration until the agent is done.
        """
        tools = [
            # Server-side web search — Anthropic runs the queries
            {"type": "web_search_20260209", "name": "web_search"},
            # Our local tools — save events, list events, generate proposals
            save_event,
            list_saved_events,
            generate_proposal_for_event,
        ]

        runner = self.client.beta.messages.tool_runner(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=[{"role": "user", "content": user_message}],
            max_iterations=max_iterations,
        )

        final_text_parts = []
        for message in runner:
            for block in message.content:
                if block.type == "text" and block.text:
                    final_text_parts.append(block.text)

        return "\n\n".join(final_text_parts).strip() or "Done."


# ---------------------------------------------------------------------------
# CLI entry point (standalone mode)
# ---------------------------------------------------------------------------

def main():
    """Run the agent from the command line."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("=" * 60)
        print("  FlowTribes AI Agent")
        print("=" * 60)
        print()
        print("  Get an API key at https://console.anthropic.com/")
        print()
        print("    export ANTHROPIC_API_KEY='sk-ant-...'")
        print("    python agent.py 'find animal flow workshops in India'")
        print()
        print("=" * 60)
        return

    import sys
    if len(sys.argv) < 2:
        print("Usage: python agent.py '<your question>'")
        print("Example: python agent.py 'find yoga festivals in India for 2026'")
        return

    user_msg = " ".join(sys.argv[1:])
    agent = FlowTribesAgent()
    print(f"\nUser: {user_msg}\n")
    print("Agent is thinking and searching the web...\n")
    response = agent.run(user_msg)
    print(response)


if __name__ == "__main__":
    main()
