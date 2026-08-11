"""GEOS Menu — Interactive command reference.

Displays all available GEOS commands organized by category with
descriptions and usage examples.
"""

from __future__ import annotations

from . import __version__
from .formatting import (
    heading, bold, dim, value, success, info, warning,
    status_ok, status_info, status_arrow, badge_version,
    print_kv, Icon
)


# ── Command Categories ────────────────────────────────────────────────────────

MENU_CATEGORIES = [
    {
        "name": "Core",
        "icon": "⚙️",
        "description": "Setup and environment",
        "commands": [
            ("init", "Detect mode, create .geos/, manifest, registry", "geos init [--mode greenfield|brownfield|standalone]"),
            ("doctor", "Environment and config checks", "geos doctor"),
            ("bootstrap", "Scaffold greenfield workspace (SPEC-103)", "geos bootstrap"),
            ("db migrate", "Apply pending database migrations", "geos db migrate"),
            ("update", "Check for updates or install latest version", "geos update [--check] [--force] [--pip]"),
        ]
    },
    {
        "name": "Knowledge",
        "icon": "📚",
        "description": "Intelligence layer",
        "commands": [
            ("knowledge ingest", "Ingest a docs directory", "geos knowledge ingest <path> [--source NAME]"),
            ("knowledge search", "FTS search over ingested chunks", "geos knowledge search \"query\" [--limit 10]"),
            ("knowledge reindex", "Rebuild all embeddings", "geos knowledge reindex [--provider hash|openai]"),
            ("graph extract", "Extract entities from documents", "geos graph extract"),
            ("graph inspect", "View graph stats and nodes", "geos graph inspect [--type TYPE]"),
        ]
    },
    {
        "name": "Research",
        "icon": "🔍",
        "description": "Research engine",
        "commands": [
            ("research run", "Run research on local knowledge base", "geos research run \"question\" [--sources-limit 5]"),
            ("models info", "Show configured LLM provider", "geos models info"),
            ("models test", "Test LLM connectivity", "geos models test"),
        ]
    },
    {
        "name": "Content",
        "icon": "📝",
        "description": "Content creation and management",
        "commands": [
            ("content create", "Create a content idea", "geos content create \"topic\" [--type article]"),
            ("content list", "List content items", "geos content list [--status IDEA]"),
            ("content draft", "Generate draft from idea", "geos content draft <id>"),
            ("content score", "Score content quality", "geos content score <id>"),
            ("content status", "Transition content status", "geos content status <id> APPROVED"),
            ("content show", "Show content details", "geos content show <id>"),
        ]
    },
    {
        "name": "Distribution",
        "icon": "📢",
        "description": "Blog, social, and publishing",
        "commands": [
            ("blog prepare", "Prepare blog post from content", "geos blog prepare <content_id>"),
            ("blog list", "List blog posts", "geos blog list [--status PUBLISHED]"),
            ("blog publish", "Publish blog post (requires approval)", "geos blog publish <post_id> --approve"),
            ("social prepare", "Prepare social post", "geos social prepare <content_id> --channel x|linkedin"),
            ("social list", "List social posts", "geos social list [--channel x]"),
            ("social publish", "Publish social post (requires approval)", "geos social publish <post_id> --approve"),
            ("social worker", "Execute pre-approved social posts", "geos social worker"),
        ]
    },
    {
        "name": "SEO",
        "icon": "🔎",
        "description": "SEO analysis",
        "commands": [
            ("seo audit", "Run SEO audit on docs/content", "geos seo audit [--scope docs] [--verbose]"),
            ("seo issues", "List SEO issues", "geos seo Issues [--severity critical]"),
        ]
    },
    {
        "name": "Growth",
        "icon": "📈",
        "description": "Opportunities and experiments",
        "commands": [
            ("opportunities collect", "Collect opportunities from research/SEO", "geos opportunities collect"),
            ("opportunities list", "List prioritized opportunities", "geos opportunities list [--method rice]"),
            ("opportunities create", "Create manual opportunity", "geos opportunities create \"problem\""),
            ("opportunities score", "Score opportunity ICE/RICE", "geos opportunities score <id> --method ice"),
            ("experiments create", "Create experiment from opportunity", "geos experiments create <opp_id> --metric \"metric\""),
            ("experiments list", "List experiments", "geos experiments list [--status RUNNING]"),
            ("experiments complete", "Complete experiment with learning", "geos experiments complete <id> --result \"...\" --decision ADOPT --learning \"...\""),
        ]
    },
    {
        "name": "Campaigns",
        "icon": "🎯",
        "description": "Campaign orchestration",
        "commands": [
            ("campaigns create", "Create a growth campaign", "geos campaigns create \"name\" --type content_distribution"),
            ("campaigns list", "List campaigns", "campaigns list [--status ACTIVE]"),
            ("campaigns show", "Show campaign details", "campaigns show <id>"),
            ("campaigns activate", "Activate a campaign", "campaigns activate <id>"),
            ("campaigns summary", "Campaign summary with metrics", "campaigns summary <id>"),
        ]
    },
    {
        "name": "CRM & Leads",
        "icon": "💼",
        "description": "Lead intelligence and CRM",
        "commands": [
            ("leads capture", "Capture a new lead", "leads capture email@example.com --name \"Name\""),
            ("leads list", "List leads", "leads list [--status QUALIFIED]"),
            ("leads qualify", "Qualify a lead (BANT/MEDDIC)", "leads qualify <id> --method BANT"),
            ("leads score", "Compute lead score", "leads score <id>"),
            ("crm create-deal", "Create a CRM deal", "crm create-deal \"Deal Name\" --value 5000"),
            ("crm list-deals", "List deals", "crm list-deals [--stage PROPOSAL]"),
            ("crm pipeline", "Pipeline summary", "crm pipeline"),
        ]
    },
    {
        "name": "Meetings",
        "icon": "📅",
        "description": "Meeting scheduling",
        "commands": [
            ("meetings schedule", "Schedule a meeting", "meetings schedule \"Title\" --at 2026-08-15T10:00:00"),
            ("meetings list", "List meetings", "meetings list [--status SCHEDULED]"),
            ("meetings upcoming", "Show upcoming meetings", "meetings upcoming"),
            ("meetings analytics", "Meeting analytics", "meetings analytics"),
        ]
    },
    {
        "name": "Email",
        "icon": "📧",
        "description": "Email nurture sequences",
        "commands": [
            ("email create-sequence", "Create email sequence", "email create-sequence \"Welcome\" --trigger lead_captured"),
            ("email list-sequences", "List sequences", "email list-sequences"),
            ("email enroll", "Enroll lead in sequence", "email enroll <seq_id> <lead_id>"),
            ("email suppress", "Suppress email address", "email suppress email@example.com"),
        ]
    },
    {
        "name": "Education",
        "icon": "🎓",
        "description": "Academy and community",
        "commands": [
            ("academy create", "Create academy content", "academy create \"Course Title\" --type course"),
            ("academy list", "List academy content", "academy list [--type lesson]"),
            ("academy enroll", "Enroll learner", "academy enroll <content_id> <learner_id>"),
            ("community add-member", "Add community member", "community add-member \"Name\" --platform discord"),
            ("community overview", "Community overview", "community overview"),
        ]
    },
    {
        "name": "Automation",
        "icon": "🤖",
        "description": "Workflows and automations",
        "commands": [
            ("workflows list", "List available workflows", "workflows list"),
            ("workflows run", "Run a workflow", "workflows run <workflow_id> [--input key=value]"),
            ("workflows schedule", "Register cron/interval trigger", "workflows schedule <workflow_id>"),
            ("workflows worker", "Process pending jobs", "workflows worker [--once]"),
            ("automations register", "Register default automations", "automations register"),
            ("automations list", "List scheduled automations", "automations list"),
            ("automations run", "Run due automations", "automations run"),
        ]
    },
    {
        "name": "Observability",
        "icon": "📊",
        "description": "Analytics and monitoring",
        "commands": [
            ("analytics collect", "Collect metrics snapshot", "analytics collect"),
            ("analytics metrics", "View collected metrics", "analytics metrics [--domain content]"),
            ("analytics insights", "View insights", "analytics insights [--type OBSERVATION]"),
            ("runs list", "List workflow runs", "runs list [--status SUCCESS]"),
            ("approvals list", "List pending approvals", "approvals list"),
            ("approvals decide", "Approve/reject action", "approvals decide <id> approve|reject"),
        ]
    },
    {
        "name": "Control Center",
        "icon": "🎛️",
        "description": "Dashboard and debugging",
        "commands": [
            ("control-center build", "Generate static HTML dashboard", "control-center build [--output path]"),
            ("cc rag-debug", "Debug RAG retrieval queries", "cc rag-debug \"query\""),
            ("cc run-debug", "Debug specific run", "cc run-debug <run_id>"),
            ("cc backup", "Backup database", "cc backup [--dir backups]"),
            ("cc audit", "Run self-audit", "cc audit"),
        ]
    },
    {
        "name": "Planning",
        "icon": "📋",
        "description": "Integration planning",
        "commands": [
            ("plan", "Generate integration plan", "geos plan"),
            ("repo add", "Add repository to registry", "repo add <id> <path> --type PRODUCT"),
            ("repo list", "List registered repositories", "repo list"),
        ]
    },
]


def get_all_commands() -> list[tuple[str, str, str]]:
    """Get flat list of all commands: (command, description, example)."""
    commands = []
    for category in MENU_CATEGORIES:
        for cmd, desc, example in category["commands"]:
            commands.append((cmd, desc, example))
    return commands


def get_command_count() -> int:
    """Get total number of commands."""
    return sum(len(cat["commands"]) for cat in MENU_CATEGORIES)


def format_menu_colored() -> str:
    """Format the full menu with colors."""
    lines = []
    
    # Header
    lines.append("")
    lines.append(f"  {bold('GEOS')} {value('v' + __version__)} — {dim('AI Agent Framework for Growth')}")
    lines.append(f"  {dim(f'{get_command_count()} commands across {len(MENU_CATEGORIES)} categories')}")
    lines.append("")
    
    # Categories
    for category in MENU_CATEGORIES:
        cat_name = f"{category['icon']}  {bold(category['name'])}"
        cat_desc = dim(f"— {category['description']}")
        lines.append(f"  {cat_name} {cat_desc}")
        
        for cmd, desc, example in category["commands"]:
            lines.append(f"    {status_arrow()} {bold(cmd):30s} {dim(desc)}")
        
        lines.append("")
    
    # Footer
    lines.append(f"  {dim('Examples:')}")
    lines.append(f"    {status_arrow()} geos init --mode greenfield")
    lines.append(f"    {status_arrow()} geos knowledge ingest docs/")
    lines.append(f"    {status_arrow()} geos content create \"AI agents\"")
    lines.append(f"    {status_arrow()} geos social prepare <id> --channel x")
    lines.append(f"    {status_arrow()} geos analytics collect")
    lines.append("")
    lines.append(f"  {dim('Documentation:')} {value('github.com/matalvesdev/geos')}")
    lines.append(f"  {dim('Update:')} {bold('geos update')}")
    lines.append("")
    
    return "\n".join(lines)


def format_menu_plain() -> str:
    """Format the menu without colors (for piping/redirect)."""
    lines = []
    
    lines.append("")
    lines.append(f"  GEOS v{__version__} — AI Agent Framework for Growth")
    lines.append(f"  {get_command_count()} commands across {len(MENU_CATEGORIES)} categories")
    lines.append("")
    
    for category in MENU_CATEGORIES:
        lines.append(f"  {category['name']} — {category['description']}")
        
        for cmd, desc, example in category["commands"]:
            lines.append(f"    > {cmd:30s} {desc}")
        
        lines.append("")
    
    lines.append(f"  Documentation: github.com/matalvesdev/geos")
    lines.append(f"  Update: geos update")
    lines.append("")
    
    return "\n".join(lines)


def cmd_menu(args: argparse.Namespace) -> int:
    """CLI handler for `geos menu`."""
    import sys
    
    if args.command:
        # Show specific command help
        return _show_command_help(args.command)
    
    if args.list:
        # Flat list of all commands
        for cmd, desc, _ in get_all_commands():
            print(f"  {cmd:35s} {desc}")
        return 0
    
    # Show full menu
    from .formatting import _TTY
    if _TTY:
        print(format_menu_colored())
    else:
        print(format_menu_plain())
    
    return 0


def _show_command_help(command: str) -> int:
    """Show help for a specific command."""
    from .formatting import heading, bold, dim, value, status_arrow
    
    # Search for command
    for category in MENU_CATEGORIES:
        for cmd, desc, example in category["commands"]:
            if cmd == command or cmd.startswith(command):
                print()
                print(f"  {bold(cmd)}")
                print(f"  {dim(desc)}")
                print()
                print(f"  {dim('Example:')}")
                print(f"    {status_arrow()} {value(example)}")
                print()
                return 0
    
    print(f"  Command not found: {command}")
    print(f"  Run {bold('geos menu')} to see all commands")
    return 1


# Need to import argparse for type hints
import argparse
