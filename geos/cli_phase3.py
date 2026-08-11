"""CLI commands for Phase 3: Leads, CRM, Meetings, Email Nurture."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .storage.database import Database
from .config import Settings


def _settings(root: str, config: str | None) -> Settings:
    path = config or str(Path(root) / ".geos/geos.yaml")
    return Settings.from_path(path, root=root)


def _db(settings: Settings) -> Database:
    db = Database(settings.db_path)
    db.open()
    return db


# ---- Leads (SPEC-026/027/028) -------------------------------------------

def cmd_leads_capture(args: argparse.Namespace) -> int:
    from .domains.leads import LeadEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = LeadEngine(db).capture(
            email=args.email, name=args.name, company=args.company,
            source=args.source, tags=args.tags,
        )
        print(f"captured {item['id']} | {item['status']} | {item['email']}")
        print(f"  name: {item.get('name', '-')} company: {item.get('company', '-')}")
    finally:
        db.close()
    return 0


def cmd_leads_list(args: argparse.Namespace) -> int:
    from .domains.leads import LeadEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = LeadEngine(db).list(status=args.status, source=args.source, limit=args.limit)
        print(f"{len(items)} lead(s)")
        for item in items:
            score = f"score={item.get('score', '-')}" if item.get('score') else "score=-"
            print(f"  {item['status']:12s} {score:12s} {item['email']:30s} {item.get('name', '-')}")
    finally:
        db.close()
    return 0


def cmd_leads_show(args: argparse.Namespace) -> int:
    from .domains.leads import LeadEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = LeadEngine(db).summary(args.lead_id)
        lead = result["lead"]
        print(f"{lead['email']} ({lead.get('name', '-')})")
        print(f"status={lead['status']} source={lead['source']}")
        if lead.get('company'):
            print(f"company: {lead['company']}")
        print(f"score: {result['score']} (confidence: {result['score_breakdown'].get('confidence', '-')})")
        print(f"interactions: {result['interaction_count']}")
    finally:
        db.close()
    return 0


def cmd_leads_transition(args: argparse.Namespace) -> int:
    from .domains.leads import LeadEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = LeadEngine(db).transition(args.lead_id, args.status)
        print(f"{item['id']}: {item['status']}")
    finally:
        db.close()
    return 0


def cmd_leads_qualify(args: argparse.Namespace) -> int:
    from .domains.leads import LeadEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = LeadEngine(db).qualify(args.lead_id, method=args.method)
        print(f"{item['id']}: {item['status']} (method: {args.method})")
    finally:
        db.close()
    return 0


def cmd_leads_disqualify(args: argparse.Namespace) -> int:
    from .domains.leads import LeadEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = LeadEngine(db).disqualify(args.lead_id, reason=args.reason)
        print(f"{item['id']}: {item['status']} (reason: {args.reason})")
    finally:
        db.close()
    return 0


def cmd_leads_interact(args: argparse.Namespace) -> int:
    from .domains.leads import LeadEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = LeadEngine(db).record_interaction(
            args.lead_id, args.type, summary=args.summary
        )
        print(f"recorded interaction on {item['id']} (count: {item['interaction_count']})")
    finally:
        db.close()
    return 0


def cmd_leads_score(args: argparse.Namespace) -> int:
    from .domains.leads import LeadEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = LeadEngine(db).score(args.lead_id)
        print(f"score: {result['score']}")
        for k, v in result["breakdown"]["components"].items():
            print(f"  {k:20s} {v:.2f}")
    finally:
        db.close()
    return 0


# ---- CRM (SPEC-029) -----------------------------------------------------

def cmd_crm_create_deal(args: argparse.Namespace) -> int:
    from .domains.crm import CRMEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CRMEngine(db).create_deal(
            name=args.name, lead_id=args.lead_id, value=args.value,
            currency=args.currency,
        )
        print(f"created {item['id']} | {item['stage']} | {item['name']}")
        print(f"  value: {item.get('value', '-')} {item['currency']}")
    finally:
        db.close()
    return 0


def cmd_crm_list_deals(args: argparse.Namespace) -> int:
    from .domains.crm import CRMEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = CRMEngine(db).list_deals(status=args.status, stage=args.stage)
        print(f"{len(items)} deal(s)")
        for item in items:
            value = f"value={item.get('value', '-')}" if item.get('value') else "value=-"
            print(f"  {item['stage']:14s} {value:14s} {item['name']}")
    finally:
        db.close()
    return 0


def cmd_crm_transition(args: argparse.Namespace) -> int:
    from .domains.crm import CRMEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CRMEngine(db).transition_deal(args.deal_id, args.stage)
        print(f"{item['id']}: {item['stage']} (probability: {item['probability']})")
    finally:
        db.close()
    return 0


def cmd_crm_pipeline(args: argparse.Namespace) -> int:
    from .domains.crm import CRMEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = CRMEngine(db).pipeline_summary()
        print(f"Pipeline: {result['total_deals']} deals | value={result['total_value']} | weighted={result['weighted_value']:.0f}")
        for stage, data in result["stages"].items():
            if data["count"] > 0:
                print(f"  {stage:14s} {data['count']:3d} deals | value={data['value']:10.0f}")
    finally:
        db.close()
    return 0


def cmd_crm_create_activity(args: argparse.Namespace) -> int:
    from .domains.crm import CRMEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CRMEngine(db).create_activity(
            activity_type=args.type, deal_id=args.deal_id, lead_id=args.lead_id,
            subject=args.subject, due_date=args.due_date,
        )
        print(f"created activity {item['id']} | {item['activity_type']}")
    finally:
        db.close()
    return 0


def cmd_crm_complete_activity(args: argparse.Namespace) -> int:
    from .domains.crm import CRMEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CRMEngine(db).complete_activity(args.activity_id, notes=args.notes)
        print(f"{item['id']}: completed")
    finally:
        db.close()
    return 0


# ---- Meetings (SPEC-031/032) --------------------------------------------

def cmd_meetings_schedule(args: argparse.Namespace) -> int:
    from .domains.meetings import MeetingEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = MeetingEngine(db).schedule(
            title=args.title, scheduled_at=args.at, lead_id=args.lead_id,
            deal_id=args.deal_id, meeting_type=args.type,
            duration_minutes=args.duration,
        )
        print(f"scheduled {item['id']} | {item['status']} | {item['title']}")
        print(f"  at: {item['scheduled_at']} type: {item['meeting_type']}")
    finally:
        db.close()
    return 0


def cmd_meetings_list(args: argparse.Namespace) -> int:
    from .domains.meetings import MeetingEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = MeetingEngine(db).list(status=args.status, limit=args.limit)
        print(f"{len(items)} meeting(s)")
        for item in items:
            print(f"  {item['status']:12s} {item['scheduled_at'][:19]} {item['title']}")
    finally:
        db.close()
    return 0


def cmd_meetings_upcoming(args: argparse.Namespace) -> int:
    from .domains.meetings import MeetingEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = MeetingEngine(db).upcoming(limit=args.limit)
        print(f"{len(items)} upcoming meeting(s)")
        for item in items:
            print(f"  {item['scheduled_at'][:19]} {item['title']} ({item['meeting_type']})")
    finally:
        db.close()
    return 0


def cmd_meetings_complete(args: argparse.Namespace) -> int:
    from .domains.meetings import MeetingEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = MeetingEngine(db).complete(args.meeting_id, notes=args.notes, outcome=args.outcome)
        print(f"{item['id']}: {item['status']}")
        if item.get('outcome'):
            print(f"  outcome: {item['outcome']}")
    finally:
        db.close()
    return 0


def cmd_meetings_cancel(args: argparse.Namespace) -> int:
    from .domains.meetings import MeetingEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = MeetingEngine(db).cancel(args.meeting_id)
        print(f"{item['id']}: {item['status']}")
    finally:
        db.close()
    return 0


def cmd_meetings_analytics(args: argparse.Namespace) -> int:
    from .domains.meetings import MeetingEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = MeetingEngine(db).analytics()
        print(f"Meetings: {result['total']} total | {result['completed']} completed | {result['no_show']} no-show")
        print(f"  completion rate: {result['completion_rate']}% | no-show rate: {result['no_show_rate']}%")
    finally:
        db.close()
    return 0


# ---- Email Nurture (SPEC-033) -------------------------------------------

def cmd_email_create_sequence(args: argparse.Namespace) -> int:
    from .domains.email_nurture import EmailNurtureEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = EmailNurtureEngine(db).create_sequence(
            name=args.name, trigger_event=args.trigger, description=args.description,
        )
        print(f"created {item['id']} | {item['status']} | {item['name']}")
    finally:
        db.close()
    return 0


def cmd_email_list_sequences(args: argparse.Namespace) -> int:
    from .domains.email_nurture import EmailNurtureEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = EmailNurtureEngine(db).list_sequences(status=args.status)
        print(f"{len(items)} sequence(s)")
        for item in items:
            print(f"  {item['status']:10s} {item['name']:30s} trigger={item['trigger_event']}")
    finally:
        db.close()
    return 0


def cmd_email_enroll(args: argparse.Namespace) -> int:
    from .domains.email_nurture import EmailNurtureEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = EmailNurtureEngine(db).enroll_lead(args.sequence_id, args.lead_id)
        print(f"enrolled {args.lead_id} in {args.sequence_id} (step: {item['current_step']})")
    finally:
        db.close()
    return 0


def cmd_email_suppress(args: argparse.Namespace) -> int:
    from .domains.email_nurture import EmailNurtureEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = EmailNurtureEngine(db).suppress_email(args.email, reason=args.reason)
        print(f"suppressed {result['email']} (reason: {result['reason']})")
    finally:
        db.close()
    return 0


def cmd_email_list_suppressions(args: argparse.Namespace) -> int:
    from .domains.email_nurture import EmailNurtureEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = EmailNurtureEngine(db).list_suppressions()
        print(f"{len(items)} suppressed email(s)")
        for item in items:
            print(f"  {item['email']:30s} reason={item['reason']}")
    finally:
        db.close()
    return 0


def register_phase3_parsers(sub) -> None:
    """Register Phase 3 CLI subparsers."""
    from .domains.leads import LEAD_SOURCES
    from .domains.meetings import MEETING_TYPES
    from .domains.email_nurture import TRIGGER_EVENTS

    # ---- leads ----
    p_leads = sub.add_parser("leads", help="lead intelligence (SPEC-026/027/028)")
    p_leads_sub = p_leads.add_subparsers(dest="leads_action", required=True)

    p_lcapture = p_leads_sub.add_parser("capture", help="capture a new lead")
    p_lcapture.add_argument("email")
    p_lcapture.add_argument("--name", default=None)
    p_lcapture.add_argument("--company", default=None)
    p_lcapture.add_argument("--source", default="manual", choices=LEAD_SOURCES)
    p_lcapture.add_argument("--tag", action="append", dest="tags", default=None)
    p_lcapture.set_defaults(func=cmd_leads_capture)

    p_llist = p_leads_sub.add_parser("list", help="list leads")
    p_llist.add_argument("--status", default=None)
    p_llist.add_argument("--source", default=None)
    p_llist.add_argument("--limit", type=int, default=50)
    p_llist.set_defaults(func=cmd_leads_list)

    p_lshow = p_leads_sub.add_parser("show", help="show lead details")
    p_lshow.add_argument("lead_id")
    p_lshow.set_defaults(func=cmd_leads_show)

    p_ltrans = p_leads_sub.add_parser("status", help="transition lead status")
    p_ltrans.add_argument("lead_id")
    p_ltrans.add_argument("status", choices=["QUALIFIED", "ENGAGED", "MEETING_SCHEDULED", "OPPORTUNITY_CREATED", "WON", "LOST", "DISQUALIFIED", "ARCHIVED"])
    p_ltrans.set_defaults(func=cmd_leads_transition)

    p_lqualify = p_leads_sub.add_parser("qualify", help="qualify a lead")
    p_lqualify.add_argument("lead_id")
    p_lqualify.add_argument("--method", default="BANT", choices=["BANT", "MEDDIC", "GPCTBA", "CHAMP", "ANTICIPATE"])
    p_lqualify.set_defaults(func=cmd_leads_qualify)

    p_ldisq = p_leads_sub.add_parser("disqualify", help="disqualify a lead")
    p_ldisq.add_argument("lead_id")
    p_ldisq.add_argument("--reason", default="other", choices=["no_budget", "no_authority", "no_need", "bad_timing", "competitor_selected", "not_ideal_fit", "unresponsive", "other"])
    p_ldisq.set_defaults(func=cmd_leads_disqualify)

    p_linteract = p_leads_sub.add_parser("interact", help="record an interaction")
    p_linteract.add_argument("lead_id")
    p_linteract.add_argument("type", choices=["email", "call", "meeting", "note", "demo"])
    p_linteract.add_argument("--summary", default=None)
    p_linteract.set_defaults(func=cmd_leads_interact)

    p_lscore = p_leads_sub.add_parser("score", help="compute lead score")
    p_lscore.add_argument("lead_id")
    p_lscore.set_defaults(func=cmd_leads_score)

    # ---- crm ----
    p_crm = sub.add_parser("crm", help="CRM deal pipeline (SPEC-029)")
    p_crm_sub = p_crm.add_subparsers(dest="crm_action", required=True)

    p_crm_create = p_crm_sub.add_parser("create-deal", help="create a deal")
    p_crm_create.add_argument("name")
    p_crm_create.add_argument("--lead-id", default=None)
    p_crm_create.add_argument("--value", type=float, default=None)
    p_crm_create.add_argument("--currency", default="BRL")
    p_crm_create.set_defaults(func=cmd_crm_create_deal)

    p_crm_list = p_crm_sub.add_parser("list-deals", help="list deals")
    p_crm_list.add_argument("--status", default=None)
    p_crm_list.add_argument("--stage", default=None)
    p_crm_list.set_defaults(func=cmd_crm_list_deals)

    p_crm_trans = p_crm_sub.add_parser("transition", help="move deal to new stage")
    p_crm_trans.add_argument("deal_id")
    p_crm_trans.add_argument("stage", choices=["QUALIFICATION", "PROPOSAL", "NEGOTIATION", "CONTRACT", "CLOSED_WON", "CLOSED_LOST"])
    p_crm_trans.set_defaults(func=cmd_crm_transition)

    p_crm_pipe = p_crm_sub.add_parser("pipeline", help="pipeline summary")
    p_crm_pipe.set_defaults(func=cmd_crm_pipeline)

    p_crm_act = p_crm_sub.add_parser("create-activity", help="create an activity")
    p_crm_act.add_argument("type", choices=["call", "email", "meeting", "task", "note", "demo", "follow_up"])
    p_crm_act.add_argument("--deal-id", default=None)
    p_crm_act.add_argument("--lead-id", default=None)
    p_crm_act.add_argument("--subject", default=None)
    p_crm_act.add_argument("--due-date", default=None)
    p_crm_act.set_defaults(func=cmd_crm_create_activity)

    p_crm_complete = p_crm_sub.add_parser("complete-activity", help="complete an activity")
    p_crm_complete.add_argument("activity_id")
    p_crm_complete.add_argument("--notes", default=None)
    p_crm_complete.set_defaults(func=cmd_crm_complete_activity)

    # ---- meetings ----
    p_meetings = sub.add_parser("meetings", help="meeting scheduling (SPEC-031/032)")
    p_meetings_sub = p_meetings.add_subparsers(dest="meetings_action", required=True)

    p_mschedule = p_meetings_sub.add_parser("schedule", help="schedule a meeting")
    p_mschedule.add_argument("title")
    p_mschedule.add_argument("--at", required=True, help="ISO datetime")
    p_mschedule.add_argument("--lead-id", default=None)
    p_mschedule.add_argument("--deal-id", default=None)
    p_mschedule.add_argument("--type", default="discovery", choices=MEETING_TYPES)
    p_mschedule.add_argument("--duration", type=int, default=30)
    p_mschedule.set_defaults(func=cmd_meetings_schedule)

    p_mlist = p_meetings_sub.add_parser("list", help="list meetings")
    p_mlist.add_argument("--status", default=None)
    p_mlist.add_argument("--limit", type=int, default=50)
    p_mlist.set_defaults(func=cmd_meetings_list)

    p_mupcoming = p_meetings_sub.add_parser("upcoming", help="upcoming meetings")
    p_mupcoming.add_argument("--limit", type=int, default=10)
    p_mupcoming.set_defaults(func=cmd_meetings_upcoming)

    p_mcomplete = p_meetings_sub.add_parser("complete", help="complete a meeting")
    p_mcomplete.add_argument("meeting_id")
    p_mcomplete.add_argument("--notes", default=None)
    p_mcomplete.add_argument("--outcome", default=None)
    p_mcomplete.set_defaults(func=cmd_meetings_complete)

    p_mcancel = p_meetings_sub.add_parser("cancel", help="cancel a meeting")
    p_mcancel.add_argument("meeting_id")
    p_mcancel.set_defaults(func=cmd_meetings_cancel)

    p_manalytics = p_meetings_sub.add_parser("analytics", help="meeting analytics")
    p_manalytics.set_defaults(func=cmd_meetings_analytics)

    # ---- email ----
    p_email = sub.add_parser("email", help="email nurture (SPEC-033)")
    p_email_sub = p_email.add_subparsers(dest="email_action", required=True)

    p_eseq = p_email_sub.add_parser("create-sequence", help="create email sequence")
    p_eseq.add_argument("name")
    p_eseq.add_argument("--trigger", required=True, choices=TRIGGER_EVENTS)
    p_eseq.add_argument("--description", default=None)
    p_eseq.set_defaults(func=cmd_email_create_sequence)

    p_elist = p_email_sub.add_parser("list-sequences", help="list sequences")
    p_elist.add_argument("--status", default=None)
    p_elist.set_defaults(func=cmd_email_list_sequences)

    p_eenroll = p_email_sub.add_parser("enroll", help="enroll lead in sequence")
    p_eenroll.add_argument("sequence_id")
    p_eenroll.add_argument("lead_id")
    p_eenroll.set_defaults(func=cmd_email_enroll)

    p_esupp = p_email_sub.add_parser("suppress", help="suppress an email")
    p_esupp.add_argument("email")
    p_esupp.add_argument("--reason", default="unsubscribed")
    p_esupp.set_defaults(func=cmd_email_suppress)

    p_elistsupp = p_email_sub.add_parser("list-suppressions", help="list suppressed emails")
    p_elistsupp.set_defaults(func=cmd_email_list_suppressions)


# ---- Academy (SPEC-036) -------------------------------------------------

def cmd_academy_create(args: argparse.Namespace) -> int:
    from .domains.academy import AcademyEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = AcademyEngine(db).create(
            title=args.title, content_type=args.type,
            description=args.description, difficulty=args.difficulty,
            duration_minutes=args.duration, parent_id=args.parent_id,
        )
        print(f"created {item['id']} | {item['status']} | {item['content_type']}")
        print(f"  title: {item['title']} ({item['slug']})")
    finally:
        db.close()
    return 0


def cmd_academy_list(args: argparse.Namespace) -> int:
    from .domains.academy import AcademyEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = AcademyEngine(db).list(
            content_type=args.type, status=args.status, limit=args.limit
        )
        print(f"{len(items)} academy item(s)")
        for item in items:
            print(f"  {item['status']:10s} {item['content_type']:10s} {item['difficulty']:12s} {item['title']}")
    finally:
        db.close()
    return 0


def cmd_academy_publish(args: argparse.Namespace) -> int:
    from .domains.academy import AcademyEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = AcademyEngine(db).publish(args.content_id)
        print(f"{item['id']}: {item['status']}")
    finally:
        db.close()
    return 0


def cmd_academy_enroll(args: argparse.Namespace) -> int:
    from .domains.academy import AcademyEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = AcademyEngine(db).enroll_learner(args.content_id, args.learner_id)
        print(f"enrolled {args.learner_id} in {args.content_id} (status: {item['status']})")
    finally:
        db.close()
    return 0


def cmd_academy_progress(args: argparse.Namespace) -> int:
    from .domains.academy import AcademyEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = AcademyEngine(db).update_progress(
            args.content_id, args.learner_id, args.progress
        )
        print(f"{item['learner_id']}: {item['progress_pct']}% ({item['status']})")
    finally:
        db.close()
    return 0


def cmd_academy_certify(args: argparse.Namespace) -> int:
    from .domains.academy import AcademyEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        cert = AcademyEngine(db).issue_certification(
            args.content_id, args.learner_id, score=args.score
        )
        print(f"certified {args.learner_id} (score: {cert.get('assessment_score', '-')})")
    finally:
        db.close()
    return 0


def cmd_academy_analytics(args: argparse.Namespace) -> int:
    from .domains.academy import AcademyEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = AcademyEngine(db).content_analytics(args.content_id)
        print(f"{result['title']}: {result['total_learners']} learners")
        print(f"  enrolled: {result['enrolled']} | in_progress: {result['in_progress']}")
        print(f"  completed: {result['completed']} | dropped: {result['dropped']}")
        print(f"  completion rate: {result['completion_rate']}%")
    finally:
        db.close()
    return 0


# ---- Community (SPEC-037) ------------------------------------------------

def cmd_community_add_member(args: argparse.Namespace) -> int:
    from .domains.community import CommunityEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        member = CommunityEngine(db).add_member(
            name=args.name, email=args.email, platform=args.platform, role=args.role,
        )
        print(f"added {member['name']} ({member['platform']}, role: {member['role']})")
    finally:
        db.close()
    return 0


def cmd_community_list_members(args: argparse.Namespace) -> int:
    from .domains.community import CommunityEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = CommunityEngine(db).list_members(platform=args.platform, limit=args.limit)
        print(f"{len(items)} member(s)")
        for item in items:
            print(f"  {item['platform']:10s} {item['role']:10s} {item['name']}")
    finally:
        db.close()
    return 0


def cmd_community_create_thread(args: argparse.Namespace) -> int:
    from .domains.community import CommunityEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        thread = CommunityEngine(db).create_thread(
            channel=args.channel, title=args.title, author_id=args.author_id,
        )
        print(f"created thread {thread['id']} | {thread['channel']} | {thread['title']}")
    finally:
        db.close()
    return 0


def cmd_community_add_reply(args: argparse.Namespace) -> int:
    from .domains.community import CommunityEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        reply = CommunityEngine(db).add_reply(
            args.thread_id, args.author_id, args.content
        )
        print(f"added reply {reply['id']}")
    finally:
        db.close()
    return 0


def cmd_community_overview(args: argparse.Namespace) -> int:
    from .domains.community import CommunityEngine
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = CommunityEngine(db).community_overview()
        print(f"Members: {result['total_members']} | Threads: {result['total_threads']}")
        print(f"  Open threads: {result['open_threads']}")
        print(f"  Platforms: {', '.join(result['platforms'])}")
    finally:
        db.close()
    return 0


def register_phase4_parsers(sub) -> None:
    """Register Phase 4 CLI subparsers."""
    from .domains.academy import CONTENT_TYPES, DIFFICULTY_LEVELS
    from .domains.community import PLATFORMS, MEMBER_ROLES

    # ---- academy ----
    p_academy = sub.add_parser("academy", help="academy content (SPEC-036)")
    p_academy_sub = p_academy.add_subparsers(dest="academy_action", required=True)

    p_acreate = p_academy_sub.add_parser("create", help="create academy content")
    p_acreate.add_argument("title")
    p_acreate.add_argument("--type", default="lesson", choices=CONTENT_TYPES)
    p_acreate.add_argument("--description", default=None)
    p_acreate.add_argument("--difficulty", default="beginner", choices=DIFFICULTY_LEVELS)
    p_acreate.add_argument("--duration", type=int, default=None)
    p_acreate.add_argument("--parent-id", default=None)
    p_acreate.set_defaults(func=cmd_academy_create)

    p_alist = p_academy_sub.add_parser("list", help="list academy content")
    p_alist.add_argument("--type", default=None, choices=CONTENT_TYPES)
    p_alist.add_argument("--status", default=None)
    p_alist.add_argument("--limit", type=int, default=50)
    p_alist.set_defaults(func=cmd_academy_list)

    p_apublish = p_academy_sub.add_parser("publish", help="publish content")
    p_apublish.add_argument("content_id")
    p_apublish.set_defaults(func=cmd_academy_publish)

    p_aenroll = p_academy_sub.add_parser("enroll", help="enroll learner")
    p_aenroll.add_argument("content_id")
    p_aenroll.add_argument("learner_id")
    p_aenroll.set_defaults(func=cmd_academy_enroll)

    p_aprogress = p_academy_sub.add_parser("progress", help="update progress")
    p_aprogress.add_argument("content_id")
    p_aprogress.add_argument("learner_id")
    p_aprogress.add_argument("progress", type=float)
    p_aprogress.set_defaults(func=cmd_academy_progress)

    p_acertify = p_academy_sub.add_parser("certify", help="issue certification")
    p_acertify.add_argument("content_id")
    p_acertify.add_argument("learner_id")
    p_acertify.add_argument("--score", type=float, default=None)
    p_acertify.set_defaults(func=cmd_academy_certify)

    p_aanalytics = p_academy_sub.add_parser("content-analytics", help="content analytics")
    p_aanalytics.add_argument("content_id")
    p_aanalytics.set_defaults(func=cmd_academy_analytics)


    p_aanalytics.add_argument("content_id")
    p_aanalytics.set_defaults(func=cmd_academy_analytics)

    # ---- community ----
    p_community = sub.add_parser("community", help="community management (SPEC-037)")
    p_comm_sub = p_community.add_subparsers(dest="community_action", required=True)

    p_cadd = p_comm_sub.add_parser("add-member", help="add community member")
    p_cadd.add_argument("name")
    p_cadd.add_argument("--email", default=None)
    p_cadd.add_argument("--platform", default="internal", choices=PLATFORMS)
    p_cadd.add_argument("--role", default="member", choices=MEMBER_ROLES)
    p_cadd.set_defaults(func=cmd_community_add_member)

    p_clist = p_comm_sub.add_parser("list-members", help="list members")
    p_clist.add_argument("--platform", default=None)
    p_clist.add_argument("--limit", type=int, default=50)
    p_clist.set_defaults(func=cmd_community_list_members)

    p_cthread = p_comm_sub.add_parser("create-thread", help="create thread")
    p_cthread.add_argument("channel")
    p_cthread.add_argument("title")
    p_cthread.add_argument("--author-id", default=None)
    p_cthread.set_defaults(func=cmd_community_create_thread)

    p_creply = p_comm_sub.add_parser("add-reply", help="add reply")
    p_creply.add_argument("thread_id")
    p_creply.add_argument("author_id")
    p_creply.add_argument("content")
    p_creply.set_defaults(func=cmd_community_add_reply)

    p_coverview = p_comm_sub.add_parser("overview", help="community overview")
    p_coverview.set_defaults(func=cmd_community_overview)


# ---- Control Center Phase 5 enhancements ---------------------------------

def cmd_control_center_rag_debug(args: argparse.Namespace) -> int:
    from .domains.control_center import ControlCenter
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = ControlCenter(db).rag_debugger(args.query)
        print(f"RAG Debug: {result['results_count']} results for '{args.query}'")
        print(f"Index: {result['index_stats']['documents']} docs, {result['index_stats']['embeddings']} embeddings")
        for i, r in enumerate(result['results'][:5], 1):
            print(f"\n  [{i}] score={r['score']:.3f} ({r['strategy']})")
            print(f"      {r['title']} ({r['source']})")
            print(f"      {r['snippet'][:100]}...")
    finally:
        db.close()
    return 0


def cmd_control_center_run_debug(args: argparse.Namespace) -> int:
    from .domains.control_center import ControlCenter
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = ControlCenter(db).run_debugger(args.run_id)
        if "error" in result:
            print(f"Error: {result['error']}")
            return 1
        run = result["run"]
        print(f"Run: {run['id'][:12]}... | status={run['status']}")
        print(f"  workflow: {run.get('workflow_id', '-')} | agent: {run.get('agent', '-')}")
        print(f"  started: {run['started_at'][:19]} | duration: {result.get('duration_ms', '-')}ms")
        if result.get("error"):
            print(f"  error: {result['error']}")
        print(f"\n  Events ({len(result['events'])}):")
        for e in result["events"][:5]:
            print(f"    - {e['type']} @ {e['created_at'][:19]}")
    finally:
        db.close()
    return 0


def cmd_control_center_backup(args: argparse.Namespace) -> int:
    from .domains.control_center import ControlCenter
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        backup_dir = args.dir or str(Path(args.root) / "backups")
        from pathlib import Path
        import datetime
        backup_name = f"geos-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        backup_path = str(Path(backup_dir) / backup_name)
        result = ControlCenter(db).backup_database(backup_path)
        if "error" in result:
            print(f"Error: {result['error']}")
            return 1
        print(f"Backup created: {result['destination']}")
        print(f"  size: {result['size_bytes']:,} bytes")
    finally:
        db.close()
    return 0


def cmd_control_center_list_backups(args: argparse.Namespace) -> int:
    from .domains.control_center import ControlCenter
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        backups = ControlCenter(db).list_backups(args.dir)
        print(f"{len(backups)} backup(s)")
        for b in backups:
            print(f"  {b['name']} ({b['size_bytes']:,} bytes)")
    finally:
        db.close()
    return 0


def cmd_control_center_audit(args: argparse.Namespace) -> int:
    from .domains.control_center import ControlCenter
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = ControlCenter(db).self_audit()
        summary = result["summary"]
        print(f"Self-Audit: {summary['score']}% score ({summary['passed']} passed, {summary['warnings']} warnings, {summary['errors']} errors)")
        print("\nChecks:")
        for check in result["checks"]:
            status_icon = "✓" if check["status"] == "ok" else "⚠" if check["status"] == "warning" else "✗"
            print(f"  {status_icon} {check['name']}: {check['detail']}")
        if result["recommendations"]:
            print("\nRecommendations:")
            for rec in result["recommendations"]:
                print(f"  → {rec}")
    finally:
        db.close()
    return 0


def register_phase5_parsers(sub) -> None:
    """Register Phase 5 CLI subparsers (Control Center enhancements)."""
    # Enhance existing control-center parser
    p_cc = None
    # We need to find the existing control-center parser
    # Since it's already registered, we'll add subcommands to it
    # by modifying the existing parser
    
    # For now, create a new 'cc' command group for Phase 5 features
    p_cc5 = sub.add_parser("cc", help="Control Center Phase 5 (RAG debug, backups, audit)")
    p_cc5_sub = p_cc5.add_subparsers(dest="cc_action", required=True)
    
    p_rag = p_cc5_sub.add_parser("rag-debug", help="debug RAG retrieval")
    p_rag.add_argument("query")
    p_rag.set_defaults(func=cmd_control_center_rag_debug)
    
    p_rundebug = p_cc5_sub.add_parser("run-debug", help="debug a specific run")
    p_rundebug.add_argument("run_id")
    p_rundebug.set_defaults(func=cmd_control_center_run_debug)
    
    p_backup = p_cc5_sub.add_parser("backup", help="backup database")
    p_backup.add_argument("--dir", default=None)
    p_backup.set_defaults(func=cmd_control_center_backup)
    
    p_listbackups = p_cc5_sub.add_parser("list-backups", help="list backups")
    p_listbackups.add_argument("--dir", default=None)
    p_listbackups.set_defaults(func=cmd_control_center_list_backups)
    
    p_audit = p_cc5_sub.add_parser("audit", help="run self-audit")
    p_audit.set_defaults(func=cmd_control_center_audit)
