"""Demonstration data.

The seed does **not** insert hand-written rows for sources: it imports the files
in ``samples/`` through the real ingest pipeline. The demo therefore exercises
exactly the code path a user's own file takes, and if extraction breaks, the
seed breaks with it.

Everything created here carries ``is_demo=True`` and the ``demo`` tag, and can
be removed in one call (``DELETE /api/maintenance/demo``).
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import PROJECT_ROOT
from .domain import (
    ClaimStance,
    DossierStatus,
    DossierSubject,
    EntityKind,
    EvidenceStance,
    KnowledgeKind,
    SourceKind,
    TargetType,
)
from .models import (
    Collection,
    CollectionItem,
    Comparison,
    ComparisonCell,
    ComparisonDimension,
    ComparisonSubject,
    Dossier,
    Entity,
    Excerpt,
    KnowledgeExcerpt,
    KnowledgeObject,
    Source,
)
from .services import dossiers as dossier_service
from .services import entities as entity_service
from .services import indexer, ingest, links, tagging

SAMPLES_DIR = PROJECT_ROOT / "samples"
DEMO_TAG = "demo"

FILES: list[tuple[str, SourceKind, dict[str, Any]]] = [
    (
        "helios-q3-fy2026-review.pdf",
        SourceKind.PDF,
        {"tags": ["demo", "earnings", "ai-compute", "hlsx"]},
    ),
    (
        "momentum-masterclass-ep41.txt",
        SourceKind.TRANSCRIPT,
        {"tags": ["demo", "process", "risk-management", "transcript"]},
    ),
    (
        "swing-trading-rules.md",
        SourceKind.MARKDOWN,
        {"tags": ["demo", "rules", "process"]},
    ),
    (
        "market-breadth-2026.csv",
        SourceKind.CSV,
        {"tags": ["demo", "breadth", "market-regime"]},
    ),
    (
        "positions-snapshot.json",
        SourceKind.JSON,
        {"tags": ["demo", "portfolio"]},
    ),
    (
        "hlsx-daily-chart.png",
        SourceKind.IMAGE,
        {"tags": ["demo", "chart", "hlsx"]},
    ),
    (
        "power-constraint-article.txt",
        SourceKind.WEB_ARTICLE,
        {"tags": ["demo", "power", "ai-infrastructure"]},
    ),
]


class SeedError(RuntimeError):
    pass


def _find(source: Source, needle: str) -> tuple[int, int, str]:
    """Locate a verbatim span in the extracted text.

    The match is whitespace-flexible (extracted text is hard-wrapped) but the
    returned text is the source's own characters, so a demo excerpt always
    quotes the document exactly. A missing phrase raises rather than degrading
    into an approximate offset.
    """

    pattern = re.compile(r"\s+".join(re.escape(word) for word in needle.split()))
    match = pattern.search(source.text)
    if match is None:
        raise SeedError(f"seed phrase not found in {source.title!r}: {needle[:60]!r}")
    return match.start(), match.end(), match.group(0)


def _excerpt(session: Session, source: Source, needle: str, note: str | None = None) -> Excerpt:
    start, end, text = _find(source, needle)
    document = next(
        (d for d in source.documents if d.char_start <= start < max(d.char_end, d.char_start + 1)), None
    )
    locator = dict(document.locator) if document else {}
    locator["char_start"] = start
    excerpt = Excerpt(
        source_id=source.id,
        document_id=document.id if document else None,
        text=text,
        note=note,
        char_start=start,
        char_end=end,
        locator=locator,
        origin="seed",
        created_via="seed",
        is_demo=True,
    )
    session.add(excerpt)
    session.flush()
    indexer.index_excerpt(session, excerpt)
    return excerpt


def has_demo_data(session: Session) -> bool:
    return session.execute(select(Source).where(Source.is_demo.is_(True)).limit(1)).scalar_one_or_none() is not None


def remove_demo_data(session: Session) -> dict[str, int]:
    """Delete every object flagged as demonstration content."""

    removed = {"sources": 0, "excerpts": 0, "knowledge": 0, "dossiers": 0, "entities": 0,
               "comparisons": 0, "collections": 0}

    for dossier in session.execute(select(Dossier).where(Dossier.is_demo.is_(True))).scalars().all():
        indexer.remove(session, TargetType.DOSSIER, dossier.id)
        tagging.delete_taggings_for(session, TargetType.DOSSIER, dossier.id)
        links.delete_links_for(session, TargetType.DOSSIER, dossier.id)
        session.delete(dossier)
        removed["dossiers"] += 1

    for obj in session.execute(
        select(KnowledgeObject).where(KnowledgeObject.is_demo.is_(True))
    ).scalars().all():
        indexer.remove(session, TargetType.KNOWLEDGE, obj.id)
        tagging.delete_taggings_for(session, TargetType.KNOWLEDGE, obj.id)
        links.delete_links_for(session, TargetType.KNOWLEDGE, obj.id)
        session.delete(obj)
        removed["knowledge"] += 1

    for comparison in session.execute(select(Comparison).where(Comparison.is_demo.is_(True))).scalars().all():
        session.delete(comparison)
        removed["comparisons"] += 1

    for collection in session.execute(select(Collection).where(Collection.is_demo.is_(True))).scalars().all():
        session.delete(collection)
        removed["collections"] += 1

    for source in session.execute(select(Source).where(Source.is_demo.is_(True))).scalars().all():
        for excerpt in source.excerpts:
            indexer.remove(session, TargetType.EXCERPT, excerpt.id)
            tagging.delete_taggings_for(session, TargetType.EXCERPT, excerpt.id)
            links.delete_links_for(session, TargetType.EXCERPT, excerpt.id)
            removed["excerpts"] += 1
        indexer.remove(session, TargetType.SOURCE, source.id)
        tagging.delete_taggings_for(session, TargetType.SOURCE, source.id)
        links.delete_links_for(session, TargetType.SOURCE, source.id)
        session.delete(source)
        removed["sources"] += 1

    for entity in session.execute(select(Entity).where(Entity.is_demo.is_(True))).scalars().all():
        indexer.remove(session, TargetType.ENTITY, entity.id)
        links.delete_links_for(session, TargetType.ENTITY, entity.id)
        session.delete(entity)
        removed["entities"] += 1

    session.flush()
    return removed


def seed_demo_data(session: Session, *, reset: bool = False, samples_dir: Path | None = None) -> dict[str, Any]:
    samples_dir = samples_dir or SAMPLES_DIR
    if not samples_dir.is_dir():
        raise SeedError(
            f"samples directory not found at {samples_dir}. Run: python scripts/make_samples.py"
        )

    if reset:
        remove_demo_data(session)
    elif has_demo_data(session):
        return {"status": "skipped", "reason": "Demo data is already present. Pass reset=true to rebuild it."}

    sources: dict[str, Source] = {}
    warnings: list[str] = []

    # --- 1. import the sample files through the real pipeline ---------------
    for filename, kind, options in FILES:
        path = samples_dir / filename
        if not path.is_file():
            warnings.append(f"missing sample file: {filename}")
            continue
        data = path.read_bytes()
        if kind in {SourceKind.PDF, SourceKind.IMAGE}:
            outcome = ingest.ingest_bytes(
                session, data=data, filename=filename, kind=kind.value, force=True, is_demo=True, origin="seed"
            )
        else:
            outcome = ingest.ingest_text(
                session,
                text=data.decode("utf-8"),
                kind=kind.value,
                filename=filename,
                force=True,
                is_demo=True,
                origin="seed",
            )
        if outcome.source is None:
            warnings.append(f"{filename}: {outcome.message}")
            continue
        source = outcome.source
        source.is_demo = True
        tagging.set_tags(session, TargetType.SOURCE, source.id, options["tags"])
        sources[filename] = source

    required = {"helios-q3-fy2026-review.pdf", "momentum-masterclass-ep41.txt", "swing-trading-rules.md"}
    missing = required - set(sources)
    if missing:
        raise SeedError(f"could not import required sample files: {', '.join(sorted(missing))}")

    pdf = sources["helios-q3-fy2026-review.pdf"]
    transcript = sources["momentum-masterclass-ep41.txt"]
    rules_doc = sources["swing-trading-rules.md"]
    breadth = sources.get("market-breadth-2026.csv")
    article = sources.get("power-constraint-article.txt")
    chart = sources.get("hlsx-daily-chart.png")
    positions = sources.get("positions-snapshot.json")

    pdf.author = "Demo Research Desk"
    pdf.published_on = dt.date(2026, 7, 24)
    transcript.author = "Dana Ruiz"
    transcript.source_url = "https://example.invalid/momentum-masterclass/41"
    transcript.published_on = dt.date(2026, 6, 5)
    if article is not None:
        article.author = "Marta Iglesias"
        article.publisher = "The Grid Letter"
        article.published_on = dt.date(2026, 6, 18)

    # --- 2. entities --------------------------------------------------------
    helios = entity_service.get_or_create_entity(
        session,
        EntityKind.COMPANY,
        "Helios Semiconductor Inc.",
        description="Fictional accelerator and networking vendor used throughout the FORGE demo data.",
        data={"sector": "Semiconductors", "demo": True},
        is_demo=True,
    )
    hlsx = entity_service.get_or_create_entity(
        session,
        EntityKind.TICKER,
        "HLSX",
        description="Ticker of the fictional Helios Semiconductor Inc.",
        data={"exchange": "DEMO", "demo": True},
        is_demo=True,
    )
    dana = entity_service.get_or_create_entity(
        session, EntityKind.PERSON, "Dana Ruiz",
        description="Fictional momentum trader interviewed in the demo transcript.", is_demo=True,
    )
    ai_compute = entity_service.get_or_create_entity(
        session, EntityKind.THEME, "AI compute",
        description="Accelerators, rack-scale systems and the networking around them.", is_demo=True,
    )
    power_theme = entity_service.get_or_create_entity(
        session, EntityKind.THEME, "Power infrastructure",
        description="Generation, interconnection and energisation constraints on data centres.", is_demo=True,
    )
    breakout_topic = entity_service.get_or_create_entity(
        session, EntityKind.TOPIC, "Breakout management",
        description="What to do after entry: stops, adds, trailing references.", is_demo=True,
    )

    entity_service.attach_entities(
        session, pdf,
        [
            {"kind": EntityKind.COMPANY, "name": helios.name, "detector": "seed"},
            {"kind": EntityKind.TICKER, "name": hlsx.name, "detector": "seed"},
            {"kind": EntityKind.THEME, "name": ai_compute.name, "detector": "seed"},
            {"kind": EntityKind.THEME, "name": power_theme.name, "detector": "seed"},
        ],
    )
    entity_service.attach_entities(
        session, transcript,
        [
            {"kind": EntityKind.PERSON, "name": dana.name, "detector": "seed"},
            {"kind": EntityKind.TOPIC, "name": breakout_topic.name, "detector": "seed"},
        ],
    )
    if article is not None:
        entity_service.attach_entities(
            session, article,
            [
                {"kind": EntityKind.THEME, "name": power_theme.name, "detector": "seed"},
                {"kind": EntityKind.THEME, "name": ai_compute.name, "detector": "seed"},
            ],
        )
    if chart is not None:
        entity_service.attach_entities(
            session, chart, [{"kind": EntityKind.TICKER, "name": hlsx.name, "detector": "seed"}]
        )

    links.create_link(
        session,
        from_type=TargetType.ENTITY, from_id=hlsx.id,
        to_type=TargetType.ENTITY, to_id=helios.id,
        relation="ticker_of", origin="seed",
    )
    links.create_link(
        session,
        from_type=TargetType.ENTITY, from_id=dana.id,
        to_type=TargetType.SOURCE, to_id=transcript.id,
        relation="authored", origin="seed",
    )

    # --- 3. excerpts (verbatim, with real offsets) --------------------------
    ex_margin = _excerpt(
        session, pdf,
        "Gross margin expanded 240 basis points year over year to 58.4%",
        note="Margin expansion attributed to mix, not price - check whether that holds next quarter.",
    )
    ex_inventory = _excerpt(
        session, pdf,
        "Inventory rose 28% sequentially.",
        note="The line item most likely to invalidate the thesis if it repeats.",
    )
    ex_power = _excerpt(
        session, pdf,
        "Power availability at customer sites was named as a gating factor for deployments",
        note="Second consecutive quarter this was raised.",
    )
    ex_concentration = _excerpt(
        session, pdf,
        "the top three customers accounted for 44% of revenue, up from 38% a year ago",
    )
    ex_invalidation = _excerpt(
        session, transcript,
        "Write down what would make you exit before you enter.",
        note="The single most portable idea in the interview.",
    )
    ex_stop = _excerpt(
        session, transcript,
        "Below the last higher low that the breakout was launched from.",
    )
    ex_add = _excerpt(
        session, transcript,
        "Only into a new base. Adding into extension is how you turn a good trade",
    )
    ex_rule_risk = _excerpt(
        session, rules_doc,
        "Every entry has a written invalidation level derived from structure, not from a percentage.",
    )
    ex_energised = None
    if article is not None:
        ex_energised = _excerpt(
            session, article,
            "the ratio of energised to contracted capacity at the ten largest operators",
            note="Concrete, checkable metric proposed by the author.",
        )
    ex_breadth = None
    if breadth is not None:
        ex_breadth = _excerpt(
            session, breadth,
            "pct_above_50dma: 44.2",
            note="Trough of the June breadth washout in the demo data set.",
        )

    # --- 4. knowledge objects ----------------------------------------------
    insight = KnowledgeObject(
        kind=KnowledgeKind.INSIGHT,
        title="Helios margin expansion is mix-driven, so it is reversible",
        body=(
            "Management attributes the 240bp gross margin expansion to a richer mix of rack-scale "
            "systems rather than to pricing. Mix-driven margin is reversible in a way that pricing "
            "power is not: if the accelerator ramp pulls in lower-margin configurations, the "
            "expansion unwinds without anything 'going wrong'.\n\n"
            "What would change this: two consecutive quarters where segment gross margin holds "
            "above 58% while the HX-9 mix normalises."
        ),
        status="active",
        confidence=60,
        is_demo=True,
    )
    rule = KnowledgeObject(
        kind=KnowledgeKind.RULE,
        title="Define the invalidation level in writing before entering",
        body=(
            "Before any entry, write one sentence naming the structural level whose loss removes "
            "the reason for the trade. If the sentence cannot be written, the setup is an opinion, "
            "not a trade.\n\n"
            "Applies to: every new position.\n"
            "Does not apply to: adds into an existing, already-defined position."
        ),
        status="active",
        confidence=90,
        review_due_on=dt.date.today() + dt.timedelta(days=10),
        is_demo=True,
    )
    hypothesis = KnowledgeObject(
        kind=KnowledgeKind.HYPOTHESIS,
        title="Energised power capacity, not order backlog, sets the shipment ceiling in FY2027",
        body=(
            "If interconnection queues rather than component supply are the binding constraint, "
            "then order backlog stops being predictive of revenue and the ratio of energised to "
            "contracted megawatts becomes the leading indicator.\n\n"
            "Supporting evidence so far: management named power as a gating factor twice in a row; "
            "an independent article proposes the same metric.\n"
            "This would be refuted by: a quarter in which shipments accelerate while the energised "
            "ratio at large operators falls."
        ),
        status="open",
        confidence=45,
        review_due_on=dt.date.today() + dt.timedelta(days=30),
        is_demo=True,
    )
    decision = KnowledgeObject(
        kind=KnowledgeKind.DECISION,
        title="Hold HLSX at 5.8% and do not add until a new base forms",
        body=(
            "Decision: keep the position at its current weight. No add while the stock is extended "
            "from its last base, per the 'only add into a new base' rule.\n\n"
            "Alternatives considered: trim to 4% on the inventory build (rejected - one quarter is "
            "not a pattern); add to 8% on the margin beat (rejected - no defined risk point).\n"
            "Invalidation: a close below the last higher low, or two closes below the 21-day average."
        ),
        status="made",
        confidence=70,
        review_due_on=dt.date.today() + dt.timedelta(days=5),
        data={"position_weight_pct": "5.8", "ticker": "HLSX"},
        is_demo=True,
    )
    quote = KnowledgeObject(
        kind=KnowledgeKind.QUOTE,
        title="Ruiz on pre-committing to the exit",
        body="“Write down what would make you exit before you enter. If you cannot write it, you do not have a trade, you have an opinion.”",
        status="active",
        is_demo=True,
    )
    note = KnowledgeObject(
        kind=KnowledgeKind.NOTE,
        title="Follow-ups for the next Helios quarter",
        body=(
            "1. Days of inventory - did it normalise as guided?\n"
            "2. Networking attach rate - is it still climbing towards 55%?\n"
            "3. Customer concentration - did the top three go above 44%?\n"
            "4. Any disclosure of energised vs contracted capacity at customers."
        ),
        status="active",
        is_demo=True,
    )
    for obj in (insight, rule, hypothesis, decision, quote, note):
        session.add(obj)
    session.flush()

    evidence_map = [
        (insight, ex_margin, EvidenceStance.SUPPORTS, "Primary statement of the margin figure."),
        (insight, ex_inventory, EvidenceStance.CONTEXT, "Watch item that could reverse the mix effect."),
        (rule, ex_invalidation, EvidenceStance.SUPPORTS, "Source of the rule."),
        (rule, ex_rule_risk, EvidenceStance.SUPPORTS, "Same principle in the written rule set."),
        (hypothesis, ex_power, EvidenceStance.SUPPORTS, None),
        (decision, ex_add, EvidenceStance.SUPPORTS, "Reason for not adding here."),
        (quote, ex_invalidation, EvidenceStance.SUPPORTS, None),
    ]
    if ex_energised is not None:
        evidence_map.append((hypothesis, ex_energised, EvidenceStance.SUPPORTS, "Independent proposal of the same metric."))
    for obj, excerpt, stance, evidence_note in evidence_map:
        session.add(
            KnowledgeExcerpt(
                knowledge_id=obj.id, excerpt_id=excerpt.id, stance=stance.value, note=evidence_note
            )
        )
    session.flush()

    knowledge_tags = {
        insight: ["demo", "hlsx", "margins"],
        rule: ["demo", "rules", "risk-management"],
        hypothesis: ["demo", "power", "ai-infrastructure"],
        decision: ["demo", "hlsx", "portfolio"],
        quote: ["demo", "process"],
        note: ["demo", "hlsx", "follow-up"],
    }
    for obj, names in knowledge_tags.items():
        tagging.set_tags(session, TargetType.KNOWLEDGE, obj.id, names)
        indexer.index_knowledge(session, obj)

    # --- 5. dossiers --------------------------------------------------------
    company = Dossier(
        slug=dossier_service.unique_slug(session, "Helios Semiconductor (HLSX)"),
        title="Helios Semiconductor (HLSX)",
        subject_kind=DossierSubject.COMPANY.value,
        status=DossierStatus.ACTIVE.value,
        overview=(
            "**Demonstration dossier.** Helios Semiconductor is a fictional company created for the "
            "FORGE sample data set.\n\n"
            "Accelerator vendor whose data centre segment passed 70% of group revenue this quarter. "
            "The interesting question is not demand - it is whether the constraint has moved from "
            "silicon supply to customer power availability, and what that does to the shape of revenue."
        ),
        thesis=(
            "Helios is a platform, not a component vendor: the networking attach rate is the "
            "evidence. The risk to that thesis is not competition in FY2026, it is energisation "
            "timing at customers in FY2027."
        ),
        bull_case=(
            "- Networking attach rate rose from 39% to 47% year over year, which is what platform "
            "lock-in looks like before it shows up in pricing.\n"
            "- Operating expenses grew 22% against 41% revenue growth: the leverage is real.\n"
            "- Free cash flow margin of 31% funds the ramp without dilution."
        ),
        bear_case=(
            "- Margin expansion is mix-driven and therefore reversible.\n"
            "- Inventory rose 28% sequentially into a ramp that depends on customer readiness.\n"
            "- Top three customers are 44% of revenue and rising."
        ),
        risks=(
            "- Power availability gates deployments regardless of order book.\n"
            "- A competing accelerator programme samples in H1 CY2027.\n"
            "- Any quarter with book-to-bill below 1.0 breaks the ramp narrative."
        ),
        open_questions=(
            "1. Does days-of-inventory normalise by Q2 FY2027 as guided?\n"
            "2. Does the networking attach rate pass 55%?\n"
            "3. Do customers begin disclosing energised versus contracted capacity?"
        ),
        primary_entity_id=helios.id,
        is_demo=True,
    )
    setup = Dossier(
        slug=dossier_service.unique_slug(session, "Breakout continuation - position management"),
        title="Breakout continuation - position management",
        subject_kind=DossierSubject.SETUP.value,
        status=DossierStatus.ACTIVE.value,
        overview=(
            "**Demonstration dossier.** A setup dossier is about the *behaviour after entry*, not "
            "about finding entries. This one collects the rules, quotes and evidence that govern "
            "how a breakout position is held, added to, and exited."
        ),
        thesis=(
            "The edge in a breakout is not the entry trigger; it is surviving the digestion phase "
            "with the position intact and the risk defined."
        ),
        bull_case=(
            "- A structural stop keeps losses bounded without requiring a forecast.\n"
            "- Adding only into a new base guarantees every add has a defined risk point."
        ),
        bear_case=(
            "- Trailing a 21-period average whipsaws in choppy regimes.\n"
            "- 'Two closes below' is a heuristic, not a tested threshold in this data set."
        ),
        risks=(
            "- Applying the setup in a deteriorating breadth regime.\n"
            "- Confusing the discretionary profit exit with the mechanical invalidation exit."
        ),
        open_questions=(
            "1. Is 'two closes below the 21-day' better than a single close in a weak tape?\n"
            "2. How often does a leader recover after violating the last higher low?"
        ),
        is_demo=True,
    )
    session.add_all([company, setup])
    session.flush()

    for dossier, names in ((company, ["demo", "hlsx", "ai-compute"]), (setup, ["demo", "process", "rules"])):
        tagging.set_tags(session, TargetType.DOSSIER, dossier.id, names)
        indexer.index_dossier(session, dossier)

    company_items = [
        (TargetType.SOURCE, pdf.id, "sources", "Primary quarterly document."),
        (TargetType.EXCERPT, ex_margin.id, "evidence", None),
        (TargetType.EXCERPT, ex_inventory.id, "evidence", None),
        (TargetType.EXCERPT, ex_concentration.id, "evidence", None),
        (TargetType.KNOWLEDGE, insight.id, "knowledge", None),
        (TargetType.KNOWLEDGE, decision.id, "knowledge", None),
        (TargetType.KNOWLEDGE, hypothesis.id, "knowledge", None),
        (TargetType.KNOWLEDGE, note.id, "notes", None),
        (TargetType.ENTITY, helios.id, "entities", None),
        (TargetType.ENTITY, hlsx.id, "entities", None),
        (TargetType.ENTITY, power_theme.id, "entities", None),
    ]
    if article is not None:
        company_items.insert(1, (TargetType.SOURCE, article.id, "sources", "Independent view of the power constraint."))
    if chart is not None:
        company_items.insert(2, (TargetType.SOURCE, chart.id, "sources", "Chart snapshot at the time of the decision."))
    if ex_energised is not None:
        company_items.append((TargetType.EXCERPT, ex_energised.id, "evidence", None))
    for target_type, target_id, section, item_note in company_items:
        dossier_service.add_item(session, company, target_type, target_id, section=section, note=item_note)

    setup_items = [
        (TargetType.SOURCE, transcript.id, "sources", "Interview the setup rules are drawn from."),
        (TargetType.SOURCE, rules_doc.id, "sources", "Written operating rules."),
        (TargetType.EXCERPT, ex_stop.id, "evidence", None),
        (TargetType.EXCERPT, ex_add.id, "evidence", None),
        (TargetType.EXCERPT, ex_invalidation.id, "evidence", None),
        (TargetType.KNOWLEDGE, rule.id, "knowledge", None),
        (TargetType.KNOWLEDGE, quote.id, "knowledge", None),
        (TargetType.ENTITY, dana.id, "entities", None),
        (TargetType.ENTITY, breakout_topic.id, "entities", None),
    ]
    if breadth is not None:
        setup_items.append((TargetType.SOURCE, breadth.id, "sources", "Regime context for the setup."))
    if ex_breadth is not None:
        setup_items.append((TargetType.EXCERPT, ex_breadth.id, "evidence", None))
    for target_type, target_id, section, item_note in setup_items:
        dossier_service.add_item(session, setup, target_type, target_id, section=section, note=item_note)

    # --- 6. claims, evidence, timeline --------------------------------------
    claims = [
        (company, "Networking attach rate rose to 47% from 39% year over year", ClaimStance.BULL, 80, None),
        (company, "Operating expenses grew 22% against 41% revenue growth", ClaimStance.BULL, 85, None),
        (company, "Gross margin expansion is mix-driven and therefore reversible", ClaimStance.BEAR, 60, ex_margin),
        (company, "Inventory rose 28% sequentially ahead of the HX-9 ramp", ClaimStance.RISK, 70, ex_inventory),
        (company, "Top three customers are 44% of revenue, up from 38%", ClaimStance.RISK, 90, ex_concentration),
        (company, "Power availability at customer sites gates deployments", ClaimStance.RISK, 75, ex_power),
        (company, "Does the networking attach rate pass 55% next year?", ClaimStance.QUESTION, None, None),
        (setup, "A structural stop removes the need to forecast", ClaimStance.BULL, 80, ex_stop),
        (setup, "Adding only into a new base keeps every add risk-defined", ClaimStance.BULL, 75, ex_add),
        (setup, "'Two closes below the 21-day' is a heuristic, not a tested threshold", ClaimStance.RISK, 50, None),
    ]
    for dossier, text, stance, confidence, excerpt in claims:
        claim = dossier_service.add_claim(
            session, dossier, text=text, stance=stance.value, confidence=confidence, origin="seed"
        )
        if excerpt is not None:
            dossier_service.add_evidence(
                session, claim, excerpt_id=excerpt.id, stance=EvidenceStance.SUPPORTS.value
            )

    events = [
        (company, dt.date(2026, 5, 14), "Position opened at 5.8% weight", "Entry taken against the last higher low at 214.00.", "position"),
        (company, dt.date(2026, 6, 18), "Power constraint article published", "Independent article proposes energised/contracted capacity as the metric to track.", "research"),
        (company, dt.date(2026, 7, 24), "Q3 FY2026 results", "Revenue 4.12bn, +41% y/y. Guidance midpoint implies deceleration to 7.5% q/q.", "earnings"),
        (company, dt.date(2026, 7, 31), "Decision reviewed - hold, no add", "No new base, so no defined risk point for an add.", "decision"),
        (setup, dt.date(2026, 6, 5), "Masterclass episode 41 published", "Source interview for the position-management rules.", "research"),
        (setup, dt.date(2026, 6, 29), "Breadth trough", "Percentage above the 50-day average bottomed at 44.2 in the demo data set.", "regime"),
    ]
    for dossier, occurred_on, title, description, kind in events:
        source_id = pdf.id if kind == "earnings" else (transcript.id if kind == "research" and dossier is setup else None)
        dossier_service.add_event(
            session, dossier, occurred_on=occurred_on, title=title,
            description=description, kind=kind, source_id=source_id,
        )

    links.create_link(
        session, from_type=TargetType.DOSSIER, from_id=company.id,
        to_type=TargetType.DOSSIER, to_id=setup.id,
        relation="related_to", note="The position in HLSX is managed with this setup's rules.", origin="seed",
    )
    links.create_link(
        session, from_type=TargetType.KNOWLEDGE, from_id=decision.id,
        to_type=TargetType.KNOWLEDGE, to_id=rule.id,
        relation="derived_from", note="The decision applies this rule.", origin="seed",
    )
    links.create_link(
        session, from_type=TargetType.KNOWLEDGE, from_id=hypothesis.id,
        to_type=TargetType.SOURCE, to_id=pdf.id,
        relation="derived_from", origin="seed",
    )

    # --- 7. comparison ------------------------------------------------------
    comparison = Comparison(
        title="Open positions - risk and thesis comparison",
        subject_type=TargetType.ENTITY.value,
        description=(
            "Demonstration comparison across the three open demo positions. Numeric cells are exact "
            "decimals; text cells are user-written."
        ),
        is_demo=True,
    )
    session.add(comparison)
    session.flush()

    voltaris = entity_service.get_or_create_entity(
        session, EntityKind.TICKER, "VLTR", description="Fictional power infrastructure name (demo).", is_demo=True
    )
    coronex = entity_service.get_or_create_entity(
        session, EntityKind.TICKER, "CRNX", description="Fictional cybersecurity name (demo).", is_demo=True
    )
    subjects = []
    for position, entity in enumerate((hlsx, voltaris, coronex)):
        subject = ComparisonSubject(
            comparison_id=comparison.id,
            target_type=TargetType.ENTITY.value,
            target_id=entity.id,
            label=entity.name,
            position=position,
        )
        session.add(subject)
        subjects.append(subject)

    dimension_specs = [
        ("Book weight", "number", "%", True),
        ("Theme", "text", None, True),
        ("Distance to invalidation", "number", "%", False),
        ("Evidence in FORGE", "number", "items", True),
        ("Thesis in one line", "text", None, True),
    ]
    dimensions = []
    for position, (name, kind, unit, higher) in enumerate(dimension_specs):
        dimension = ComparisonDimension(
            comparison_id=comparison.id, name=name, kind=kind, unit=unit,
            higher_is_better=higher, weight=Decimal("1"), position=position,
        )
        session.add(dimension)
        dimensions.append(dimension)
    session.flush()

    cell_values: dict[tuple[int, int], tuple[str | None, Decimal | None]] = {
        (0, 0): (None, Decimal("5.8")), (1, 0): (None, Decimal("5.1")), (2, 0): (None, Decimal("4.4")),
        (0, 1): ("AI compute", None), (1, 1): ("Power infrastructure", None), (2, 1): ("Cybersecurity", None),
        (0, 2): (None, Decimal("7.4")), (1, 2): (None, Decimal("11.2")), (2, 2): (None, Decimal("5.9")),
        (0, 3): (None, Decimal("5")), (1, 3): (None, Decimal("1")), (2, 3): (None, Decimal("0")),
        (0, 4): ("Platform economics, gated by customer power availability", None),
        (1, 4): ("Sells into the constraint that gates everyone else", None),
        (2, 4): ("Least-researched position in the book - thesis not written yet", None),
    }
    for (subject_index, dimension_index), (text_value, numeric_value) in cell_values.items():
        session.add(
            ComparisonCell(
                comparison_id=comparison.id,
                subject_id=subjects[subject_index].id,
                dimension_id=dimensions[dimension_index].id,
                text_value=text_value,
                numeric_value=numeric_value,
                origin="seed",
            )
        )

    # --- 8. collection ------------------------------------------------------
    collection = Collection(
        slug="demo-reading-queue",
        name="Reading queue (demo)",
        description="Sources to revisit before the next quarterly update.",
        is_demo=True,
    )
    session.add(collection)
    session.flush()
    for position, source in enumerate([s for s in (pdf, article, transcript) if s is not None]):
        session.add(
            CollectionItem(
                collection_id=collection.id,
                target_type=TargetType.SOURCE.value,
                target_id=source.id,
                position=position,
            )
        )

    for source in sources.values():
        ingest.mark_reviewed(session, source)
    session.flush()

    return {
        "status": "created",
        "sources": len(sources),
        "excerpts": len([e for e in session.execute(select(Excerpt).where(Excerpt.is_demo.is_(True))).scalars()]),
        "knowledge": 6,
        "dossiers": 2,
        "entities": 8,
        "comparisons": 1,
        "collections": 1,
        "warnings": warnings,
        "note": "All demonstration content is tagged 'demo' and flagged is_demo=true.",
    }
