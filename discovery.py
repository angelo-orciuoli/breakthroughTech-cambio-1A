# discovery.py
import json
import requests
import csv
import datetime as dt
import pathlib
import time

URL_SEARCH = "https://api.grants.gov/v1/api/search2"
URL_FETCH  = "https://api.grants.gov/v1/api/fetchOpportunity"  # to get detail fields like URL

CONFIG_PATH = pathlib.Path("config/internal_keywords.json")
with open(CONFIG_PATH) as f:
    INT = json.load(f)

def search_grants(keyword="education", rows=200, statuses="forecasted|posted", max_records=2000):
    """
    Fetch ALL pages from Grants.gov search2 API.
    Returns a flat list of oppHits (not the whole response).
    """
    all_hits = []
    start_record = 0
    total_expected = None

    while True:
        payload = {
            "keyword": keyword,
            "rows": rows,                  # page size (200 is fine)
            "oppStatuses": statuses,       # "posted" or "forecasted|posted"
            "startRecordNum": start_record,
            "oppNum": "",
            "eligibilities": "",
            "agencies": "",
            "aln": "",
            "fundingCategories": ""
        }
        r = requests.post(URL_SEARCH, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        r.raise_for_status()
        data = r.json().get("data", {})

        hits = data.get("oppHits", []) or []
        total = data.get("hitCount", 0)
        if total_expected is None:
            total_expected = total

        # append this page
        all_hits.extend(hits)
        print(f"Fetched {len(all_hits)} / {total_expected or '?'} so far...")

        # stop conditions
        if not hits:
            break
        if total_expected and len(all_hits) >= total_expected:
            break
        if max_records and len(all_hits) >= max_records:
            break

        start_record += rows  # move to next page

    print(f"Finished fetching {len(all_hits)} total opportunities.")
    return all_hits

def fetch_details(opp_number: str) -> dict:
    # Returns detail payload (often includes more fields/links)
    r = requests.post(URL_FETCH, json={"oppNum": opp_number}, headers={"Content-Type": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()

def get(item, *keys, default=""):
    for k in keys:
        if k in item and item[k]:
            return item[k]
    return default

def parse_date(s: str):
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

MIN_DAYS_TO_DEADLINE = 10  # drop if fewer days left

def passes_filters(item: dict) -> bool:
    # deadline screen (only if close date exists)
    d = parse_date(item.get("closeDate") or item.get("CloseDate") or "")
    if d:
        days_left = (d - dt.date.today()).days
        if days_left < MIN_DAYS_TO_DEADLINE:
            return False
    return True

def score_opportunity(item: dict) -> tuple[int, dict]:
    """Return (score, breakdown) based on title+agency text."""
    text = f"{item.get('title','')} {item.get('agency','')}".lower()
    m = sum(kw in text for kw in INT["mission"])
    p = sum(kw in text for kw in INT["programs"])
    t = sum(kw in text for kw in INT["technology"])

    # weights/caps (simple & explainable)
    mission_pts = min(40, m * 8)
    program_pts = min(24, p * 6)
    tech_pts    = min(16, t * 4)

    # small bonus if clearly nonprofit/edu friendly (if present in text)
    if any(x in text for x in ["nonprofit", "education organization", "community-based"]):
        mission_pts += 10

    total = min(100, mission_pts + program_pts + tech_pts)
    breakdown = {
        "mission_hits": m, "program_hits": p, "tech_hits": t,
        "mission_pts": mission_pts, "program_pts": program_pts, "tech_pts": tech_pts
    }
    return total, breakdown

def enrich_with_details(item: dict) -> dict:
    """Fetch detail fields and merge them for better scoring."""
    oppnum = get(item, "number", "OpportunityNumber")
    out = dict(item)  # copy search hit
    out["eligibilityText"] = ""
    out["synopsisText"] = ""
    out["categoryText"] = ""
    out["url"] = get(item, "url", "OpportunityURL", default="")
    if not oppnum:
        return out
    try:
        details = fetch_details(oppnum).get("data", {})
        out["eligibilityText"] = (
            details.get("EligibilityCategory") or
            details.get("Eligibility") or
            details.get("EligibleApplicants") or
            ""
        )
        out["synopsisText"] = (
            details.get("SynopsisText") or
            details.get("Description") or
            details.get("Synopsis") or
            ""
        )
        out["categoryText"] = (
            details.get("CategoryOfFundingActivity") or
            details.get("FundingCategories") or
            ""
        )
        out["url"] = (
            details.get("OpportunityURL") or
            details.get("SynopsisURL") or
            details.get("opportunitySynopsisURL") or
            out.get("url","")
        )
    except Exception:
        pass
    return out

def score_opportunity_rich(item: dict) -> tuple[int, dict]:
    """Extended scoring using synopsis/eligibility/category text, returns counts & points."""
    text = (
        f"{item.get('title','')} "
        f"{item.get('agency','')} "
        f"{item.get('synopsisText','')} "
        f"{item.get('eligibilityText','')} "
        f"{item.get('categoryText','')}"
    ).lower()

    m = sum(kw in text for kw in INT["mission"])
    p = sum(kw in text for kw in INT["programs"])
    t = sum(kw in text for kw in INT["technology"])

    mission_pts = min(40, m * 8)
    program_pts = min(24, p * 6)
    tech_pts    = min(16, t * 4)

    # gentle bonus for explicit alignment words
    if any(x in text for x in ["youth", "bipoc", "education", "workforce", "community"]):
        mission_pts += 10

    total = min(100, mission_pts + program_pts + tech_pts)
    breakdown = {
        "MissionHits": m, "ProgramHits": p, "TechHits": t,
        "MissionPts": mission_pts, "ProgramPts": program_pts, "TechPts": tech_pts
    }
    return total, breakdown

def days_left(close_str: str) -> int | None:
    d = parse_date(close_str or "")
    if not d:
        return None
    return (d - dt.date.today()).days

# filter policy for "relevant to Cambio"
SCORE_THRESHOLD = 40
REQUIRE_ANY_ALIGNMENT = True  # at least one of mission/program/tech hits

def is_relevant(row: dict) -> bool:
    if row["Score"] < SCORE_THRESHOLD:
        return False
    if REQUIRE_ANY_ALIGNMENT:
        b = json.loads(row["ScoreBreakdown"])
        if (b["MissionHits"] + b["ProgramHits"] + b["TechHits"]) == 0:
            return False
    # OPTIONAL: require friendly eligibility text
    elig = (row.get("Eligibility") or "").lower()
    if any(x in elig for x in ["for-profit only", "small business only"]):
        return False
    return True

def clean_row(row: dict) -> dict:
    """Fill missing values and add derived columns."""
    row["Category"] = row.get("Category") or "Not specified"
    row["Eligibility"] = row.get("Eligibility") or "Not specified"
    row["URL"] = row.get("URL") or "Not specified"
    row["DaysLeft"] = days_left(row.get("CloseDate") or "")
    # unpack breakdown for columns
    try:
        b = json.loads(row["ScoreBreakdown"])
        row.update(b)
    except Exception:
        pass
    return row

if __name__ == "__main__":
    # 1) Pull ALL pages (pagination)
    hits = search_grants(
        keyword="education OR youth OR workforce",
        rows=200,
        statuses="forecasted|posted",
        max_records=2000
    )
    total = len(hits)
    if not hits:
        print("No opportunities returned.")
        raise SystemExit(0)

    # 2) Score + filter + enrich + export 
    rows = []
    for i, item in enumerate(hits):
        title = get(item, "title", "OpportunityTitle", default="(no title)")
        agency = get(item, "agency", "AgencyName")
        close  = get(item, "closeDate", "CloseDate")
        oppnum = get(item, "number", "OpportunityNumber")

        rec = {"title": title, "agency": agency, "closeDate": close, "number": oppnum}

        # deadline filter
        if not passes_filters(rec):
            continue

        # enrich (synopsis/eligibility/category/url)
        rich = enrich_with_details(item)

        score, breakdown = score_opportunity_rich({
            "title": title,
            "agency": agency,
            "synopsisText": rich.get("synopsisText", ""),
            "eligibilityText": rich.get("eligibilityText", ""),
            "categoryText": rich.get("categoryText", ""),
        })

        rows.append({
            "Score": score,
            "Title": title,
            "Agency": agency,
            "CloseDate": close,
            "OppNumber": oppnum,
            "Category": rich.get("categoryText",""),
            "Eligibility": rich.get("eligibilityText","")[:240],
            "URL": rich.get("url",""),
            "ScoreBreakdown": json.dumps(breakdown)
        })

    # 3) Sort & keep top N for quick review 
    # Clean rows and compute relevant set
    for r in rows:
        clean_row(r)

    relevant = [r for r in rows if is_relevant(r)]

    rows.sort(key=lambda r: r["Score"], reverse=True)
    relevant.sort(key=lambda r: r["Score"], reverse=True)

    FIELDS = [
        "Score","Title","Agency","CloseDate","DaysLeft","OppNumber",
        "Category","Eligibility","URL",
        "MissionHits","ProgramHits","TechHits","MissionPts","ProgramPts","TechPts",
        "ScoreBreakdown"
    ]

    with open("top_grants_relevant.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(relevant)

    with open("top_grants_full.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    # Console preview
    preview = relevant[:10] if relevant else rows[:10]
    print(f"Found {total} opps; after deadline filter kept {len(rows)}; relevant={len(relevant)}.")
    print("Top 10 relevant:")
    for r in preview:
        print(f"- {r['Title']} (Score {r['Score']}, DaysLeft {r['DaysLeft']})")
        print(f"  Agency: {r['Agency']} | Close: {r['CloseDate']} | Opp#: {r['OppNumber']}")
        print(f"  URL: {r['URL']}\n")

    print(f"Saved {len(relevant)} relevant to top_grants_relevant.csv and {len(rows)} full to top_grants_full.csv")

# --- DEBUG: score distribution ---
print(f"[debug] total rows (after deadline filter) = {len(rows)}")
if rows:
    scores = [r["Score"] for r in rows]
    print(f"[debug] min={min(scores)} max={max(scores)} avg={sum(scores)/len(scores):.1f}")
    print("[debug] sample titles with scores:")
    for r in rows[:5]:
        print(f"  - {r['Title'][:60]}...  -> {r['Score']}")
