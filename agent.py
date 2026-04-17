"""
FlowTribes Scout - AI Agent Module

Two modes (auto-detected):
  CLI mode  — uses `claude` CLI → works with your $200 Max subscription (no API key)
  API mode  — uses anthropic SDK + web search + tools → needs ANTHROPIC_API_KEY

The bot tries both and uses whichever is available.
"""

import os
import subprocess
import yaml
from typing import Optional

from tracker import EventTracker
from proposal import ProposalGenerator


AGENT_CONTEXT = """\
You are the FlowTribes Scout Agent — an AI assistant helping Deepak
(@flowtribes) discover movement & fitness events and workshop opportunities.

WHAT FLOWTRIBES DOES:
- Animal Flow (ground-based quadrupedal movement)
- Row Flow (flow-based rowing/pulling patterns)
- Maze Flow (complex multi-directional movement patterns)
- Corporate wellness sessions
- Workshops for all skill levels

YOUR JOB:
- Help find movement workshops, yoga festivals, fitness expos, wellness retreats,
  flow arts gatherings, calisthenics meetups, functional training events
- Prioritize India, then Asia, then global
- Help draft compelling workshop proposals and email pitches
- Give strategic advice on which events to apply to

STYLE:
- Conversational, warm, helpful
- Brief and to-the-point (Telegram — keep under 1500 chars)
- Bullet points for event lists
- Reference events by their #ID from the database when relevant
"""


class FlowTribesAgent:
    """AI agent backed by Claude for natural language event discovery and proposals."""

    def __init__(self, config_path="config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.tracker = EventTracker()
        self.proposal_gen = ProposalGenerator(config_path)
        self.mode = self._detect_mode()

    @property
    def available(self):
        return self.mode is not None

    # ------------------------------------------------------------------
    # Mode detection
    # ------------------------------------------------------------------

    def _detect_mode(self):
        """Auto-detect the best available Claude backend."""
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic  # noqa: F401
                return "api"
            except ImportError:
                pass

        try:
            r = subprocess.run(
                ["claude", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                return "cli"
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        return None

    # ------------------------------------------------------------------
    # Context builder (shared by all modes)
    # ------------------------------------------------------------------

    def _event_db_summary(self):
        """Summarize the current event database for prompt context."""
        events = self.tracker.get_all_events()
        stats = self.tracker.get_stats()
        workshops = self.config["proposal"]["workshop_types"]

        lines = [f"EVENT DATABASE: {stats['total']} events tracked."]
        if stats.get("by_status"):
            lines.append(
                "Statuses: "
                + ", ".join(f"{s}={c}" for s, c in stats["by_status"].items())
            )
        if events:
            lines.append("\nTracked events:")
            for e in events[:25]:
                lines.append(
                    f"  #{e['id']} {e['name']} | {e['date']} | "
                    f"{e['location']}, {e['country']} | status={e['status']}"
                )
        lines.append("\nWorkshop types available:")
        for wt in workshops:
            lines.append(f"  - {wt['name']} ({wt['duration']}, {wt['level']})")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, user_message: str) -> str:
        """Handle a free-text message. Returns a string reply."""
        if self.mode == "api":
            return self._run_api(user_message)
        if self.mode == "cli":
            return self._run_cli(user_message)
        return "AI agent not available. Use /scout, /events, /propose."

    def enhance_proposal(self, base_proposal: str, event: dict) -> str:
        """Use AI to improve a template proposal."""
        prompt = (
            "You are a professional workshop proposal writer for FlowTribes.\n\n"
            f"Event: {event.get('name')} at {event.get('location')} "
            f"on {event.get('date', 'TBA')}.\n\n"
            f"Template proposal:\n{base_proposal}\n\n"
            "Rewrite to be more compelling and tailored to this event. "
            "Keep the same structure. Professional but warm. "
            "Output ONLY the improved proposal, nothing else."
        )
        result = self._ask_simple(prompt)
        if result.startswith(("Error", "API error", "Claude error", "Timed out")):
            return base_proposal
        return result

    # ------------------------------------------------------------------
    # CLI mode (Max subscription via `claude` CLI)
    # ------------------------------------------------------------------

    def _run_cli(self, user_message: str) -> str:
        db = self._event_db_summary()
        prompt = (
            f"{AGENT_CONTEXT}\n\n{db}\n\n"
            f"User: {user_message}\n\n"
            "Respond helpfully. Keep it under 1500 characters for Telegram."
        )
        return self._call_cli(prompt)

    def _call_cli(self, prompt: str) -> str:
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            err = result.stderr.strip()
            if any(w in err.lower() for w in ["not authenticated", "login", "sign in"]):
                return (
                    "Claude CLI is not logged in. Run this in your terminal:\n\n"
                    "  claude login\n\n"
                    "Then restart the bot."
                )
            return f"Claude error: {err or 'empty response'}"
        except subprocess.TimeoutExpired:
            return "Timed out — try a shorter question."
        except FileNotFoundError:
            self.mode = None
            return (
                "Claude CLI not found. Install it:\n\n"
                "  npm install -g @anthropic-ai/claude-code\n\n"
                "Or set ANTHROPIC_API_KEY for API mode."
            )
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------------------------
    # API mode (Anthropic API key — full agent with web search + tools)
    # ------------------------------------------------------------------

    def _run_api(self, user_message: str) -> str:
        try:
            return self._run_api_with_tools(user_message)
        except Exception:
            return self._run_api_simple(user_message)

    def _run_api_with_tools(self, user_message: str) -> str:
        """Full agentic loop: web search + database tools."""
        import anthropic
        from anthropic import beta_tool

        tracker = self.tracker
        proposal_gen = self.proposal_gen

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
            """Save a discovered movement, fitness, yoga, or flow event to the
            FlowTribes tracker database. Only save events actually relevant to
            flow-based movement, fitness workshops, yoga festivals, calisthenics
            meetups, or similar."""
            city = location.split(",")[0].strip() if "," in location else location
            ok = tracker.add_event({
                "name": name, "date": date, "location": location,
                "city": city, "country": country, "event_type": event_type,
                "description": description, "url": url, "organizer": organizer,
                "contact_email": contact_email,
                "source": "AI Agent (web search)", "status": "discovered",
            })
            return f"Saved '{name}'." if ok else f"'{name}' already tracked (skipped)."

        @beta_tool
        def list_saved_events(country: str = "", keyword: str = "") -> str:
            """List events already saved in the FlowTribes tracker database."""
            events = tracker.get_all_events()
            if country:
                events = [e for e in events if country.lower() in e.get("country", "").lower()]
            if keyword:
                kw = keyword.lower()
                events = [
                    e for e in events
                    if kw in e.get("name", "").lower()
                    or kw in e.get("description", "").lower()
                ]
            if not events:
                return "No events found matching those filters."
            lines = [f"{len(events)} events:"]
            for e in events[:30]:
                lines.append(
                    f"  #{e['id']} {e['name']} | {e['date']} | "
                    f"{e['location']} | {e['status']}"
                )
            return "\n".join(lines)

        @beta_tool
        def generate_proposal_for_event(
            event_id: int, workshop_type: str = "Flow Fusion Workshop"
        ) -> str:
            """Generate a workshop proposal for a saved event by its tracker ID.
            workshop_type must be one of: 'Intro to Animal Flow',
            'Flow Fusion Workshop', 'Advanced Flow Lab',
            'Corporate Wellness - Movement Break'."""
            event = tracker.get_event(event_id)
            if not event:
                return f"Event #{event_id} not found."
            proposal = proposal_gen.generate_email(event, workshop_type)
            tracker.save_application(event_id, workshop_type, proposal)
            return f"Proposal for '{event['name']}':\n\n{proposal}"

        client = anthropic.Anthropic()
        tools = [
            {"type": "web_search_20260209", "name": "web_search"},
            save_event,
            list_saved_events,
            generate_proposal_for_event,
        ]

        runner = client.beta.messages.tool_runner(
            model="claude-opus-4-7",
            max_tokens=16000,
            system=AGENT_CONTEXT,
            tools=tools,
            messages=[{"role": "user", "content": user_message}],
            max_iterations=10,
        )

        parts = []
        for message in runner:
            for block in message.content:
                if block.type == "text" and block.text:
                    parts.append(block.text)
        return "\n\n".join(parts).strip() or "Done."

    def _run_api_simple(self, user_message: str) -> str:
        """Fallback: simple API call without tools if beta features unavailable."""
        db = self._event_db_summary()
        prompt = (
            f"{AGENT_CONTEXT}\n\n{db}\n\n"
            f"User: {user_message}\n\n"
            "Respond helpfully. Under 1500 characters."
        )
        return self._ask_api(prompt)

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _ask_simple(self, prompt: str) -> str:
        """Send a one-shot prompt through whichever backend is active."""
        if self.mode == "api":
            return self._ask_api(prompt)
        if self.mode == "cli":
            return self._call_cli(prompt)
        return "AI not available."

    def _ask_api(self, prompt: str) -> str:
        try:
            import anthropic
            client = anthropic.Anthropic()
            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text
        except Exception as e:
            return f"API error: {e}"


# ---------------------------------------------------------------------------
# CLI entry point (standalone usage)
# ---------------------------------------------------------------------------

def main():
    agent = FlowTribesAgent()

    if not agent.available:
        print("=" * 60)
        print("  FlowTribes AI Agent")
        print("=" * 60)
        print()
        print("  Option 1 — Use your Max subscription (no API key):")
        print("    npm install -g @anthropic-ai/claude-code")
        print("    claude login")
        print()
        print("  Option 2 — Use an API key:")
        print("    export ANTHROPIC_API_KEY='sk-ant-...'")
        print()
        print("  Then: python agent.py 'find animal flow workshops in India'")
        print("=" * 60)
        return

    import sys
    if len(sys.argv) < 2:
        print(f"Agent ready (mode: {agent.mode})")
        print("Usage: python agent.py 'your question here'")
        return

    user_msg = " ".join(sys.argv[1:])
    print(f"\nUser: {user_msg}\n")
    print(f"Agent ({agent.mode} mode) thinking...\n")
    print(agent.run(user_msg))


if __name__ == "__main__":
    main()
