# 93,000 Customers and No Repeats: Olist Brazilian E-Commerce Analytics

Multi-table analytics on the Olist Brazilian e-commerce dataset: 100,000 orders, 93,000 customers, 2016-2018. No machine learning. RFM segmentation, cohort retention, and delivery-time impact on review scores.

## Key findings

| Metric | Value |
| --- | ---: |
| Delivered orders | 96,478 |
| Unique customers | 93,358 |
| Total revenue | R$ 15.4M |
| Single-purchase customers | 97% |
| Month-1 retention | ~3% |
| SP share of revenue | ~45% |

Cohort retention is near-zero past month 0. Olist's growth comes from new customers, not repeats — the product mix is one-time-purchase items (appliances, electronics, home goods), which makes customer lifetime value collapse to first-order value. Delivery time correlates strongly with review score: orders in 0-3 days average 4.5 stars; orders past 30 days average below 3.0.

## What is in this repo

`src/run_analysis.py` does the multi-table joins, RFM scoring, cohort construction, and figure generation. `notebooks/` has the narrative walk-through. `figures/` has the monthly revenue chart, RFM segment bars, recency-monetary scatter, cohort retention heatmap, delivery-time-to-review chart, and a state-revenue animation. `outputs/` has the RFM segmentation CSV and summary JSON.

`REPORT.md` is the long-form analysis.

## How to reproduce

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/run_analysis.py --data data/ --figures figures --outputs outputs
```

Download the 9 Olist CSVs from <https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce> and place them in `data/`.

## Further reading

<https://ndjstn.github.io/posts/olist-ecommerce-retention/>.

## License

MIT.
