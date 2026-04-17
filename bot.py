#!/usr/bin/env python3
"""
FlowTribes Scout — Telegram Agent Bot
A persistent AI agent that finds movement events and helps you apply for workshops.

Setup:
    1. Message @BotFather on Telegram → /newbot → get your token
    2. Set TELEGRAM_BOT_TOKEN in .env or export it
    3. Run: python bot.py
"""

import os
import logging
from datetime import datetime, time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from event_scout import EventScout
from tracker import EventTracker
from proposal import ProposalGenerator

try:
    from agent import FlowTribesAgent
    AI_AGENT_AVAILABLE = bool(os.environ.get("ANTHROPIC_API_KEY"))
except ImportError:
    AI_AGENT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
tracker = EventTracker()
scout = EventScout()
proposal_gen = ProposalGenerator()
ai_agent = FlowTribesAgent() if AI_AGENT_AVAILABLE else None

# Store the chat ID of the owner so we can send proactive messages
OWNER_CHAT_ID = None


# ===========================================================================
# Command handlers
# ===========================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message and register owner."""
    global OWNER_CHAT_ID
    OWNER_CHAT_ID = update.effective_chat.id

    ai_note = (
        "✨ *AI Agent mode is ON.* Just chat with me normally:\n"
        "  • \"find yoga festivals in Bangalore\"\n"
        "  • \"what's happening in Goa this year\"\n"
        "  • \"draft a proposal for event #3\"\n\n"
        if ai_agent else
        "_(AI agent offline — set ANTHROPIC_API_KEY to enable smart search.)_\n\n"
    )

    await update.message.reply_text(
        "Hey! I'm your *FlowTribes Scout* agent.\n\n"
        "I find movement & fitness events and help you apply for workshops.\n\n"
        f"{ai_note}"
        "*Commands:*\n"
        "/scout — Quick scrape-based scout\n"
        "/events — List all tracked events\n"
        "/india — Show India events only\n"
        "/search `keyword` — Search events\n"
        "/detail `id` — View event details\n"
        "/status `id` `status` — Update event status\n"
        "/propose `id` — Generate workshop proposal\n"
        "/email `id` — Generate email pitch\n"
        "/stats — Dashboard\n"
        "/workshops — Show workshop types\n"
        "/add — Add a custom event\n"
        "/help — Show this message",
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help."""
    await start(update, context)


async def scout_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search for new events."""
    msg = await update.message.reply_text("Scouting for events... this may take a minute.")

    events = scout.search_all()
    scout.deduplicate()
    events = scout.events

    added = tracker.bulk_add_events(events)

    text = f"*Scouting complete!*\n\n"
    text += f"Found *{len(events)}* events total\n"
    text += f"*{added}* new events added to tracker\n\n"

    # Show top 10
    all_events = tracker.get_all_events()
    if all_events:
        text += "*Latest events:*\n"
        for e in all_events[:10]:
            flag = "🇮🇳" if "india" in e.get("country", "").lower() else "🌍"
            text += f"\n{flag} *#{e['id']}* {e['name']}\n"
            text += f"   📅 {e['date']} | 📍 {e['location']}\n"

    await msg.edit_text(text, parse_mode="Markdown")


async def events_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all events."""
    events = tracker.get_all_events()
    if not events:
        await update.message.reply_text("No events yet. Run /scout first!")
        return
    await _send_event_list(update, events, "All Tracked Events")


async def india_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List India events."""
    events = tracker.get_all_events()
    india = [e for e in events if "india" in e.get("country", "").lower()]
    if not india:
        await update.message.reply_text("No India events found. Run /scout first!")
        return
    await _send_event_list(update, india, "Events in India")


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search events by keyword."""
    if not context.args:
        await update.message.reply_text("Usage: /search `keyword`\nExample: /search yoga")
        return
    keyword = " ".join(context.args)
    events = tracker.search_events(keyword)
    if not events:
        await update.message.reply_text(f"No events matching '{keyword}'")
        return
    await _send_event_list(update, events, f"Search: '{keyword}'")


async def detail_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show event details."""
    if not context.args:
        await update.message.reply_text("Usage: /detail `id`\nExample: /detail 3")
        return
    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid event ID number.")
        return

    event = tracker.get_event(event_id)
    if not event:
        await update.message.reply_text(f"Event #{event_id} not found.")
        return

    status_emoji = {
        "discovered": "⚪", "interested": "🟡",
        "applied": "🔵", "accepted": "🟢", "rejected": "🔴",
    }

    text = f"*Event #{event['id']}*\n\n"
    text += f"*{event['name']}*\n\n"
    text += f"📅 Date: {event['date']}\n"
    text += f"📍 Location: {event['location']}\n"
    text += f"🏙 City: {event['city']}\n"
    text += f"🌍 Country: {event['country']}\n"
    text += f"🏷 Type: {event['event_type']}\n"
    text += f"📡 Source: {event['source']}\n"
    text += f"{status_emoji.get(event['status'], '⚪')} Status: {event['status']}\n"

    if event.get("url"):
        text += f"🔗 URL: {event['url']}\n"
    if event.get("organizer"):
        text += f"👤 Organizer: {event['organizer']}\n"
    if event.get("description"):
        text += f"\n_{event['description']}_\n"
    if event.get("notes"):
        text += f"\n📝 Notes: {event['notes']}\n"

    # Action buttons
    keyboard = [
        [
            InlineKeyboardButton("🟡 Interested", callback_data=f"status_{event_id}_interested"),
            InlineKeyboardButton("🔵 Applied", callback_data=f"status_{event_id}_applied"),
        ],
        [
            InlineKeyboardButton("🟢 Accepted", callback_data=f"status_{event_id}_accepted"),
            InlineKeyboardButton("🔴 Rejected", callback_data=f"status_{event_id}_rejected"),
        ],
        [
            InlineKeyboardButton("📝 Generate Proposal", callback_data=f"propose_{event_id}"),
            InlineKeyboardButton("📧 Email Pitch", callback_data=f"email_{event_id}"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update event status via command."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /status `id` `status`\n"
            "Statuses: discovered, interested, applied, accepted, rejected\n"
            "Example: /status 3 interested"
        )
        return

    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid event ID.")
        return

    valid = ["discovered", "interested", "applied", "accepted", "rejected"]
    new_status = context.args[1].lower()
    if new_status not in valid:
        await update.message.reply_text(f"Invalid status. Choose: {', '.join(valid)}")
        return

    event = tracker.get_event(event_id)
    if not event:
        await update.message.reply_text(f"Event #{event_id} not found.")
        return

    notes = " ".join(context.args[2:]) if len(context.args) > 2 else ""
    tracker.update_status(event_id, new_status, notes)
    await update.message.reply_text(f"Updated *#{event_id}* ({event['name']}) → *{new_status}*", parse_mode="Markdown")


async def propose_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a workshop proposal."""
    if not context.args:
        await update.message.reply_text("Usage: /propose `id`\nExample: /propose 3")
        return

    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid event ID.")
        return

    event = tracker.get_event(event_id)
    if not event:
        await update.message.reply_text(f"Event #{event_id} not found.")
        return

    # Show workshop type picker
    workshops = proposal_gen.get_workshop_types()
    keyboard = []
    for wt in workshops:
        keyboard.append([InlineKeyboardButton(
            f"{wt['name']} ({wt['duration']})",
            callback_data=f"genprop_{event_id}_{wt['name'][:20]}",
        )])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Select workshop type for *{event['name']}*:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def email_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate an email pitch."""
    if not context.args:
        await update.message.reply_text("Usage: /email `id`\nExample: /email 3")
        return

    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid event ID.")
        return

    event = tracker.get_event(event_id)
    if not event:
        await update.message.reply_text(f"Event #{event_id} not found.")
        return

    email = proposal_gen.generate_email(event)
    # Telegram has a 4096 char limit; split if needed
    for chunk in _split_message(email):
        await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show dashboard stats."""
    stats = tracker.get_stats()

    text = "*FlowTribes Scout Dashboard*\n\n"
    text += f"📊 Total events tracked: *{stats['total']}*\n\n"

    if stats["by_status"]:
        emoji_map = {
            "discovered": "⚪", "interested": "🟡",
            "applied": "🔵", "accepted": "🟢", "rejected": "🔴",
        }
        text += "*By Status:*\n"
        for s, c in stats["by_status"].items():
            text += f"  {emoji_map.get(s, '⚪')} {s}: {c}\n"

    if stats["by_country"]:
        text += "\n*By Country:*\n"
        for country, c in stats["by_country"].items():
            text += f"  📍 {country or 'Unknown'}: {c}\n"

    if stats["by_type"]:
        text += "\n*By Type:*\n"
        for t, c in stats["by_type"].items():
            text += f"  🏷 {t or 'Unknown'}: {c}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def workshops_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available workshop types."""
    workshops = proposal_gen.get_workshop_types()
    text = "*Available Workshop Types:*\n\n"
    for i, wt in enumerate(workshops, 1):
        text += f"*{i}. {wt['name']}*\n"
        text += f"   ⏱ {wt['duration']} | 👥 {wt['capacity']} | 📈 {wt['level']}\n"
        text += f"   _{wt['description'].strip()[:150]}..._\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a custom event. Usage: /add Event Name | Date | Location | Country"""
    if not context.args:
        await update.message.reply_text(
            "Usage: /add `Event Name | Date | City, Country | Type`\n\n"
            "Example:\n"
            "/add FitFest Mumbai | June 2026 | Mumbai, India | fitness expo"
        )
        return

    parts = " ".join(context.args).split("|")
    parts = [p.strip() for p in parts]

    name = parts[0] if len(parts) > 0 else "Unknown Event"
    date = parts[1] if len(parts) > 1 else "TBA"
    location = parts[2] if len(parts) > 2 else "TBA"
    event_type = parts[3] if len(parts) > 3 else "event"

    # Try to extract country from location
    country = "India"
    if "," in location:
        country = location.split(",")[-1].strip()

    tracker.add_event({
        "name": name,
        "date": date,
        "location": location,
        "city": location.split(",")[0].strip() if "," in location else location,
        "country": country,
        "event_type": event_type,
        "url": "",
        "source": "Manual (Telegram)",
        "status": "interested",
    })

    await update.message.reply_text(f"Added *{name}* to tracker!", parse_mode="Markdown")


# ===========================================================================
# Callback query handler (inline buttons)
# ===========================================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("status_"):
        # Format: status_{id}_{status}
        parts = data.split("_", 2)
        event_id = int(parts[1])
        new_status = parts[2]
        tracker.update_status(event_id, new_status)
        event = tracker.get_event(event_id)
        await query.edit_message_text(
            f"Updated *#{event_id}* ({event['name']}) → *{new_status}*",
            parse_mode="Markdown",
        )

    elif data.startswith("propose_"):
        event_id = int(data.split("_")[1])
        event = tracker.get_event(event_id)
        if not event:
            await query.edit_message_text("Event not found.")
            return
        workshops = proposal_gen.get_workshop_types()
        keyboard = []
        for wt in workshops:
            keyboard.append([InlineKeyboardButton(
                f"{wt['name']} ({wt['duration']})",
                callback_data=f"genprop_{event_id}_{wt['name'][:20]}",
            )])
        await query.edit_message_text(
            f"Select workshop type for *{event['name']}*:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("genprop_"):
        parts = data.split("_", 2)
        event_id = int(parts[1])
        workshop_prefix = parts[2]
        event = tracker.get_event(event_id)
        if not event:
            await query.edit_message_text("Event not found.")
            return
        # Find matching workshop
        workshops = proposal_gen.get_workshop_types()
        workshop_name = None
        for wt in workshops:
            if wt["name"].startswith(workshop_prefix):
                workshop_name = wt["name"]
                break
        proposal = proposal_gen.generate_proposal(event, workshop_name)
        tracker.save_application(event_id, workshop_name or "default", proposal)
        await query.edit_message_text(f"Proposal generated for *{event['name']}*!", parse_mode="Markdown")
        for chunk in _split_message(proposal):
            await query.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")

    elif data.startswith("email_"):
        event_id = int(data.split("_")[1])
        event = tracker.get_event(event_id)
        if not event:
            await query.edit_message_text("Event not found.")
            return
        email = proposal_gen.generate_email(event)
        await query.edit_message_text(f"Email pitch for *{event['name']}*:", parse_mode="Markdown")
        for chunk in _split_message(email):
            await query.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")


# ===========================================================================
# Natural language handler (basic agent behavior)
# ===========================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Free-text messages go through the AI agent (Claude + web search)."""
    text = update.message.text.strip()

    if ai_agent is None:
        await update.message.reply_text(
            "The AI agent is not configured. Set ANTHROPIC_API_KEY and restart.\n\n"
            "Or use commands directly: /scout, /events, /stats, /help"
        )
        return

    msg = await update.message.reply_text("🤔 Thinking & searching the web...")

    try:
        import asyncio
        response = await asyncio.to_thread(ai_agent.run, text)
    except Exception as e:
        logger.exception("Agent error")
        await msg.edit_text(f"Agent error: {e}")
        return

    # Telegram has a 4096 char limit
    if len(response) <= 4000:
        await msg.edit_text(response)
    else:
        await msg.delete()
        for chunk in _split_message(response):
            await update.message.reply_text(chunk)


# ===========================================================================
# Scheduled jobs (proactive agent behavior)
# ===========================================================================

async def scheduled_scout(context: ContextTypes.DEFAULT_TYPE):
    """Proactively scout for events and notify the owner."""
    if not OWNER_CHAT_ID:
        return

    logger.info("Running scheduled event scout...")
    events = scout.search_all()
    scout.deduplicate()
    added = tracker.bulk_add_events(scout.events)

    if added > 0:
        text = f"🔔 *Daily Scout Report*\n\n"
        text += f"Found *{added}* new events!\n\n"
        new_events = tracker.get_all_events()[-added:]
        for e in new_events[:5]:
            flag = "🇮🇳" if "india" in e.get("country", "").lower() else "🌍"
            text += f"{flag} *#{e['id']}* {e['name']}\n"
            text += f"   📅 {e['date']} | 📍 {e['location']}\n\n"
        if added > 5:
            text += f"...and {added - 5} more. Use /events to see all."
        text += "\nUse /detail `id` to see details and apply!"

        await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=text, parse_mode="Markdown")


# ===========================================================================
# Helpers
# ===========================================================================

def _split_message(text, max_len=3500):
    """Split long messages for Telegram's 4096 char limit."""
    chunks = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:]
    chunks.append(text)
    return chunks


async def _send_event_list(update, events, title):
    """Format and send a list of events."""
    text = f"*{title}* ({len(events)} events)\n\n"
    for e in events[:20]:
        flag = "🇮🇳" if "india" in e.get("country", "").lower() else "🌍"
        status_emoji = {
            "discovered": "⚪", "interested": "🟡",
            "applied": "🔵", "accepted": "🟢", "rejected": "🔴",
        }
        s = status_emoji.get(e.get("status", ""), "⚪")
        text += f"{flag} *#{e['id']}* {e['name']}\n"
        text += f"   📅 {e['date']} | 📍 {e['location']} {s}\n\n"

    if len(events) > 20:
        text += f"_...and {len(events) - 20} more. Use /search to filter._"

    text += "\nUse /detail `id` for full info + actions."
    await update.message.reply_text(text, parse_mode="Markdown")


# ===========================================================================
# Main
# ===========================================================================

def main():
    """Start the bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    if not token:
        print("=" * 60)
        print("  FlowTribes Scout — Telegram Agent")
        print("=" * 60)
        print()
        print("  To get started:")
        print()
        print("  1. Open Telegram and message @BotFather")
        print("  2. Send /newbot and follow the steps")
        print("  3. Copy the token BotFather gives you")
        print("  4. Run:")
        print()
        print("     export TELEGRAM_BOT_TOKEN='your-token-here'")
        print("     python bot.py")
        print()
        print("=" * 60)
        return

    print("Starting FlowTribes Scout Telegram Agent...")

    app = Application.builder().token(token).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("scout", scout_cmd))
    app.add_handler(CommandHandler("events", events_cmd))
    app.add_handler(CommandHandler("india", india_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("detail", detail_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("propose", propose_cmd))
    app.add_handler(CommandHandler("email", email_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("workshops", workshops_cmd))
    app.add_handler(CommandHandler("add", add_cmd))

    # Inline button handler
    app.add_handler(CallbackQueryHandler(button_handler))

    # Natural language fallback
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Schedule daily scout at 9 AM
    if app.job_queue:
        app.job_queue.run_daily(
            scheduled_scout,
            time=time(hour=9, minute=0),
            name="daily_scout",
        )
        print("Scheduled daily event scout at 9:00 AM")

    print("Bot is running! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
