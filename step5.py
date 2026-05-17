#!/usr/bin/env python
# coding: utf-8

# In[2]:


import pandas as pd
import numpy as np
from pathlib import Path

CUSTOM_MONTHS = 3


OFFTAKE_FILE = Path("C:/Users/pawarux2/OneDrive - Abbott/Documents/FFC/FFC Test/output/offtake_step2_final.csv")
DB_LEVEL_FILE = Path("C:/Users/pawarux2/OneDrive - Abbott/Documents/FFC/FFC Test/output/DB_Level_Apollo_Keimed_2026_local.csv")
PIN_TERR_FILE = Path("C:/Users/pawarux2/OneDrive - Abbott/Documents/FFC/FFC Test/input/20260402_Mar Pincode_Universe_AIL Mapped.csv")

OUT_CONTRI = Path("C:/Users/pawarux2/OneDrive - Abbott/Documents/FFC/FFC Test/output/FF_Contribution_All_Channels_local.csv")

custom_months = 3

for p in [OFFTAKE_FILE, DB_LEVEL_FILE, PIN_TERR_FILE]:
    if not p.exists():
        raise FileNotFoundError(f"Missing required input: {p}")


# In[3]:


# -------- LOAD STEP-2 OFFTAKE (SAFE) --------
offtake = pd.read_csv(OFFTAKE_FILE)

offtake = offtake[
    [
        "month",
        "name of customer",
        "Division Name",
        "Affiliate",
        "pincode",
        "channel_sales",
    ]
].copy()

offtake["month"] = pd.to_datetime(offtake["month"], errors="coerce")
offtake["pincode"] = offtake["pincode"].astype("string")


# -------- LOAD STEP-3 DB LEVEL (SAFE) --------
db_level = pd.read_csv(DB_LEVEL_FILE)

db_level = db_level[
    [
        "month",
        "name of customer",
        "Division Name",
        "Affiliate",
        "pincode",
        "channel_sales",
    ]
].copy()

db_level["month"] = pd.to_datetime(db_level["month"], errors="coerce")
db_level["pincode"] = db_level["pincode"].astype("string")


# -------- LOAD PINCODE → TERRITORY --------
dvl_from_ff = pd.read_csv(
    PIN_TERR_FILE,
    usecols=["pincode", "Division Name", "Affiliate", "Final Mapped Territory"],
    dtype={"pincode": "string"},
)

dvl_from_ff.rename(
    columns={"Final Mapped Territory": "Territory Code"}, inplace=True
)

offtake.shape, db_level.shape, dvl_from_ff.shape


# In[4]:


def normalize_customer(name):
    if pd.isna(name):
        return name
    n = name.upper().strip()
    if "APOLLO" in n:
        return "APOLLO"
    if "KEIMED" in n:
        return "KEIMEDGT"
    if "FLIPKART" in n:
        return "FLIPKART HEALTH PLUS"
    if "NETMEDS" in n:
        return "NETMEDS"
    return n

for df in [offtake, db_level]:
    df["name of customer"] = df["name of customer"].apply(normalize_customer)
    df["Division Name"] = df["Division Name"].str.upper().str.strip()
    df["Affiliate"] = df["Affiliate"].str.upper().str.strip()


# In[5]:


res = pd.concat([offtake, db_level], ignore_index=True)

last_date = res["month"].max()

offtake_data_filtered = res[
    (res["month"] > last_date - pd.offsets.MonthBegin(CUSTOM_MONTHS))
    & (res["month"] <= last_date)
].copy()

offtake_data_filtered["channel_sales1"] = (
    offtake_data_filtered["channel_sales"] / CUSTOM_MONTHS
)


# In[6]:


offtake_data_filtered["channel_sales"].sum()


# In[8]:


# Count how many territories per Division + pincode
dvl_grouped_bu_pin = (
    dvl_from_ff
    .groupby(["Division Name", "pincode"])
    .agg(count=("Territory Code", "nunique"))
    .reset_index()
)

dvl_grouped_bu_pin["count"] = dvl_grouped_bu_pin["count"].replace(0, 1)


# In[9]:


offtake_grouped = pd.merge(
    offtake_data_filtered,
    dvl_grouped_bu_pin,
    how="left",
    on=["Division Name", "pincode"],
)

offtake_grouped["count"] = offtake_grouped["count"].fillna(1)

offtake_grouped["app_chan_sales"] = (
    offtake_grouped["channel_sales1"] / offtake_grouped["count"]
)


# In[10]:


offtake_grouped_new = pd.merge(
    offtake_grouped,
    dvl_from_ff[["pincode", "Division Name", "Affiliate", "Territory Code"]],
    how="left",
    on=["pincode", "Division Name", "Affiliate"],
)

# ✅ IMPORTANT:
# Do NOT globally drop unmapped yet


# In[11]:


cols_to_keep = [
    "name of customer",
    "Division Name",
    "Territory Code",
    "pincode",
    "channel_sales",
    "app_chan_sales",
]

offtake_grouped_req = offtake_grouped_new[cols_to_keep].copy()


# In[12]:


# ✅ RESTORE channel_sales1 FOR CONTRIBUTION CALC
offtake_grouped_req["channel_sales1"] = (
    offtake_grouped_req["channel_sales"] / CUSTOM_MONTHS
)


# In[13]:


offtake_grouped_req["Territory Code"].notna().sum()


# In[14]:


ap_keimed = ["APOLLO", "KEIMEDGT"]
other_accounts = ["1MG", "MEDPLUS", "PHARMEASY", "FLIPKART HEALTH PLUS", "UDAAN", "WELLNESS", "NETMEDS"]

offtake_ap = offtake_grouped_req[
    offtake_grouped_req["name of customer"].isin(ap_keimed)
].copy()

offtake_other = offtake_grouped_req[
    offtake_grouped_req["name of customer"].isin(other_accounts)
].copy()


# In[15]:


offtake_ap = offtake_ap[offtake_ap["Territory Code"].notna()]
offtake_other = offtake_other[offtake_other["Territory Code"].notna()]


# In[16]:


terr_ap = (
    offtake_ap
    .groupby(["name of customer", "Division Name", "Territory Code"])
    [["channel_sales1", "app_chan_sales"]]
    .sum()
    .reset_index()
)

pivot_ap = terr_ap.pivot(
    index=["Division Name", "Territory Code"],
    columns="name of customer",
    values="channel_sales1",   # ✅ IMPORTANT CHANGE
).fillna(0).reset_index()

for c in ["APOLLO", "KEIMEDGT"]:
    if c not in pivot_ap.columns:
        pivot_ap[c] = 0

pivot_ap["final_channel_sales"] = pivot_ap["APOLLO"] + pivot_ap["KEIMEDGT"]
pivot_ap["total_sales"] = pivot_ap.groupby("Division Name")["final_channel_sales"].transform("sum")

pivot_ap["contri"] = np.where(
    pivot_ap["total_sales"] == 0,
    0,
    pivot_ap["final_channel_sales"] / pivot_ap["total_sales"]
)

pivot_ap["name of customer"] = "KEIMED"

terr_ap_final = pivot_ap[
    ["name of customer", "Division Name", "Territory Code", "final_channel_sales", "total_sales", "contri"]
]


# In[17]:


terr_other = (
    offtake_other
    .groupby(["name of customer", "Division Name", "Territory Code"])
    [["channel_sales1"]]
    .sum()
    .reset_index()
)

terr_other["total_sales"] = terr_other.groupby(
    ["name of customer", "Division Name"]
)["channel_sales1"].transform("sum")

terr_other["contri"] = np.where(
    terr_other["total_sales"] == 0,
    0,
    terr_other["channel_sales1"] / terr_other["total_sales"]
)

terr_other.rename(columns={"channel_sales1": "final_channel_sales"}, inplace=True)


# In[18]:


offtake_grouped_req["name of customer"].value_counts().head(20)


# In[19]:


final_output = pd.concat([terr_other, terr_ap_final], ignore_index=True)

final_output.to_csv(OUT_CONTRI, index=False)

final_output.shape


# In[20]:


final_output["contri"].describe()


# In[21]:


final_output.groupby("Division Name")["contri"].sum().head()


# In[22]:


final_output["Territory Code"].value_counts().head()


# In[ ]:




