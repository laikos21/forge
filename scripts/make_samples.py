"""Generate the sample documents in ``samples/``.

Run once (``python scripts/make_samples.py``); the generated files are committed
so a fresh clone can seed and test without running this first.

All companies, tickers, figures and quotes in these files are **invented for
demonstration**. They are deliberately not real securities data: FORGE ships a
worked example, not a market data set.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from minipdf import build_pdf  # noqa: E402

DISCLAIMER = (
    "DEMONSTRATION CONTENT - Helios Semiconductor Inc. is a fictional company invented for "
    "the FORGE sample data set. Every figure below is illustrative and must not be used for "
    "any real analysis."
)

PDF_TEXT = f"""Helios Semiconductor Inc. (HLSX) - Q3 FY2026 Review

{DISCLAIMER}

1. Summary

Helios Semiconductor Inc. reported Q3 FY2026 revenue of 4.12 billion USD, up 41% year over
year and 9% sequentially. Data centre accelerators contributed 3.05 billion USD of that
total, the first quarter in which the segment passed 70% of group revenue. Gross margin
expanded 240 basis points year over year to 58.4%, which management attributed to a richer
mix of rack-scale systems rather than to pricing.

Management guided Q4 FY2026 revenue to a range of 4.35 to 4.55 billion USD. The midpoint
implies 7.5% sequential growth, a deceleration from the 9% posted this quarter. The company
described its supply position as "improving but still the binding constraint" on shipments.

2. Segment detail

Data centre: 3.05 billion USD, +62% year over year. Management said the segment is now
supply constrained rather than demand constrained, and that lead times on the flagship
HX-9 accelerator remain above 20 weeks.

Networking: 610 million USD, +18% year over year. The attach rate of Helios networking to
Helios accelerators rose to 47% from 39% a year ago.

Client and embedded: 460 million USD, -6% year over year. Management characterised this
segment as "stable but not a priority for incremental capacity".

3. Margins and operating leverage

Operating expenses grew 22% year over year, well below revenue growth, producing 810 basis
points of operating margin expansion. R&D remained 19% of revenue. The company reiterated
its long-term operating margin target of 34% to 36%.

Inventory rose 28% sequentially. The CFO said the build was deliberate and tied to the HX-9
ramp, and that days of inventory would normalise by Q2 FY2027. This is the single line item
that most deserves follow-up next quarter.

4. Capital allocation

Free cash flow was 1.28 billion USD, a 31% margin. The company repurchased 400 million USD
of stock and did not initiate a dividend. Net cash stood at 5.4 billion USD.

5. Risks flagged by management

Power availability at customer sites was named as a gating factor for deployments for the
second consecutive quarter. Management said several customers had "energised capacity
scheduled for calendar 2027 that we would ship into today if it existed".

Customer concentration remains elevated: the top three customers accounted for 44% of
revenue, up from 38% a year ago.

A competing accelerator programme from a large integrated device manufacturer is expected
to sample in the first half of calendar 2027. Management declined to comment on it.

6. What would change the view

The thesis depends on the data centre segment holding above 55% gross margin while the
HX-9 ramps. Two consecutive quarters of sequential gross margin compression, or a
book-to-bill below 1.0, would materially weaken it.

Conversely, evidence that the networking attach rate passes 55% would suggest the platform
is becoming harder to displace than the current multiple implies.
"""

TRANSCRIPT_TEXT = """Momentum Masterclass - Episode 41: Managing a Position After the Breakout

DEMONSTRATION CONTENT - a fictional interview written for the FORGE sample data set.

0:00 Host: Welcome back. Today we are talking about what happens after the breakout, which
is the part nobody films.
0:24 Host: My guest is Dana Ruiz, who runs a concentrated momentum book.
0:41 Dana Ruiz: Thanks for having me. The post-entry phase is where most of the damage gets
done, in my experience.
1:15 Dana Ruiz: The first thing I would say is that the entry is a risk decision, not a
conviction decision. You size for the stop, not for the story.
2:02 Host: How do you define the stop?
2:09 Dana Ruiz: Structurally. Below the last higher low that the breakout was launched from.
If that level breaks, the reason I am in the trade is gone. It has nothing to do with how
much I am willing to lose in percentage terms.
3:30 Dana Ruiz: I also use the 21-period moving average as a trailing reference once the
trade is working. Not as a trigger by itself. Two closes below it is information; one close
below it is noise.
4:47 Host: Do you add to winners?
4:52 Dana Ruiz: Only into a new base. Adding into extension is how you turn a good trade
into an average one. If the stock has not consolidated, there is no new risk point to add
against.
6:10 Dana Ruiz: The hardest discipline is doing nothing while a leader digests a move. Most
of the return in a leader comes from a small number of weeks, and you cannot know in advance
which weeks those are.
7:35 Host: What about market context?
7:41 Dana Ruiz: Environment first, always. I will take the same setup in two different
regimes and get two completely different distributions of outcomes. When breadth is
deteriorating I shrink size before I change my rules.
9:02 Dana Ruiz: One more thing on exits. I separate the invalidation exit from the profit
exit. The invalidation exit is mechanical. The profit exit is discretionary and I am allowed
to be wrong about it.
10:48 Host: If someone takes one thing away from this episode?
10:55 Dana Ruiz: Write down what would make you exit before you enter. If you cannot write
it, you do not have a trade, you have an opinion.
11:30 Host: Thanks Dana. See everyone next week.
"""

WEB_ARTICLE = """Power, Not Silicon, Is Becoming the Binding Constraint on Compute

DEMONSTRATION CONTENT - a fictional article written for the FORGE sample data set.
By Marta Iglesias - Published 2026-06-18 - The Grid Letter

For two years the bottleneck in accelerated computing was packaging capacity. That
constraint has eased. The new one is electricity, and it moves on a different clock.

Utilities in three of the largest data centre markets have published interconnection
queues that now extend past 2029. A queue position is not a guarantee of energised
capacity, and operators have begun treating the two as separate planning problems.

The practical consequence for equipment vendors is that a signed order is no longer a
reliable indicator of a near-term shipment. Several operators have started to disclose
"energised megawatts" alongside contracted megawatts, and the gap between the two is the
number worth tracking.

Behind-the-meter generation is the obvious workaround, and it is being pursued, but the
permitting timelines for on-site gas turbines are measured in quarters and the timelines
for anything nuclear are measured in years.

None of this changes the direction of demand. It changes its shape: less a smooth ramp,
more a series of step functions timed to substation energisation dates.

The metric to watch is not order backlog. It is the ratio of energised to contracted
capacity at the ten largest operators, and whether that ratio is rising or falling.
"""

RULES_MD = """---
title: Swing trading operating rules
author: Demo User
date: 2026-05-02
tags: rules, risk, process
---

# Swing trading operating rules

DEMONSTRATION CONTENT - illustrative rules written for the FORGE sample data set. They are
not investment advice.

## 1. Environment before setup

No setup is evaluated outside its regime. If breadth is deteriorating and the index is below
its 50-day average, position size is halved before any individual chart is opened.

## 2. Risk is defined before entry

Every entry has a written invalidation level derived from structure, not from a percentage.
If the invalidation level cannot be written in one sentence, the trade is not taken.

## 3. Position sizing

Standard position is 5% to 6% of the book. A position is never increased above 10% except
through appreciation.

## 4. Exits

Two distinct exits exist. The invalidation exit is mechanical and non-negotiable. The profit
exit is discretionary and is allowed to be wrong.

A leader is held until it is stopped out structurally, or until it closes more than two
sessions below the 21-period moving average.

## 5. Review cadence

Every open hypothesis is reviewed weekly. Every rule is reviewed quarterly, and a rule that
has not been applied in two quarters is retired rather than kept as decoration.
"""

BREADTH_ROWS = [
    ("date", "pct_above_50dma", "pct_above_200dma", "new_highs", "new_lows", "advance_decline"),
    ("2026-06-01", "62.4", "58.1", "184", "41", "1.84"),
    ("2026-06-08", "59.8", "57.6", "162", "48", "1.42"),
    ("2026-06-15", "55.1", "56.9", "131", "63", "0.96"),
    ("2026-06-22", "48.7", "55.2", "98", "88", "0.71"),
    ("2026-06-29", "44.2", "53.8", "76", "112", "0.58"),
    ("2026-07-06", "46.9", "54.1", "89", "94", "0.83"),
    ("2026-07-13", "52.3", "55.0", "118", "67", "1.21"),
    ("2026-07-20", "57.6", "56.4", "147", "52", "1.55"),
    ("2026-07-27", "61.2", "57.8", "173", "44", "1.71"),
]

POSITIONS = {
    "generated": "DEMONSTRATION CONTENT - fictional portfolio for the FORGE sample data set",
    "as_of": "2026-07-31",
    "book_currency": "USD",
    "positions": [
        {
            "ticker": "HLSX",
            "name": "Helios Semiconductor Inc.",
            "theme": "AI compute",
            "weight_pct": "5.8",
            "entry_date": "2026-05-14",
            "invalidation": "close below 214.00 (last higher low)",
            "status": "open",
        },
        {
            "ticker": "VLTR",
            "name": "Voltaris Grid Systems",
            "theme": "Power infrastructure",
            "weight_pct": "5.1",
            "entry_date": "2026-06-02",
            "invalidation": "two closes below the 21-day average",
            "status": "open",
        },
        {
            "ticker": "CRNX",
            "name": "Coronex Security",
            "theme": "Cybersecurity",
            "weight_pct": "4.4",
            "entry_date": "2026-06-24",
            "invalidation": "close below 88.50",
            "status": "open",
        },
        {
            "ticker": "MDLA",
            "name": "Medalia Biosciences",
            "theme": "Biotech",
            "weight_pct": "0.0",
            "entry_date": "2026-04-08",
            "exit_date": "2026-05-29",
            "invalidation": "close below 61.00",
            "status": "stopped_out",
        },
    ],
}


def write_chart_png(path: Path) -> None:
    """A simple, readable price chart. Real pixels, not a placeholder."""

    from PIL import Image, ImageDraw

    width, height = 900, 480
    background = (14, 16, 20)
    grid = (32, 36, 44)
    up = (94, 197, 138)
    down = (226, 106, 106)
    line = (110, 160, 235)

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    for y in range(60, height - 40, 60):
        draw.line([(50, y), (width - 20, y)], fill=grid)

    closes: list[float] = []
    price = 100.0
    series: list[tuple[float, float, float, float]] = []
    steps = [1.2, 0.6, -0.4, 1.8, 2.4, -1.1, 0.9, 3.2, 1.4, -0.7, -1.9, 0.4, 2.8, 3.6, 1.1,
             -0.5, 2.2, 4.1, 1.7, -1.2, 0.8, 2.9, 3.4, -0.9, 1.6, 2.1, 4.4, 1.9, -1.4, 2.6]
    for step in steps:
        open_price = price
        close_price = price + step
        high = max(open_price, close_price) + 0.9
        low = min(open_price, close_price) - 0.9
        series.append((open_price, high, low, close_price))
        closes.append(close_price)
        price = close_price

    low_bound, high_bound = min(low for _, _, low, _ in series), max(high for _, high, _, _ in series)
    span = high_bound - low_bound or 1.0

    def y_for(value: float) -> float:
        return 60 + (high_bound - value) / span * (height - 130)

    slot = (width - 90) / len(series)
    for index, (open_price, high, low, close_price) in enumerate(series):
        x = 60 + index * slot + slot / 2
        colour = up if close_price >= open_price else down
        draw.line([(x, y_for(high)), (x, y_for(low))], fill=colour)
        draw.rectangle(
            [x - slot * 0.3, y_for(max(open_price, close_price)), x + slot * 0.3, y_for(min(open_price, close_price))],
            fill=colour,
        )

    window = 8
    points = []
    for index in range(len(closes)):
        start = max(0, index - window + 1)
        average = sum(closes[start : index + 1]) / (index - start + 1)
        points.append((60 + index * slot + slot / 2, y_for(average)))
    draw.line(points, fill=line, width=2)

    draw.text((56, 24), "HLSX - daily - demonstration chart (synthetic data)", fill=(196, 202, 214))
    draw.text((56, height - 30), "Generated by FORGE sample generator. Not market data.", fill=(120, 126, 140))
    image.save(path, format="PNG")


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)

    pdf = build_pdf(
        PDF_TEXT,
        title="Helios Semiconductor Inc. (HLSX) - Q3 FY2026 Review",
        author="Demo Research Desk",
        subject="Quarterly review (demonstration content)",
        created=dt.date(2026, 7, 24),
    )
    (SAMPLES / "helios-q3-fy2026-review.pdf").write_bytes(pdf)

    (SAMPLES / "momentum-masterclass-ep41.txt").write_text(TRANSCRIPT_TEXT, encoding="utf-8")
    (SAMPLES / "power-constraint-article.txt").write_text(WEB_ARTICLE, encoding="utf-8")
    (SAMPLES / "swing-trading-rules.md").write_text(RULES_MD, encoding="utf-8")
    (SAMPLES / "market-breadth-2026.csv").write_text(
        "\n".join(",".join(row) for row in BREADTH_ROWS) + "\n", encoding="utf-8"
    )
    (SAMPLES / "positions-snapshot.json").write_text(
        json.dumps(POSITIONS, indent=2) + "\n", encoding="utf-8"
    )
    write_chart_png(SAMPLES / "hlsx-daily-chart.png")

    (SAMPLES / "README.md").write_text(
        "# Sample documents\n\n"
        "Generated by `python scripts/make_samples.py`. Every company, ticker, figure and\n"
        "quotation in these files is **invented for demonstration**. They exist so that the\n"
        "seed data and the test-suite exercise the real import pipeline against real files\n"
        "(a real PDF with a real text layer, a real PNG, a real CSV), never against mocks.\n\n"
        "| File | Imported as | Demonstrates |\n"
        "| --- | --- | --- |\n"
        "| `helios-q3-fy2026-review.pdf` | pdf | multi-page extraction, page locators, PDF metadata |\n"
        "| `momentum-masterclass-ep41.txt` | transcript | timestamp + speaker locators |\n"
        "| `power-constraint-article.txt` | web_article | pasted article text |\n"
        "| `swing-trading-rules.md` | markdown | front matter, section locators |\n"
        "| `market-breadth-2026.csv` | csv | row-group locators, header detection |\n"
        "| `positions-snapshot.json` | json | record locators, JSON pointers |\n"
        "| `hlsx-daily-chart.png` | image | image metadata, optional OCR path |\n",
        encoding="utf-8",
    )
    for path in sorted(SAMPLES.iterdir()):
        print(f"{path.name:38} {path.stat().st_size:>9,} bytes")


if __name__ == "__main__":
    main()
