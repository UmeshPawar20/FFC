#!/usr/bin/env python
# coding: utf-8

# ## FFC — Step 4 (Local): Pincode Universe (Unmapped)
# 
# This notebook produces a local equivalent of the Step‑4 deliverable generated in `FFC/Step 4 - Pincode Universe.ipynb`.
# 
# It uses **local copies** of the Step‑2 final offtake output, Step‑3 Apollo/Keimed DB-level output, and the current pincode→territory universe mapping file.
# 
# ### Inputs (local)
# - Step 2 output CSV (local)
# - Step 3 output CSV (local)
# - Pincode universe mapping CSV (local)
# 
# ### Output
# - `output/Pincode_Universe_Unmapped_local.csv`
# 

# In[5]:


from pathlib import Path

print("Working directory:", Path().resolve())


# In[2]:


import os
from pathlib import Path
import pandas as pd
import numpy as np

os.makedirs("output", exist_ok=True)

# ----------------------------
# CONFIG (edit these paths)
# ----------------------------

# Step 2 final offtake file (local)
OFFTAKE_FILE = Path("output/offtake_step2_final.csv")

# Step 3 Apollo+Keimed DB-level file (local)
DB_LEVEL_FILE = Path("output/DB_Level_Apollo_Keimed_2026_local.csv")

# Pincode universe mapping (use the in-repo file by default)
# This file matches the original Step-4 inputs and contains:
# pincode, Division Name, Affiliate, State, District, Previously Mapped Territory Code, Final Mapped Territory
PIN_UNIVERSE_FILE = Path("C:/Users/pawarux2/OneDrive - Abbott/Documents/FFC/FFC Test/input/20260402_Mar Pincode_Universe_AIL Mapped.csv")

OUT_UNMAPPED = Path("output/Pincode_Universe_Unmapped_local.csv")

for p in [OFFTAKE_FILE, DB_LEVEL_FILE, PIN_UNIVERSE_FILE]:
    if not p.exists():
        raise FileNotFoundError(f"Missing required input: {p}")


# In[3]:


# Load inputs (optimized: read only required columns)

offtake = pd.read_csv(
    OFFTAKE_FILE,
    usecols=["pincode", "Division Name", "Affiliate", "State", "District"],
    dtype={"pincode": "string", "Division Name": "string", "Affiliate": "string"},
    low_memory=False,
)

db_level = pd.read_csv(
    DB_LEVEL_FILE,
    usecols=["pincode", "Division Name", "Affiliate", "State", "District"],
    dtype={"pincode": "string", "Division Name": "string", "Affiliate": "string"},
    low_memory=False,
)

pin_universe = pd.read_csv(
    PIN_UNIVERSE_FILE,
    usecols=[
        "pincode",
        "Division Name",
        "Affiliate",
        "State",
        "District",
        "Previously Mapped Territory Code",
        "Final Mapped Territory",
    ],
    dtype={"pincode": "string", "Division Name": "string", "Affiliate": "string"},
    low_memory=False,
)

offtake.head(2), db_level.head(2), pin_universe.head(2)


# In[ ]:


# Clean mapping universe (same logic as original Step-4)
pin_universe_2 = pin_universe.copy()

bad_markers = {"0", "Not mapped", "Unmapped", "Dummy"}

pin_universe_2["Final Mapped Territory"] = np.where(
    pin_universe_2["Final Mapped Territory"].astype(str).isin(bad_markers),
    np.nan,
    pin_universe_2["Final Mapped Territory"],
)

pin_universe_2["Previously Mapped Territory Code"] = np.where(
    pin_universe_2["Previously Mapped Territory Code"].astype(str).isin(bad_markers),
    np.nan,
    pin_universe_2["Previously Mapped Territory Code"],
)

pin_universe_2["Final Mapped Territory"] = np.where(
    pd.isna(pin_universe_2["Final Mapped Territory"]),
    pin_universe_2["Previously Mapped Territory Code"],
    pin_universe_2["Final Mapped Territory"],
)

pin_universe_2.head(3)


# In[ ]:


# Collect pincodes observed in sales (offtake + db-level)

# Observed pincodes from both sources
offtake_obs = offtake.copy()
db_obs = db_level.copy()

observed = pd.concat([offtake_obs, db_obs], ignore_index=True)
observed = observed.drop_duplicates()

observed.shape


# In[ ]:


# Left-join to mapping universe to identify missing (unmapped) pincodes
merged = pd.merge(
    observed,
    pin_universe_2[["pincode", "Division Name", "Affiliate", "Final Mapped Territory"]],
    how="left",
    on=["pincode", "Division Name", "Affiliate"],
)

unmapped = merged[pd.isna(merged["Final Mapped Territory"])].copy()

unmapped.to_csv(OUT_UNMAPPED, index=False)

{
    "unmapped_rows": unmapped.shape[0],
    "output": str(OUT_UNMAPPED),
}

