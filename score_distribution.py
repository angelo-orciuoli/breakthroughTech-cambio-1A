# save as filter_relevant.py and run with: python3 -u filter_relevant.py
import pandas as pd

df = pd.read_csv("top_grants_full.csv")

df["Fit"] = df[["MissionPts","ProgramPts","TechPts"]].sum(axis=1)
df["Score2"] = df["Score"]*2 + df["Fit"]  # weight Score higher than Fit
relevant2 = df.sort_values(["Score2","Score"], ascending=False)
relevant2.head(100).to_csv("top_grants_relevant_fit.csv", index=False)


def pick_relevant(df, min_rows=60, q_target=0.90, hard_floor=18):
    # Start at target quantile
    thresh = df["Score"].quantile(q_target)
    out = df[df["Score"] >= thresh]

    # If too few, relax to 80th then 70th
    for q_try in (0.80, 0.70):
        if len(out) < min_rows:
            thresh = df["Score"].quantile(q_try)
            out = df[df["Score"] >= thresh]

    # Enforce a hard floor so we don't dip into noise
    if hard_floor is not None:
        out = out[out["Score"] >= hard_floor]

    # Optional: prune obvious out-of-scope/ancient stuff by simple heuristics
    # (edit these to match your mission)
    bad_title_words = [
        "Biennale",           # art exhibitions
    ]
    bad_year_words = [
        "2018",               # very old programs sprinkled in titles
    ]
    mask_bad = False
    for w in bad_title_words + bad_year_words:
        mask_bad = mask_bad | out["Title"].str.contains(w, case=False, na=False)
    out = out[~mask_bad]

    # Sort nicely
    return out.sort_values(["Score","CloseDate","Title"], ascending=[False, True, True])

relevant = pick_relevant(df, min_rows=40, q_target=0.90, hard_floor=18)
print(f"[info] kept {len(relevant)} after filtering (≥ quantile & ≥18 & prunes)")

# Save main relevant list
relevant_cols = ["Title","Agency","CloseDate","DaysLeft","OppNumber","Category","Eligibility","URL","Score","ScoreBreakdown"]
relevant[relevant_cols].to_csv("top_grants_relevant.csv", index=False)

# Also save a deterministic top-K list as a fallback
TOP_K = 100
topk = df.sort_values("Score", ascending=False).head(TOP_K)
topk[relevant_cols].to_csv("top_grants_relevant_topk.csv", index=False)

# Quick console preview
print("\n Preview (top 20 by Score)")
print(relevant.head(20)[["Title","Agency","CloseDate","Score"]].to_string(index=False))
