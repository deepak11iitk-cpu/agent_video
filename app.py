#!/usr/bin/env python3
"""
FlowTribes Scout — CLI App
Find movement events worldwide, track them, and generate workshop proposals.

Usage:
    python app.py                  Interactive menu
    python app.py scout            Search for new events
    python app.py list             List all tracked events
    python app.py list --india     List India events only
    python app.py propose <id>     Generate proposal for event #id
    python app.py stats            Show dashboard stats
    python app.py search <keyword> Search events by keyword
"""

import sys
import os

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.text import Text
from rich.columns import Columns
from rich import box

from event_scout import EventScout
from tracker import EventTracker
from proposal import ProposalGenerator


console = Console()

BANNER = """
[bold cyan]
 _____ _            _____ _  _             ___                 _
|  ___| | _____    |_   _| |(_) |__   ___ / __| ___ ___  _  _| |_
| |_  | |/ _ \\ \\    | | | || | '_ \\ / _ \\ (__  / __/ _ \\| || |  _|
|  _| | | (_) \\ \\   | | |   | | |_) |  __/\\__ \\\\__ \\(_) | || | |_
|_|   |_|\\___/ \\_\\  |_| |_| |_|_.__/ \\___||___/|___/\\___/ \\_,_|\\__|
[/bold cyan]
[dim]Find events. Apply for workshops. Grow your movement tribe.[/dim]
"""

STATUS_COLORS = {
    "discovered": "white",
    "interested": "yellow",
    "applied": "cyan",
    "accepted": "green",
    "rejected": "red",
}


def show_banner():
    console.print(BANNER)


def scout_events():
    """Search for new events and add them to the tracker."""
    console.print("\n[bold yellow]Scouting for movement events...[/bold yellow]\n")
    scout = EventScout()
    events = scout.search_all()
    scout.deduplicate()
    events = scout.events

    console.print(f"\n[green]Found {len(events)} events![/green]\n")

    tracker = EventTracker()
    tracker.bulk_add_events(events)
    console.print(f"[green]Events saved to tracker database.[/green]\n")

    show_events_table(events[:15], title="Newly Discovered Events (showing first 15)")


def show_events_table(events, title="Events"):
    """Display events in a rich table."""
    table = Table(title=title, box=box.ROUNDED, show_lines=True)
    table.add_column("ID", style="dim", width=4)
    table.add_column("Event", style="bold", max_width=35)
    table.add_column("Date", width=15)
    table.add_column("Location", width=20)
    table.add_column("Type", width=18)
    table.add_column("Source", style="dim", width=15)
    table.add_column("Status", width=12)

    for e in events:
        eid = str(e.get("id", "-"))
        status = e.get("status", "discovered")
        color = STATUS_COLORS.get(status, "white")
        table.add_row(
            eid,
            e.get("name", "")[:35],
            e.get("date", "TBA")[:15],
            e.get("location", "")[:20],
            e.get("event_type", "")[:18],
            e.get("source", "")[:15],
            f"[{color}]{status}[/{color}]",
        )

    console.print(table)


def list_events(filter_country=None, filter_status=None):
    """List all tracked events."""
    tracker = EventTracker()
    events = tracker.get_all_events(status=filter_status)
    if filter_country:
        events = [e for e in events if filter_country.lower() in e.get("country", "").lower()]

    if not events:
        console.print("[yellow]No events found. Run 'scout' first to discover events.[/yellow]")
        return

    title = "All Tracked Events"
    if filter_country:
        title = f"Events in {filter_country}"
    if filter_status:
        title += f" (Status: {filter_status})"

    show_events_table(events, title=title)


def search_events(keyword):
    """Search events by keyword."""
    tracker = EventTracker()
    events = tracker.search_events(keyword)
    if not events:
        console.print(f"[yellow]No events matching '{keyword}'[/yellow]")
        return
    show_events_table(events, title=f"Search: '{keyword}' ({len(events)} results)")


def show_event_detail(event_id):
    """Show full details of a single event."""
    tracker = EventTracker()
    event = tracker.get_event(event_id)
    if not event:
        console.print(f"[red]Event #{event_id} not found.[/red]")
        return

    status = event["status"]
    color = STATUS_COLORS.get(status, "white")

    detail = f"""
[bold]{event['name']}[/bold]

  Date:        {event['date']}
  Location:    {event['location']}
  City:        {event['city']}
  Country:     {event['country']}
  Type:        {event['event_type']}
  Source:      {event['source']}
  URL:         {event['url']}
  Organizer:   {event['organizer']}
  Contact:     {event['contact_email']}
  Apply URL:   {event['application_url']}
  Deadline:    {event['deadline']}
  Status:      [{color}]{status}[/{color}]
  Notes:       {event['notes']}
  Discovered:  {event['discovered_at']}
"""
    if event["description"]:
        detail += f"\n  Description:\n  {event['description']}\n"

    console.print(Panel(detail, title=f"Event #{event['id']}", box=box.ROUNDED))
    return event


def update_event_status(event_id):
    """Update the status of an event."""
    tracker = EventTracker()
    event = tracker.get_event(event_id)
    if not event:
        console.print(f"[red]Event #{event_id} not found.[/red]")
        return

    console.print(f"\nCurrent status: [bold]{event['status']}[/bold]")
    statuses = ["discovered", "interested", "applied", "accepted", "rejected"]
    for i, s in enumerate(statuses, 1):
        color = STATUS_COLORS[s]
        console.print(f"  {i}. [{color}]{s}[/{color}]")

    choice = IntPrompt.ask("Select new status", choices=[str(i) for i in range(1, 6)])
    new_status = statuses[choice - 1]
    notes = Prompt.ask("Add notes (optional)", default="")
    tracker.update_status(event_id, new_status, notes)
    console.print(f"[green]Updated event #{event_id} to '{new_status}'[/green]")


def generate_proposal(event_id, workshop_name=None):
    """Generate a workshop proposal for an event."""
    tracker = EventTracker()
    event = tracker.get_event(event_id)
    if not event:
        console.print(f"[red]Event #{event_id} not found.[/red]")
        return

    gen = ProposalGenerator()
    workshops = gen.get_workshop_types()

    if not workshop_name:
        console.print("\n[bold]Available Workshop Types:[/bold]\n")
        for i, wt in enumerate(workshops, 1):
            console.print(f"  {i}. [cyan]{wt['name']}[/cyan] — {wt['duration']}, {wt['level']}")

        choice = IntPrompt.ask(
            "\nSelect workshop type",
            choices=[str(i) for i in range(1, len(workshops) + 1)],
        )
        workshop_name = workshops[choice - 1]["name"]

    # Ask for output type
    console.print("\n[bold]Output format:[/bold]")
    console.print("  1. Full Proposal")
    console.print("  2. Email Pitch")
    console.print("  3. Both")
    fmt = IntPrompt.ask("Select format", choices=["1", "2", "3"], default="3")

    if fmt in (1, 3):
        proposal = gen.generate_proposal(event, workshop_name)
        console.print(Panel(proposal, title="Full Proposal", box=box.DOUBLE))

        if Confirm.ask("Save proposal to file?", default=True):
            filename = f"proposal_{event_id}_{workshop_name.replace(' ', '_').lower()}.txt"
            with open(filename, "w") as f:
                f.write(proposal)
            console.print(f"[green]Saved to {filename}[/green]")

            # Also save to DB
            tracker.save_application(event_id, workshop_name, proposal)

    if fmt in (2, 3):
        email = gen.generate_email(event, workshop_name)
        console.print(Panel(email, title="Email Pitch", box=box.DOUBLE))

        if Confirm.ask("Save email to file?", default=True):
            filename = f"email_{event_id}_{workshop_name.replace(' ', '_').lower()}.txt"
            with open(filename, "w") as f:
                f.write(email)
            console.print(f"[green]Saved to {filename}[/green]")


def show_stats():
    """Show dashboard with statistics."""
    tracker = EventTracker()
    stats = tracker.get_stats()

    console.print(Panel(
        f"[bold cyan]Total Events Tracked: {stats['total']}[/bold cyan]",
        title="FlowTribes Scout Dashboard",
        box=box.DOUBLE,
    ))

    # Status breakdown
    if stats["by_status"]:
        table = Table(title="By Status", box=box.SIMPLE)
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")
        for status, count in stats["by_status"].items():
            color = STATUS_COLORS.get(status, "white")
            table.add_row(f"[{color}]{status}[/{color}]", str(count))
        console.print(table)

    # Country breakdown
    if stats["by_country"]:
        table = Table(title="By Country", box=box.SIMPLE)
        table.add_column("Country", style="bold")
        table.add_column("Count", justify="right")
        for country, count in stats["by_country"].items():
            table.add_row(country or "Unknown", str(count))
        console.print(table)

    # Type breakdown
    if stats["by_type"]:
        table = Table(title="By Event Type", box=box.SIMPLE)
        table.add_column("Type", style="bold")
        table.add_column("Count", justify="right")
        for etype, count in stats["by_type"].items():
            table.add_row(etype or "Unknown", str(count))
        console.print(table)


def interactive_menu():
    """Main interactive menu."""
    show_banner()

    while True:
        console.print("\n[bold]What would you like to do?[/bold]\n")
        console.print("  [cyan]1[/cyan]  Scout for new events")
        console.print("  [cyan]2[/cyan]  List all events")
        console.print("  [cyan]3[/cyan]  List India events")
        console.print("  [cyan]4[/cyan]  Search events")
        console.print("  [cyan]5[/cyan]  View event details")
        console.print("  [cyan]6[/cyan]  Update event status")
        console.print("  [cyan]7[/cyan]  Generate workshop proposal")
        console.print("  [cyan]8[/cyan]  Dashboard / Stats")
        console.print("  [cyan]9[/cyan]  Add custom event")
        console.print("  [cyan]0[/cyan]  Exit")

        choice = Prompt.ask("\nSelect option", choices=["0","1","2","3","4","5","6","7","8","9"])

        if choice == "0":
            console.print("[dim]See you on the mat! [/dim]")
            break
        elif choice == "1":
            scout_events()
        elif choice == "2":
            list_events()
        elif choice == "3":
            list_events(filter_country="India")
        elif choice == "4":
            keyword = Prompt.ask("Search keyword")
            search_events(keyword)
        elif choice == "5":
            eid = IntPrompt.ask("Event ID")
            show_event_detail(eid)
        elif choice == "6":
            eid = IntPrompt.ask("Event ID")
            update_event_status(eid)
        elif choice == "7":
            eid = IntPrompt.ask("Event ID")
            generate_proposal(eid)
        elif choice == "8":
            show_stats()
        elif choice == "9":
            add_custom_event()


def add_custom_event():
    """Manually add a custom event."""
    console.print("\n[bold]Add Custom Event[/bold]\n")
    name = Prompt.ask("Event name")
    date = Prompt.ask("Date (e.g., 'March 2026')", default="TBA")
    location = Prompt.ask("Location")
    city = Prompt.ask("City", default="")
    country = Prompt.ask("Country", default="India")
    event_type = Prompt.ask("Event type (e.g., 'fitness expo', 'yoga festival')", default="event")
    url = Prompt.ask("URL", default="")
    contact = Prompt.ask("Contact email", default="")
    description = Prompt.ask("Description", default="")

    tracker = EventTracker()
    tracker.add_event({
        "name": name,
        "date": date,
        "location": location,
        "city": city,
        "country": country,
        "event_type": event_type,
        "url": url,
        "source": "Manual Entry",
        "description": description,
        "contact_email": contact,
        "status": "interested",
    })
    console.print(f"[green]Added '{name}' to tracker![/green]")


def main():
    """Entry point — handle CLI args or launch interactive menu."""
    args = sys.argv[1:]

    if not args:
        interactive_menu()
        return

    cmd = args[0].lower()

    if cmd == "scout":
        show_banner()
        scout_events()
    elif cmd == "list":
        show_banner()
        if "--india" in args:
            list_events(filter_country="India")
        elif "--status" in args and len(args) > args.index("--status") + 1:
            list_events(filter_status=args[args.index("--status") + 1])
        else:
            list_events()
    elif cmd == "search" and len(args) > 1:
        show_banner()
        search_events(" ".join(args[1:]))
    elif cmd == "propose" and len(args) > 1:
        show_banner()
        generate_proposal(int(args[1]))
    elif cmd == "stats":
        show_banner()
        show_stats()
    elif cmd == "detail" and len(args) > 1:
        show_banner()
        show_event_detail(int(args[1]))
    else:
        console.print(__doc__)


if __name__ == "__main__":
    main()
