#!/usr/bin/env python
# coding: utf-8

# ## FFC — Step 1 (Local)
# 
# This notebook is a 1:1 local execution version of `FFC/FFC Test/Step_1_Offtake_LOCAL.py`.
# 
# ### Output
# - `output/offtake_combined_local_march_2026.csv`
# 
# ### Inputs (local)
# - `input/Abbott_Sales_Mar'26_Netmeds.xlsx`
# - `input/Abbott Mar-26_wellness.xlsx`
# - `input/Abbott CFA_Truemeds_march'26_edited.xlsx`
# 

# In[6]:


import os
from pathlib import Path
import logging
import pandas as pd
import numpy as np
import openpyxl
# =====================================================
# LOGGING
# =====================================================

os.makedirs("logs", exist_ok=True)
os.makedirs("output", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/offtake_run.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

INPUT_PATH = Path("input")

# ----------------------------
# Input files (local)
# ----------------------------
NETMEDS_XLSX = INPUT_PATH / "Abbott_Sales_Mar'26_Netmeds.xlsx"
WELLNESS_XLSX = INPUT_PATH / "Abbott Mar-26_wellness.xlsx"
TRUEMEDS_XLSX = INPUT_PATH / "Abbott CFA_Truemeds_march'26_edited.xlsx"

for p in [NETMEDS_XLSX, WELLNESS_XLSX, TRUEMEDS_XLSX]:
    if not p.exists():
        raise FileNotFoundError(f"Missing required input file: {p}")


# In[7]:


# NETMEDS

logger.info("Processing NETMEDS")

netmeds_file = NETMEDS_XLSX

cols_to_keep_netmeds = [
    "Order Date",
    "Shipping to Pincode",
    "Product Code",
    "Purchase Qty",
    "Amount",
    "Order Status",
    "Product Name"
]

data_netmeds = pd.read_excel(netmeds_file, engine="openpyxl")
data_netmeds = data_netmeds[cols_to_keep_netmeds]
data_netmeds = data_netmeds[data_netmeds["Order Status"] == "Delivered"]

data_netmeds["Order Date"] = (
    pd.to_datetime(data_netmeds["Order Date"], dayfirst=True)
    .dt.to_period("M")
    .dt.to_timestamp()
)

data_netmeds.rename(
    columns={
        "Order Date": "month",
        "Shipping to Pincode": "pincode",
        "Product Code": "product_code",
        "Purchase Qty": "units_sold",
        "Amount": "revenue",
        "Product Name": "sku_name",
    },
    inplace=True,
)

# city intentionally set to 0
data_netmeds["city"] = 0
data_netmeds["name of customer"] = "NETMEDS"

data_netmeds["revenue"] = pd.to_numeric(data_netmeds["revenue"], errors="coerce")
data_netmeds["units_sold"] = pd.to_numeric(data_netmeds["units_sold"], errors="coerce")

logger.info("NETMEDS completed")


# In[8]:


# WELLNESS

logger.info("Processing WELLNESS")

wellness_file = WELLNESS_XLSX

cols_to_keep_wellness = [
    "Pincode",
    "City",
    "Item Code",
    "Sales Qty",
    "Sales Value",
    "Item name",
]

data_wellness = pd.read_excel(wellness_file, engine="openpyxl")
data_wellness = data_wellness[cols_to_keep_wellness]

data_wellness["month"] = pd.to_datetime("2026-03-01")

data_wellness.rename(
    columns={
        "Pincode": "pincode",
        "City": "city",
        "Item Code": "product_code",
        "Sales Qty": "units_sold",
        "Sales Value": "revenue",
        "Item name": "sku_name",
    },
    inplace=True,
)

data_wellness["name of customer"] = "WELLNESS"
data_wellness["revenue"] = pd.to_numeric(data_wellness["revenue"], errors="coerce")
data_wellness["units_sold"] = pd.to_numeric(data_wellness["units_sold"], errors="coerce")

logger.info("WELLNESS completed")


# In[9]:


# TRUEMEDS 

logger.info("Processing TRUEMEDS")

truemeds_file = TRUEMEDS_XLSX

cols_to_keep_truemeds = [
    "Date",
    "Billing Zip",
    "Location",
    "Item Code",
    "Quantity Sold",
    "Item Amount",
]

data_truemeds = pd.read_excel(truemeds_file, engine="openpyxl")
data_truemeds = data_truemeds[cols_to_keep_truemeds]

data_truemeds["Date"] = (
    pd.to_datetime(data_truemeds["Date"])
    .dt.to_period("M")
    .dt.to_timestamp()
)

data_truemeds.rename(
    columns={
        "Date": "month",
        "Billing Zip": "pincode",
        "Location": "city",
        "Item Code": "product_code",
        "Quantity Sold": "units_sold",
        "Item Amount": "revenue",
    },
    inplace=True,
)

data_truemeds["sku_name"] = ""
data_truemeds["name of customer"] = "TRUEMEDS"
data_truemeds["revenue"] = pd.to_numeric(data_truemeds["revenue"], errors="coerce")
data_truemeds["units_sold"] = pd.to_numeric(data_truemeds["units_sold"], errors="coerce")

logger.info("TRUEMEDS completed")


# In[10]:


# COMBINE ALL CHANNELS

logger.info("Combining all datasets")

offtake_combined_all_channels = pd.concat(
    [data_netmeds, data_wellness, data_truemeds],
    axis=0,
    ignore_index=True,
)

# Canonical Step-1 schema
final_cols = [
    "month",
    "name of customer",
    "pincode",
    "city",
    "product_code",
    "sku_name",
    "units_sold",
    "revenue",
]

offtake_combined_all_channels = offtake_combined_all_channels[final_cols]
offtake_combined_all_channels["pincode"] = offtake_combined_all_channels["pincode"].astype(str)


# In[11]:


# QC CHECKS 

logger.info("Running Step-1 QC checks")

dup_count = offtake_combined_all_channels.duplicated().sum()
logger.info(f"Duplicate rows detected: {dup_count}")

qc_summary = (
    offtake_combined_all_channels
    .groupby("name of customer", dropna=False)
    .agg(
        rows=("product_code", "count"),
        total_units=("units_sold", "sum"),
        total_revenue=("revenue", "sum"),
    )
    .reset_index()
)

logger.info("QC SUMMARY (Step-1)")
logger.info("\n" + qc_summary.to_string(index=False))

qc_summary


# In[12]:


# OUTPUT 

output_file = os.path.join("output", "offtake_combined_local_march_2026.csv")
offtake_combined_all_channels.to_csv(output_file, index=False)

logger.info("Step-1 local notebook completed successfully")
output_file


# In[ ]:




