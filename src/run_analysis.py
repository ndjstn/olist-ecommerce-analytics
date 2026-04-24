"""Olist Brazilian e-commerce: multi-table analytics.

Nine CSVs totalling ~100k orders across ~99k customers. No ML. The project is
pure analytics — multi-table joins, RFM segmentation, cohort retention, and
customer lifetime value calculations. Business intelligence output, not model
output.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _palette import OLIST as P, apply_to_mpl  # noqa: E402

sns.set_style("whitegrid")
apply_to_mpl(P)
plt.rcParams.update({"figure.dpi": 120, "savefig.dpi": 150, "font.size": 11})


def _cmap_native():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("project", [P.bg, P.accent, P.header_bg, P.highlight])


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="Olist dataset directory containing the 9 CSVs")
    ap.add_argument("--figures", required=True)
    ap.add_argument("--outputs", required=True)
    return ap.parse_args()


def main():
    args = parse_args()
    fig_dir, out_dir = Path(args.figures), Path(args.outputs)
    fig_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = Path(args.data)

    customers = pd.read_csv(data / "olist_customers_dataset.csv")
    orders = pd.read_csv(data / "olist_orders_dataset.csv")
    items = pd.read_csv(data / "olist_order_items_dataset.csv")
    payments = pd.read_csv(data / "olist_order_payments_dataset.csv")
    reviews = pd.read_csv(data / "olist_order_reviews_dataset.csv")

    print(f"customers: {len(customers):,}  orders: {len(orders):,}  items: {len(items):,}")

    # Parse dates
    orders["order_purchase_timestamp"] = pd.to_datetime(orders["order_purchase_timestamp"])
    orders["order_approved_at"] = pd.to_datetime(orders["order_approved_at"])
    orders["order_delivered_customer_date"] = pd.to_datetime(orders["order_delivered_customer_date"])

    # Filter to delivered orders
    delivered = orders.loc[orders["order_status"] == "delivered"].copy()
    print(f"delivered: {len(delivered):,}")

    # Item totals per order
    order_totals = items.groupby("order_id").agg(
        items_count=("order_item_id", "max"),
        items_value=("price", "sum"),
        freight=("freight_value", "sum"),
    ).reset_index()
    order_totals["order_total"] = order_totals["items_value"] + order_totals["freight"]

    # Join customers for unique customer id
    orders_full = (delivered
                   .merge(customers, on="customer_id", how="left")
                   .merge(order_totals, on="order_id", how="left"))
    orders_full = orders_full.dropna(subset=["order_total", "order_purchase_timestamp"])
    print(f"orders with totals: {len(orders_full):,}")

    # Revenue by month
    orders_full["purchase_month"] = orders_full["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()
    monthly_rev = orders_full.groupby("purchase_month").agg(revenue=("order_total", "sum"),
                                                              orders=("order_id", "count")).reset_index()

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(monthly_rev["purchase_month"], monthly_rev["revenue"] / 1000, "o-", color=P.header_bg, lw=2.5, ms=5)
    ax.fill_between(monthly_rev["purchase_month"], 0, monthly_rev["revenue"] / 1000, color=P.accent, alpha=0.25)
    ax.set_xlabel("Month")
    ax.set_ylabel("Monthly revenue (thousand BRL)")
    ax.set_title("Olist monthly revenue, 2016-2018")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(fig_dir / "monthly-revenue.png")
    plt.close(fig)

    # RFM segmentation
    snapshot_date = orders_full["order_purchase_timestamp"].max() + pd.Timedelta(days=1)
    rfm = orders_full.groupby("customer_unique_id").agg(
        recency=("order_purchase_timestamp", lambda s: (snapshot_date - s.max()).days),
        frequency=("order_id", "count"),
        monetary=("order_total", "sum"),
    ).reset_index()

    # Score 1-5 per dimension
    rfm["r_score"] = pd.qcut(rfm["recency"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    rfm["f_score"] = pd.qcut(rfm["frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["m_score"] = pd.qcut(rfm["monetary"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["rfm_total"] = rfm["r_score"] + rfm["f_score"] + rfm["m_score"]

    def segment(row):
        r, f, m = row["r_score"], row["f_score"], row["m_score"]
        if r >= 4 and f >= 4:
            return "Champions"
        if r >= 4 and f <= 2:
            return "New / Recent"
        if r >= 3 and m >= 4:
            return "Big spenders"
        if r <= 2 and f >= 4:
            return "At risk"
        if r <= 2 and f <= 2:
            return "Lost"
        return "Others"

    rfm["segment"] = rfm.apply(segment, axis=1)
    seg_counts = rfm["segment"].value_counts()
    seg_rev = rfm.groupby("segment")["monetary"].sum().reindex(seg_counts.index)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    colors = [P.accent, P.highlight, P.header_bg, P.muted, P.cover_subtitle, P.accent_text][:len(seg_counts)]
    axes[0].bar(seg_counts.index, seg_counts.values, color=colors)
    axes[0].set_ylabel("Customers")
    axes[0].set_title("Customer count per RFM segment")
    axes[0].tick_params(axis="x", rotation=30)

    axes[1].bar(seg_rev.index, seg_rev.values / 1000, color=colors)
    axes[1].set_ylabel("Total revenue (thousand BRL)")
    axes[1].set_title("Revenue per RFM segment")
    axes[1].tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(fig_dir / "rfm-segments.png")
    plt.close(fig)

    # Recency vs Monetary scatter coloured by frequency
    fig, ax = plt.subplots(figsize=(9, 5.5))
    sc = ax.scatter(rfm["recency"], rfm["monetary"], c=rfm["frequency"], s=8, cmap=_cmap_native(), alpha=0.65)
    ax.set_yscale("log")
    ax.set_xlabel("Recency (days since last order)")
    ax.set_ylabel("Monetary (BRL, log scale)")
    ax.set_title("Customer landscape: recency vs. monetary, coloured by frequency")
    fig.colorbar(sc, ax=ax, label="Order frequency")
    fig.tight_layout()
    fig.savefig(fig_dir / "rfm-scatter.png")
    plt.close(fig)

    # Cohort retention heatmap
    first_purchase = orders_full.groupby("customer_unique_id")["order_purchase_timestamp"].min().dt.to_period("M")
    orders_full["cohort"] = orders_full["customer_unique_id"].map(first_purchase)
    orders_full["period"] = orders_full["order_purchase_timestamp"].dt.to_period("M")
    orders_full["cohort_index"] = ((orders_full["period"].dt.year - orders_full["cohort"].dt.year) * 12
                                    + (orders_full["period"].dt.month - orders_full["cohort"].dt.month))
    cohort = (orders_full.groupby(["cohort", "cohort_index"])["customer_unique_id"]
              .nunique().unstack(fill_value=0))
    cohort_sizes = cohort[0]
    retention = cohort.divide(cohort_sizes, axis=0)
    # Filter to cohorts with at least 100 customers and the first 12 months
    retention = retention.loc[cohort_sizes >= 100].iloc[:, :12]

    fig, ax = plt.subplots(figsize=(11, 6))
    sns.heatmap(retention * 100, cmap=_cmap_native(), annot=False, cbar_kws={"label": "Retention (%)"},
                yticklabels=[str(p) for p in retention.index], ax=ax)
    ax.set_xlabel("Months since first purchase")
    ax.set_ylabel("Cohort (first purchase month)")
    ax.set_title("Olist cohort retention: most one-time buyers, few repeats")
    fig.tight_layout()
    fig.savefig(fig_dir / "cohort-retention.png")
    plt.close(fig)

    # Review score vs delivery time (common Olist finding)
    reviews_j = (reviews.merge(orders_full[["order_id", "order_purchase_timestamp", "order_delivered_customer_date"]], on="order_id", how="inner"))
    reviews_j["delivery_days"] = (reviews_j["order_delivered_customer_date"] - reviews_j["order_purchase_timestamp"]).dt.days
    reviews_j = reviews_j.loc[reviews_j["delivery_days"].between(0, 45)]
    score_by_delivery = reviews_j.groupby(pd.cut(reviews_j["delivery_days"], bins=[-0.5, 3, 7, 14, 21, 30, 45]))["review_score"].mean()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar([str(c) for c in score_by_delivery.index], score_by_delivery.values, color=P.accent)
    ax.set_xlabel("Delivery time bucket (days)")
    ax.set_ylabel("Mean review score (1-5)")
    ax.set_title("Delivery speed is the dominant driver of review score")
    fig.tight_layout()
    fig.savefig(fig_dir / "review-vs-delivery.png")
    plt.close(fig)

    # Animation: top states by monthly revenue over 2017-2018
    state_month = (orders_full.groupby(["purchase_month", "customer_state"])["order_total"].sum().reset_index())
    top_states = (orders_full.groupby("customer_state")["order_total"].sum().nlargest(8).index.tolist())
    months_sorted = sorted(orders_full["purchase_month"].unique())
    # Restrict to months with enough activity
    active_months = [m for m in months_sorted if len(orders_full.loc[orders_full["purchase_month"] == m]) >= 500]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.set_ylim(0, 700000)
    ax.set_xlabel("State")
    ax.set_ylabel("Monthly revenue (BRL)")
    bars = ax.bar(top_states, [0] * len(top_states), color=[P.accent if s == "SP" else P.header_bg for s in top_states])
    sup = ax.set_title("")
    def animate(i):
        month = active_months[i]
        sub = state_month.loc[state_month["purchase_month"] == month].set_index("customer_state")
        values = [float(sub.loc[s, "order_total"]) if s in sub.index else 0 for s in top_states]
        for bar, v in zip(bars, values):
            bar.set_height(v)
        ax.set_title(f"Monthly revenue by state — {pd.Timestamp(month).strftime('%Y-%m')}")
        return list(bars)
    anim = animation.FuncAnimation(fig, animate, frames=len(active_months), interval=450, blit=False)
    anim.save(str(fig_dir / "state-revenue-animation.gif"), writer="pillow", fps=3)
    plt.close(fig)

    summary = {
        "customers_unique": int(rfm["customer_unique_id"].nunique()),
        "delivered_orders": int(len(orders_full)),
        "total_revenue_brl": float(orders_full["order_total"].sum()),
        "segments": seg_counts.to_dict(),
        "segment_revenue": {k: float(v) for k, v in seg_rev.items()},
    }
    (out_dir / "analysis_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    rfm.to_csv(out_dir / "rfm-segmentation.csv", index=False)

    md = ["# Olist analytics summary", ""]
    md.append(f"Unique customers: {rfm['customer_unique_id'].nunique():,}. Delivered orders: {len(orders_full):,}.")
    md.append(f"Total revenue: R$ {orders_full['order_total'].sum():,.0f}.")
    md.append("")
    md.append("## RFM segments")
    md.append("")
    md.append("| Segment | Customers | Revenue (BRL) |")
    md.append("|---|---:|---:|")
    for seg, n in seg_counts.items():
        md.append(f"| {seg} | {n:,} | {seg_rev[seg]:,.0f} |")
    (out_dir / "analysis_summary.md").write_text("\n".join(md))
    print("Done")


if __name__ == "__main__":
    main()
