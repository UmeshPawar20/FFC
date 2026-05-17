#!/usr/bin/env python
# coding: utf-8

# ## FFC — Step 5 (Local): Contribution / Ratio
# 
# This notebook is a **business-logic-faithful** local execution adaptation of the core contribution logic found in `FFC/Step 5 _ Keimed Ratio Creation _Custom Months.ipynb`.
# 
# **No business rules are changed**. The optimization is around file paths, validations, and efficient reads.
# 
# ### Inputs (local)
# - `output/offtake_step2_final.csv` (Step 2 output)
# - `output/DB_Level_Apollo_Keimed_2026_local.csv` (Step 3 output)
# - `FFC/20260402_Mar Pincode_Universe_AIL Mapped.csv` (already in repo)
# 
# ### Outputs
# - `output/FF_Contribution_All_Channels_local.csv`
# 

# In[8]:


from pathlib import Path

print("Working directory:", Path().resolve())


# In[9]:


import os
from pathlib import Path
import pandas as pd
import numpy as np

print("library got it")
os.makedirs("output", exist_ok=True)

OFFTAKE_FILE = Path("C:/Users/pawarux2/OneDrive - Abbott/Documents/FFC/FFC Test/output/offtake_step2_final.csv")
DB_LEVEL_FILE = Path("C:/Users/pawarux2/OneDrive - Abbott/Documents/FFC/FFC Test/output/DB_Level_Apollo_Keimed_2026_local.csv")
PIN_TERR_FILE = Path("C:/Users/pawarux2/OneDrive - Abbott/Documents/FFC/FFC Test/input/20260402_Mar Pincode_Universe_AIL Mapped.csv")

OUT_CONTRI = Path("C:/Users/pawarux2/OneDrive - Abbott/Documents/FFC/FFC Test/output/FF_Contribution_All_Channels_local.csv")

# mirrors original Step-5 notebook
custom_months = 3

for p in [OFFTAKE_FILE, DB_LEVEL_FILE, PIN_TERR_FILE]:
    if not p.exists():
        raise FileNotFoundError(f"Missing required input: {p}")


# In[10]:


# Load (optimized columns only)
offtake = pd.read_csv(
    OFFTAKE_FILE,
    usecols=["month", "name of customer", "Division Name", "Affiliate", "pincode", "channel_sales"],
    dtype={"pincode": "string", "Division Name": "string", "Affiliate": "string", "name of customer": "string"},
    parse_dates=["month"],
    low_memory=False,
)

db_level = pd.read_csv(
    DB_LEVEL_FILE,
    usecols=["month", "name of customer", "Division Name", "Affiliate", "pincode", "channel_sales"],
    dtype={"pincode": "string", "Division Name": "string", "Affiliate": "string", "name of customer": "string"},
    parse_dates=["month"],
    low_memory=False,
)

dvl_from_ff = pd.read_csv(
    PIN_TERR_FILE,
    usecols=["pincode", "Division Name", "Affiliate", "Final Mapped Territory"],
    dtype={"pincode": "string", "Division Name": "string", "Affiliate": "string"},
    low_memory=False,
)

offtake.shape, db_level.shape, dvl_from_ff.shape


# In[11]:


# Rename to match original Step-5 naming
dvl_from_ff.rename(columns={"Final Mapped Territory": "Territory Code"}, inplace=True)

dvl_from_ff.head()


# In[12]:


# Combine offtake + db-level (same conceptual inputs as original)
res = pd.concat([offtake, db_level], ignore_index=True)

# Original Step-5 filters last N months relative to last_date
last_date = res["month"].max()
offtake_data_filtered = res.loc[
    (res["month"] > last_date - pd.tseries.offsets.MonthBegin(custom_months))
    & (res["month"] <= last_date)
].copy()

# Original: average across custom_months
offtake_data_filtered["channel_sales1"] = offtake_data_filtered["channel_sales"] / custom_months

offtake_data_filtered.shape


# In[13]:


for df in [offtake, db_level]:
    df["Affiliate"] = df["Affiliate"].str.upper().str.strip()
    df["Division Name"] = df["Division Name"].str.upper().str.strip()
    df["name of customer"] = df["name of customer"].str.upper().str.strip()


# In[16]:


def normalize_customer(name):
    if pd.isna(name):
        return name
    name = name.upper().strip()
    if "APOLLO" in name:
        return "APOLLO"
    if "KEIMED" in name:
        return "KEIMEDGT"
    if "NETMEDS" in name:
        return "NETMEDS"
    if "MEDPLUS" in name:
        return "MEDPLUS"
    if "PHARMEASY" in name:
        return "PHARMEASY"
    return name

for df in [offtake, db_level]:
    df["name of customer"] = df["name of customer"].apply(normalize_customer)


# In[17]:


# Merge territory mapping
final_dvl = dvl_from_ff.copy()

# How many territories are mapped to each pincode for each division
dvl_grouped_bu_pin = (
    final_dvl.groupby(["Division Name", "pincode"], dropna=False)
    .agg({"Territory Code": pd.Series.nunique})
    .reset_index()
)

# Avoid divide-by-zero (matches original replace 0->1 behavior)
dvl_grouped_bu_pin["Territory Code"] = dvl_grouped_bu_pin["Territory Code"].replace(0, 1)
dvl_grouped_bu_pin.rename(columns={"Territory Code": "count"}, inplace=True)

# Attach count to sales
offtake_grouped = pd.merge(
    offtake_data_filtered,
    dvl_grouped_bu_pin,
    how="left",
    left_on=["Division Name", "pincode"],
    right_on=["Division Name", "pincode"],
)
offtake_grouped["count"] = offtake_grouped["count"].fillna(1)

# Original: allocate averaged channel sales across multiple territories
offtake_grouped["app_chan_sales"] = offtake_grouped["channel_sales1"] / offtake_grouped["count"]

# Join territory code onto each row (one-to-many possible)
offtake_grouped_new = pd.merge(
    offtake_grouped,
    final_dvl[["pincode", "Division Name", "Affiliate", "Territory Code"]],
    how="left",
    on=["pincode", "Division Name", "Affiliate"],
)

# ✅ REMOVE UNMAPPED TERRITORIES BEFORE CONTRIBUTION LOGIC
offtake_grouped_new = offtake_grouped_new[
    offtake_grouped_new["Territory Code"].notna()
].copy()

cols_to_keep = ["name of customer", "Division Name", "Territory Code", "pincode", "channel_sales", "app_chan_sales"]
offtake_grouped_req = offtake_grouped_new[cols_to_keep].copy()

# Original name normalizations
offtake_grouped_req["name of customer"] = offtake_grouped_req["name of customer"].replace(["SASTA SUNDAR"], "FLIPKART HEALTH PLUS")
offtake_grouped_req["name of customer"] = offtake_grouped_req["name of customer"].replace(["KIEMEDGT"], "KEIMEDGT")

# Split Apollo/Keimed vs other accounts
offtake_grouped_req2 = offtake_grouped_req.loc[offtake_grouped_req["name of customer"].isin(["APOLLO", "KEIMEDGT"])].copy()
offtake_grouped_req_other = offtake_grouped_req.loc[offtake_grouped_req["name of customer"].isin(["1MG","MEDPLUS","PHARMEASY","FLIPKART HEALTH PLUS","UDAAN","WELLNESS","NETMEDS"])].copy()

offtake_grouped_req2.shape, offtake_grouped_req_other.shape


# In[19]:


offtake_grouped_new["name of customer"].value_counts().head()


# In[18]:


# ----------------------------
# Apollo + Keimed blended ratio (matches original core)
# ----------------------------

terr_data_ap = (
    offtake_grouped_req2.groupby(["name of customer", "Division Name", "pincode", "Territory Code"], dropna=False)[["channel_sales", "app_chan_sales"]]
    .sum()
    .reset_index()
)

terr_data_ap["final_channel_sales"] = np.where(
    pd.isna(terr_data_ap["Territory Code"]),
    terr_data_ap["channel_sales"] / custom_months,
    terr_data_ap["app_chan_sales"],
)
terr_data_ap["Territory Code"] = terr_data_ap.fillna(0)["Territory Code"]

terr_data_ap2 = (
    terr_data_ap.groupby(["name of customer", "Division Name", "Territory Code"])[["final_channel_sales"]]
    .sum()
    .reset_index()
)

terr_data_ap3 = terr_data_ap2.pivot(
    index=["Division Name", "Territory Code"],
    columns="name of customer",
    values="final_channel_sales",
).reset_index()

# Ensure expected columns exist
for col in ["APOLLO", "KEIMEDGT"]:
    if col not in terr_data_ap3.columns:
        terr_data_ap3[col] = 0

terr_data_ap3 = terr_data_ap3.rename(columns={"APOLLO": "final_channel_sales_APOLLO", "KEIMEDGT": "final_channel_sales_KEIMEDGT"})

b_ap = terr_data_ap3.groupby(["Division Name"])[["final_channel_sales_APOLLO", "final_channel_sales_KEIMEDGT"]].transform("sum")
terr_data_ap4 = pd.concat([terr_data_ap3, b_ap], axis=1)
terr_data_ap4.fillna(0, inplace=True)
terr_data_ap4.columns = ["Division Name","Territory Code","final_channel_sales_APOLLO","final_channel_sales_KEIMEDGT","total_sales_APOLLO","total_sales_KEIMEDGT"]

terr_data_ap4["Territory_Sales"] = terr_data_ap4["final_channel_sales_KEIMEDGT"] + terr_data_ap4["final_channel_sales_APOLLO"]
terr_data_ap4["total_sales"] = terr_data_ap4["total_sales_APOLLO"] + terr_data_ap4["total_sales_KEIMEDGT"]
terr_data_ap4["Keimed_Apollo_Blended_Ratio"] = np.where(terr_data_ap4["total_sales"] == 0, 0, terr_data_ap4["Territory_Sales"] / terr_data_ap4["total_sales"])

terr_data_ap_write = terr_data_ap4.copy()
terr_data_ap_write["name of customer"] = "KEIMED"
terr_data_ap_write.rename(columns={"Territory_Sales": "final_channel_sales", "Keimed_Apollo_Blended_Ratio": "contri"}, inplace=True)
terr_data_ap_write = terr_data_ap_write[["name of customer", "Division Name", "Territory Code", "final_channel_sales", "total_sales", "contri"]]

# ----------------------------
# Other accounts contribution (matches original core)
# ----------------------------

terr_data = (
    offtake_grouped_req_other.groupby(["name of customer", "Division Name", "pincode", "Territory Code"], dropna=False)[["channel_sales", "app_chan_sales"]]
    .sum()
    .reset_index()
)

terr_data["final_channel_sales"] = np.where(
    pd.isna(terr_data["Territory Code"]),
    terr_data["channel_sales"] / custom_months,
    terr_data["app_chan_sales"],
)

terr_data["Territory Code"] = terr_data.fillna(0)["Territory Code"]

terr_data2 = terr_data.groupby(["name of customer", "Division Name", "Territory Code"])[["final_channel_sales"]].sum().reset_index()
b = terr_data2.groupby(["Division Name", "name of customer"])["final_channel_sales"].transform("sum")
terr_data4 = pd.concat([terr_data2, b], axis=1)
terr_data4.columns = ["name of customer", "Division Name", "Territory Code", "final_channel_sales", "total_sales"]
terr_data4["contri"] = np.where(terr_data4["total_sales"] == 0, 0, terr_data4["final_channel_sales"] / terr_data4["total_sales"])

# Append blended Keimed/Apollo contribution rows
terr_data4 = pd.concat([terr_data4, terr_data_ap_write], axis=0, ignore_index=True)

terr_data4.to_csv(OUT_CONTRI, index=False)

{
    "rows": terr_data4.shape[0],
    "output": str(OUT_CONTRI),
}

