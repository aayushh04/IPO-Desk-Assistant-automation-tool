"""Subscription tracker logic: category-wise multiples by day, charts and neutral update text.

Subscription multiple = shares bid for / shares offered in that category.
Example: bids for 3 crore shares against 1 crore offered = 3.0x ("subscribed 3 times").
The total figure is all bids / all shares offered, NOT the average of category multiples.

Categories:
- QIB  (Qualified Institutional Buyers): mutual funds, insurers, banks, FPIs. Watched closely
        because they are professional investors who study the issue in depth.
- NII  (Non-Institutional Investors / HNIs): bids above Rs 2 lakh. Split into
        sNII (Rs 2-10 lakh, 1/3 of the NII portion) and bNII (above Rs 10 lakh, 2/3).
- Retail (Retail Individual Investors): bids up to Rs 2 lakh.
- Employee: a reserved portion for the company's employees, if any.
"""
from __future__ import annotations

import io
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
import plotly.graph_objects as go

from ipodesk.config import disclaimer

CATEGORY_LABELS: dict[str, str] = {
    "qib": "QIB", "nii": "NII", "nii_big": "bNII (> Rs 10 lakh)", "nii_small": "sNII (Rs 2-10 lakh)",
    "retail": "Retail", "employee": "Employee", "total": "Total",
}
SHORT_LABELS: dict[str, str] = {"qib": "QIB", "nii": "NII", "nii_big": "bNII", "nii_small": "sNII",
                                "retail": "Retail", "employee": "Employee", "total": "Total"}
_ALIASES: dict[str, str] = {
    "qib": "qib", "qibs": "qib", "qualified institutional buyers": "qib",
    "nii": "nii", "hni": "nii", "non institutional": "nii", "non-institutional": "nii",
    "nii big": "nii_big", "big nii": "nii_big", "bnii": "nii_big", "nii_big": "nii_big", "nii (>10l)": "nii_big",
    "nii small": "nii_small", "small nii": "nii_small", "snii": "nii_small", "nii_small": "nii_small",
    "nii (2-10l)": "nii_small", "retail": "retail", "rii": "retail", "retail individual investors": "retail",
    "employee": "employee", "employees": "employee", "emp": "employee", "total": "total", "overall": "total",
}
CATEGORY_ORDER: list[str] = ["qib", "nii", "nii_big", "nii_small", "retail", "employee", "total"]
# Pencil palette (red is reserved for queries and flags, so no series uses it).
COLORS: dict[str, str] = {"qib": "#1E4E8C", "nii": "#7A5C2E", "nii_big": "#7A5C2E", "nii_small": "#B08A3E",
                          "retail": "#2E7D32", "employee": "#8E5A9C", "total": "#2B2F2A"}


def fmt_x(value: float) -> str:
    """Format a multiple to 1 decimal, rounding half up (0.95 -> '1.0x', not '0.9x')."""
    return f"{Decimal(str(value)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}x"


def subscription_multiple(shares_bid: float, shares_offered: float) -> float:
    """Shares bid / shares offered (0 if nothing was offered)."""
    return shares_bid / shares_offered if shares_offered else 0.0


def normalize_category(name: str) -> str | None:
    """Map spellings like 'QIBs', 'bNII', 'RII', 'Overall' to our category keys."""
    return _ALIASES.get(str(name).strip().lower().replace("_", " ").replace("  ", " ")) or \
        _ALIASES.get(str(name).strip().lower())


def load_subscription(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Validate an uploaded/entered table and compute multiples.

    Accepts either (shares_offered, shares_bid) columns, or a ready subscription_x column.
    Adds a 'total' row per day when share counts are available and no total was given.
    """
    errors: list[str] = []
    need = {"company", "day", "category"}
    if not need <= set(df.columns):
        return pd.DataFrame(), [f"Missing columns: {', '.join(sorted(need - set(df.columns)))}"]
    has_shares = {"shares_offered", "shares_bid"} <= set(df.columns)
    if not has_shares and "subscription_x" not in df.columns:
        return pd.DataFrame(), ["Need either shares_offered + shares_bid columns, or a subscription_x column."]
    out = df.copy()
    out["category"] = out["category"].map(normalize_category)
    bad = df.loc[out["category"].isna(), "category"].unique()
    if len(bad):
        errors.append(f"Unknown categories ignored: {', '.join(map(str, bad))}")
    out = out.dropna(subset=["category"])
    out["day"] = pd.to_numeric(out["day"], errors="coerce").astype("Int64")
    out = out.dropna(subset=["day"])
    if has_shares:
        out["shares_offered"] = pd.to_numeric(out["shares_offered"], errors="coerce")
        out["shares_bid"] = pd.to_numeric(out["shares_bid"], errors="coerce")
        out["subscription_x"] = [round(subscription_multiple(b, o), 2)
                                 for b, o in zip(out["shares_bid"], out["shares_offered"])]
        totals = []
        for (company, day), grp in out.groupby(["company", "day"]):
            if "total" not in set(grp["category"]):
                parts = grp[grp["category"].isin(["qib", "nii", "nii_big", "nii_small", "retail", "employee"])]
                # Don't double count if both 'nii' and its split were given.
                if "nii" in set(parts["category"]) and {"nii_big", "nii_small"} & set(parts["category"]):
                    parts = parts[parts["category"] != "nii"]
                off, bid = parts["shares_offered"].sum(), parts["shares_bid"].sum()
                totals.append({"company": company, "day": day, "category": "total", "shares_offered": off,
                               "shares_bid": bid, "subscription_x": round(subscription_multiple(bid, off), 2)})
        if totals:
            out = pd.concat([out, pd.DataFrame(totals)], ignore_index=True)
    else:
        out["subscription_x"] = pd.to_numeric(out["subscription_x"], errors="coerce")
    out["order"] = out["category"].map(CATEGORY_ORDER.index)
    out = out.sort_values(["company", "day", "order"]).drop(columns="order").reset_index(drop=True)
    return out, errors


def _nii_combined(day_rows: pd.DataFrame) -> float | None:
    """NII multiple for a day: the 'nii' row if given, else (bNII + sNII bids) / (bNII + sNII offered)."""
    cats = day_rows.set_index("category")
    if "nii" in cats.index:
        return float(cats.loc["nii", "subscription_x"])
    split = day_rows[day_rows["category"].isin(["nii_big", "nii_small"])]
    if split.empty or "shares_offered" not in split or split["shares_offered"].isna().any():
        return None
    return round(subscription_multiple(split["shares_bid"].sum(), split["shares_offered"].sum()), 2)


def latest_day(df: pd.DataFrame, company: str) -> int:
    """The most recent day number for a company."""
    return int(df.loc[df["company"] == company, "day"].max())


def update_text(df: pd.DataFrame, company: str, day: int | None = None) -> str:
    """Neutral one-line update, e.g. 'Day 2 close: QIB 3.4x, NII 5.1x, Retail 2.2x, Total 3.1x'."""
    day = day or latest_day(df, company)
    rows = df[(df["company"] == company) & (df["day"] == day)]
    x = dict(zip(rows["category"], rows["subscription_x"]))
    parts = []
    if "qib" in x:
        parts.append(f"QIB {fmt_x(x['qib'])}")
    nii = _nii_combined(rows)
    if nii is not None:
        parts.append(f"NII {fmt_x(nii)}")
    for cat in ("retail", "employee", "total"):
        if cat in x:
            parts.append(f"{SHORT_LABELS[cat]} {fmt_x(x[cat])}")
    return f"Day {day} close: " + ", ".join(parts)


def client_update(df: pd.DataFrame, company: str, day: int | None = None) -> str:
    """The update text with the company name and disclaimer, ready to copy."""
    return f"{company}: IPO subscription status\n{update_text(df, company, day)}\n(Exchange data, cumulative)\n\n{disclaimer()}"


def latest_table(df: pd.DataFrame, company: str, day: int | None = None) -> pd.DataFrame:
    """Latest numbers by category (with change vs the previous day)."""
    day = day or latest_day(df, company)
    sub = df[df["company"] == company]
    cur = sub[sub["day"] == day].set_index("category")
    prev = sub[sub["day"] == day - 1].set_index("category")
    out = pd.DataFrame({"Category": [CATEGORY_LABELS[c] for c in cur.index]})
    if "shares_offered" in cur:
        out["Shares offered"] = cur["shares_offered"].values
        out["Shares bid"] = cur["shares_bid"].values
    out["Subscription (x)"] = cur["subscription_x"].values
    out["Change vs previous day"] = [round(cur.loc[c, "subscription_x"] - prev.loc[c, "subscription_x"], 2)
                                     if c in prev.index else None for c in cur.index]
    return out


def _series(df: pd.DataFrame, company: str) -> dict[str, pd.DataFrame]:
    """Per-category rows for one company, in display order."""
    sub = df[df["company"] == company]
    return {c: sub[sub["category"] == c].sort_values("day") for c in CATEGORY_ORDER if c in set(sub["category"])}


def chart(df: pd.DataFrame, company: str) -> go.Figure:
    """Interactive line chart: subscription multiple by category across issue days."""
    fig = go.Figure()
    for cat, rows in _series(df, company).items():
        fig.add_trace(go.Scatter(
            x=[f"Day {d}" for d in rows["day"]], y=rows["subscription_x"], mode="lines+markers+text",
            name=CATEGORY_LABELS[cat], line={"color": COLORS[cat], "width": 3.5 if cat == "total" else 2,
                                            "dash": "dot" if cat == "total" else "solid"},
            # Label only the latest point, so labels don't pile up on early days.
            text=[""] * (len(rows) - 1) + [fmt_x(rows["subscription_x"].iloc[-1])], textposition="middle right",
            hovertemplate="%{x}: %{y:.2f}x<extra>" + CATEGORY_LABELS[cat] + "</extra>"))
    fig.update_layout(title={"text": f"{company}: subscription by category", "font": {"size": 15}},
                      yaxis_title="Times subscribed (x)", legend={"orientation": "h", "y": -0.18},
                      margin={"l": 10, "r": 40, "t": 50, "b": 10}, height=420,
                      font={"family": "Public Sans, sans-serif", "color": "#2B2F2A"},
                      paper_bgcolor="#FBFCFA", plot_bgcolor="#FBFCFA")
    fig.update_xaxes(showgrid=False, linecolor="#2B2F2A")
    fig.update_yaxes(gridcolor="#E1E7DF", zeroline=False)
    return fig


def chart_png(df: pd.DataFrame, company: str) -> bytes:
    """The same chart as a PNG image (matplotlib, so no browser is needed on the server)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150, facecolor="#FBFCFA")
    ax.set_facecolor("#FBFCFA")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for cat, rows in _series(df, company).items():
        days = [f"Day {d}" for d in rows["day"]]
        ax.plot(days, rows["subscription_x"], marker="o", label=CATEGORY_LABELS[cat], color=COLORS[cat],
                linewidth=3 if cat == "total" else 1.8, linestyle=":" if cat == "total" else "-")
        ax.annotate(fmt_x(rows['subscription_x'].iloc[-1]), (days[-1], rows["subscription_x"].iloc[-1]),
                    textcoords="offset points", xytext=(6, 0), fontsize=8, color=COLORS[cat])
    ax.set_title(f"{company}: subscription by category", fontsize=11)
    ax.set_ylabel("Times subscribed (x)")
    ax.grid(axis="y", color="#E1E7DF")
    ax.legend(fontsize=8, frameon=False)
    fig.text(0.01, 0.01, "Source: exchange data (cumulative). For information only. Not a recommendation.", fontsize=7, alpha=0.7)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
