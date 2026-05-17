"""
FFC — Step 2 (Local)
1:1 local execution version of Step_2_2026_Offtake_Primary_Data_Processing_LOCAL.py

Inputs (local)
--------------
- output/offtake_combined_local_march_2026.csv   (from Step 1 local)
- input/2026_customer_abbott_code_mapping.xlsx
- input/2026_Consolidated_Price_Master.xlsx
- input/2025_Conversion_Master.xlsx
- input/2026_SKU_Brand_Division_mapping.xlsx
- input/2026_PinCodes_with_States_and_Districts.csv
- input/2026_EAP_Primary_Sales.csv

Outputs
-------
- output/offtake_step2_final.csv
- output/qc_step2.xlsx

Bug-fixes vs original notebook
-------------------------------
1. KEY NORMALIZATION MOVED BEFORE ALL MERGES
   Original: clean_key_col() was called AFTER the first merge (Customer SKU → Abbott SKU),
   so product_code / name-of-customer were un-normalized at merge time → almost zero
   matches for NETMEDS & WELLNESS → SKU No was NaN → every downstream column
   (pts_price, Brand Name, Division Name, State, District, channel_sales, GMV) came out
   blank for those two channels.
   Fix: apply clean_key_col() to all master files AND to offtake BEFORE any merge.

2. STALE MERGE COLUMNS DROPPED BEFORE RE-MERGE
   Original: cell 7 ran the first merge (with dirty keys), then cell 8 cleaned keys but
   the already-merged stale columns (Customer, Customer Item Code, SKU No) remained in
   offtake, polluting the shape and making the price join match on wrong keys.
   Fix: drop those columns from offtake before the re-merge.

3. primary.reindex BUG
   Original: reindexing primary to offtake.columns (which still contained raw merge
   artifact columns) caused misaligned concatenation and fill_value=0 replacing real data.
   Fix: reindex only against the explicit set of columns needed.
"""

import os
from pathlib import Path
import logging
import pandas as pd
import numpy as np

# =====================================================
# LOGGING
# =====================================================

os.makedirs("logs", exist_ok=True)
os.makedirs("output", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/step2_run.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# =====================================================
# INPUT FILES
# =====================================================

STEP1_FILE      = Path("output/offtake_combined_local_march_2026.csv")
PRODUCT_MAP_FILE = Path("input/2026_customer_abbott_code_mapping.xlsx")
PRICE_FILE      = Path("input/2026_Consolidated_Price_Master.xlsx")
CONVERSION_FILE = Path("input/2025_Conversion_Master.xlsx")
BRAND_DIV_FILE  = Path("input/2026_SKU_Brand_Division_mapping.xlsx")
PINCODE_FILE    = Path("input/2026_PinCodes_with_States_and_Districts.csv")
PRIMARY_FILE    = Path("input/2026_EAP_Primary_Sales.csv")

for p in [STEP1_FILE, PRODUCT_MAP_FILE, PRICE_FILE, CONVERSION_FILE,
          BRAND_DIV_FILE, PINCODE_FILE, PRIMARY_FILE]:
    if not p.exists():
        raise FileNotFoundError(f"Missing required input: {p}")

# =====================================================
# LOAD STEP-1 OFFTAKE
# =====================================================

logger.info("Loading Step-1 Offtake")

offtake = pd.read_csv(
    STEP1_FILE,
    parse_dates=["month"],
    dtype={"product_code": "string", "pincode": "string"},
    low_memory=False,
)

offtake["name of customer"] = offtake["name of customer"].str.upper()

# CRITICAL: create ECB_Primary_Sales column EARLY
offtake["ECB_Primary_Sales"] = 0.0

logger.info(f"Step-1 loaded: {offtake.shape}")

# =====================================================
# LOAD MASTER FILES
# =====================================================

logger.info("Loading mapping masters")

product_map       = pd.read_excel(PRODUCT_MAP_FILE)
price_master      = pd.read_excel(PRICE_FILE)
conversion_master = pd.read_excel(CONVERSION_FILE)
brand_div         = pd.read_excel(BRAND_DIV_FILE)

pincode_map = pd.read_csv(
    PINCODE_FILE,
    encoding="latin1",
    dtype={"Pin.Code": "string"},
    low_memory=False,
)

logger.info("Masters loaded")
logger.info({
    "product_map":        product_map.shape,
    "price_master":       price_master.shape,
    "conversion_master":  conversion_master.shape,
    "brand_div":          brand_div.shape,
    "pincode_map":        pincode_map.shape,
})

# =====================================================
# LOAD & NORMALIZE PRIMARY SALES
# =====================================================

logger.info("Loading ECB Primary Sales")

primary = pd.read_csv(PRIMARY_FILE, low_memory=False)
primary["month"] = pd.to_datetime(primary["month"], dayfirst=True, errors="coerce")

# Detect primary sales column
primary_col = None
for col in primary.columns:
    norm = col.strip().replace(" ", "_").upper()
    if norm in ["ECB_PRIMARY_SALES", "ECBPRIMARYSALES", "PRIMARY_SALES"]:
        primary_col = col
        break

if primary_col is None:
    raise ValueError("ECB Primary Sales column not found in PRIMARY_FILE")

primary["ECB_Primary_Sales"] = pd.to_numeric(primary[primary_col], errors="coerce").fillna(0)

logger.info(f"Primary sales loaded: {primary.shape}")

# =====================================================
# BUG-FIX 1 — KEY NORMALIZATION *BEFORE* ALL MERGES
# =====================================================
#
# Original notebook ran clean_key_col() AFTER the first merge (cell 8 came after cell 7).
# That meant all three customer channels still had raw / mixed-case / trailing-.0 keys
# at merge time, so product_code lookups found almost zero Abbott SKU matches for
# NETMEDS and WELLNESS, leaving SKU No blank and cascading blanks into every column.

def clean_key_col(s: pd.Series) -> pd.Series:
    return (
        s.astype("string")
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )

# --- offtake keys ---
offtake["name of customer"] = clean_key_col(offtake["name of customer"])
offtake["product_code"]     = clean_key_col(offtake["product_code"])
offtake["month"]            = (
    pd.to_datetime(offtake["month"], errors="coerce")
    .dt.to_period("M")
    .dt.to_timestamp()
)

# --- product_map keys ---
product_map["Customer"]           = clean_key_col(product_map["Customer"])
product_map["Customer Item Code"] = clean_key_col(product_map["Customer Item Code"])
product_map["SKU No"]             = clean_key_col(product_map["SKU No"])

# --- price_master keys ---
price_master["sap_code"] = clean_key_col(price_master["sap_code"])
price_master["month"]    = (
    pd.to_datetime(price_master["month"], errors="coerce")
    .dt.to_period("M")
    .dt.to_timestamp()
)

# --- conversion_master keys ---
conversion_master["Customer"]             = clean_key_col(conversion_master["Customer"])
conversion_master["Channel Product Code"] = clean_key_col(conversion_master["Channel Product Code"])

# --- brand_div keys ---
brand_div["SKU Code"] = clean_key_col(brand_div["SKU Code"])

logger.info("Normalization completed")

# =====================================================
# 1. CUSTOMER SKU → ABBOTT SKU  (merge AFTER normalization)
# =====================================================

logger.info("Mapping Customer SKU to Abbott SKU")

offtake = offtake.merge(
    product_map,
    how="left",
    left_on=["product_code", "name of customer"],
    right_on=["Customer Item Code", "Customer"],
)

logger.info(f"After SKU mapping: {offtake.shape}")
logger.info(
    f"SKU No mapped: {offtake['SKU No'].notna().sum()} | "
    f"blank: {offtake['SKU No'].isna().sum()}"
)

# Drop merge-artifact columns that would collide with the conversion merge below
offtake.drop(
    columns=[c for c in ["Customer", "Customer Item Code"] if c in offtake.columns],
    inplace=True,
    errors="ignore",
)

# =====================================================
# 2. PTS PRICE
# =====================================================

logger.info("Applying PTS price")

offtake = offtake.merge(
    price_master,
    how="left",
    left_on=["SKU No", "month"],
    right_on=["sap_code", "month"],
)

logger.info(f"After PTS price merge: {offtake.shape}")

# =====================================================
# 3. CONVERSION FACTOR
# =====================================================

# Drop any leftover conversion columns (idempotent)
offtake.drop(
    columns=[c for c in ["Customer", "Channel Product Code", "Conversion Factor"]
             if c in offtake.columns],
    inplace=True,
    errors="ignore",
)

logger.info("Applying conversion factor")

offtake = offtake.merge(
    conversion_master,
    how="left",
    left_on=["name of customer", "product_code"],
    right_on=["Customer", "Channel Product Code"],
)

offtake["units_sold"] = pd.to_numeric(offtake["units_sold"], errors="coerce")
cond = offtake["Conversion Factor"].notna()

offtake["final_converted_quantity"] = np.where(
    cond,
    offtake["units_sold"] / offtake["Conversion Factor"],
    offtake["units_sold"],
)

# Step-1 revenue is already channel sales (local pipeline)
offtake["channel_sales"] = pd.to_numeric(offtake["revenue"], errors="coerce").fillna(0)

# Keep revenue as GMV for final output
offtake.rename(columns={"revenue": "GMV"}, inplace=True)

logger.info(f"After conversion factor: {offtake.shape}")

# =====================================================
# 4. APPEND ECB PRIMARY SALES
# =====================================================
#
# BUG-FIX 3 — reindex primary ONLY against the explicit final column set,
# not against offtake.columns (which contained raw merge artifact columns).

logger.info("Appending ECB Primary Sales")

# Columns that must exist in both frames before concat
concat_cols = [
    "month", "name of customer", "pincode", "product_code", "sku_name",
    "units_sold", "GMV", "channel_sales", "ECB_Primary_Sales",
    "SKU No", "final_converted_quantity",
]

primary_aligned = primary.reindex(columns=concat_cols, fill_value=0)
offtake_aligned = offtake.reindex(columns=concat_cols)

offtake = pd.concat([offtake_aligned, primary_aligned], axis=0, ignore_index=True)

logger.info(f"After primary append: {offtake.shape}")

# =====================================================
# 5. BRAND / DIVISION
# =====================================================

logger.info("Applying Brand & Division")

offtake = offtake.merge(
    brand_div,
    how="left",
    left_on="SKU No",
    right_on="SKU Code",
)

logger.info(f"After Brand/Division merge: {offtake.shape}")

# =====================================================
# 6. PINCODE → STATE / DISTRICT
# =====================================================

logger.info("Applying Pincode to State/District")

offtake = offtake.merge(
    pincode_map,
    how="left",
    left_on="pincode",
    right_on="Pin.Code",
)

logger.info(f"After pincode merge: {offtake.shape}")

# =====================================================
# 7. BUSINESS OVERRIDES
# =====================================================

override_customers = [
    "ASTER",
    "ASWAS",
    "NOBLE",
    "DAWADOST",
    "SASTA AROGYA",
    "GUARDIAN",
    "THULASI",
    "ZENO HEALTH",
    "EASYMEDICO",
]

mask = offtake["name of customer"].isin(override_customers)
offtake.loc[mask, "channel_sales"] = offtake.loc[mask, "ECB_Primary_Sales"]

logger.info("Overrides applied")

# =====================================================
# 8. FINAL OUTPUT COLUMNS
# =====================================================

final_cols = [
    "month",
    "name of customer",
    "pincode",
    "State",
    "District",
    "SKU No",
    "Brand Name",
    "Division Name",
    "units_sold",
    "channel_sales",
    "ECB_Primary_Sales",
    "GMV",
]

offtake_final = offtake[final_cols].copy()

# Add Affiliate column
offtake_final["Affiliate"] = "AIL"

# Reorder for clean hierarchy
offtake_final = offtake_final[
    [
        "month",
        "name of customer",
        "Affiliate",
        "pincode",
        "State",
        "District",
        "SKU No",
        "Brand Name",
        "Division Name",
        "units_sold",
        "channel_sales",
        "ECB_Primary_Sales",
        "GMV",
    ]
]

# Fill numeric nulls
for c in ["channel_sales", "ECB_Primary_Sales", "GMV"]:
    offtake_final[c] = offtake_final[c].fillna(0)

logger.info(f"Final shape: {offtake_final.shape}")

# =====================================================
# QC
# =====================================================

qc = (
    offtake_final.groupby(["name of customer", "month"])
    .agg(
        Rows=("SKU No", "count"),
        Channel_Sales=("channel_sales", "sum"),
        ECB_Primary=("ECB_Primary_Sales", "sum"),
        GMV=("GMV", "sum"),
    )
    .reset_index()
)

# Customer name standardisation (post-QC)
offtake_final["name of customer"] = (
    offtake_final["name of customer"]
    .str.upper()
    .str.strip()
    .replace({
        "APOLLO RETAIL": "APOLLO",
        "KEIMED": "KEIMEDGT",
    })
)

# =====================================================
# WRITE OUTPUT
# =====================================================

offtake_final.to_csv("output/offtake_step2_final.csv", index=False)

with pd.ExcelWriter("output/qc_step2.xlsx") as writer:
    qc.to_excel(writer, sheet_name="Account_Month_QC", index=False)

logger.info("Step-2 local notebook completed successfully")
print({
    "final_csv": "output/offtake_step2_final.csv",
    "qc_xlsx":   "output/qc_step2.xlsx",
})
