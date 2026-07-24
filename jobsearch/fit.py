"""Score how well a job opening fits Sarah's profile.

Profile: policy / international relations, works in EN/FR/ES (some NL/PT),
2-5 years' experience, interested in an anthropology PhD, with a deliberate
Latin America / Spanish angle.

Given a job title (the openings detector already extracts these), return a
0-100 fit score plus the reasons, so the app can surface the best-matched
openings first and filter to "good fit only". Multilingual, because the
catalogue is full of French/Dutch/Spanish/German postings.
"""
import re

# --- strong-fit topics (the core of her profile) -----------------------
POLICY = (
    "policy", "policies", "advocacy", "adviser", "advisor", "affairs",
    "programme", "program", "public affairs", "government affairs",
    "politique", "plaidoyer", "conseiller", "beleid", "politik", "referent",
    "incidencia", "politica", "politiche",
)
LATAM = (
    "latin america", "latin-america", "latam", "eu-lac", "lac ", "mercosur",
    "celac", "amerique latine", "america latina", "iberoameric",
    "spanish", "hispanophone", "espagnol", "español", "hispano",
    "colombia", "mexico", "brazil", "argentina", "chile", "peru", "bolivia",
    "guatemala", "venezuela", "cuba", "andean", "central america",
)
RESEARCH = (
    "research", "researcher", "phd", "doctoral", "doctorate", "postdoc",
    "post-doc", "academic", "fellow", "fellowship", "chercheur", "onderzoek",
    "wissenschaftlich", "investigador", "ricercatore", "study", "studies",
    "anthropolog", "ethnograph",
)
# --- secondary-fit (adjacent, she's qualified) -------------------------
SECONDARY = (
    "communications", "communication", "comms", "project", "coordinator",
    "coordination", "campaign", "engagement", "outreach", "partnerships",
    "development", "human rights", "migration", "asylum", "gender", "climate",
    "trade", "digital", "chargé", "coordinateur", "projet", "coördinator",
    "kommunikation", "comunicación", "comunicazione", "diritti", "derechos",
)

# --- seniority signals -------------------------------------------------
TOO_SENIOR = (
    "head of", "director", "directeur", "directrice", "chief", "secretary general",
    "secretary-general", "secretaire general", "senior", "lead ", "principal",
    "vice-president", "vice president", "deputy director", "managing director",
    "leiter", "leiterin", "directeur", "jefe", "responsabile", "capo",
    "president", "chef de", "cheffe de", "head,", "director,",
)
JUNIOR = (
    "junior", "assistant", "trainee", "traineeship", "intern", "internship",
    "stagiaire", "stage", "graduate", "entry", "praktik", "becario", "stagista",
    "aankomend", "débutant",
)
# Right-level words for 2-5 years.
MID = (
    "officer", "adviser", "advisor", "coordinator", "manager", "analyst",
    "associate", "specialist", "consultant", "chargé", "conseiller",
    "medewerker", "referent", "responsable", "gestor", "funcionario",
)

# Her working languages, for a small language-match bonus.
HER_LANGS = ("french", "français", "spanish", "español", "espagnol",
             "english", "dutch", "néerlandais", "portuguese", "portugais")


def _has(text: str, terms) -> bool:
    return any(t in text for t in terms)


# The fit dimensions Sarah can toggle on/off. Each maps to a keyword group and
# its point contribution; turning one off removes both its points and its
# reason. Defaults are all-on -- the profile as originally tuned.
DIMENSIONS = ("policy", "latam", "research", "comms", "seniority")
DEFAULT_DIMS = {d: True for d in DIMENSIONS}


def score_title(title: str, dims: dict | None = None) -> dict:
    """0-100 fit score for one opening title, with reasons.

    `dims` toggles the scoring dimensions on/off (see DIMENSIONS); None means
    all on. A dimension that's off contributes neither points nor a reason, so
    Sarah can, say, stop rewarding comms roles or stop penalising senior ones.
    """
    d = {**DEFAULT_DIMS, **(dims or {})}
    t = (title or "").lower()
    if not t or len(t) < 3:
        return {"score": 0, "reasons": [], "band": "unknown"}

    score = 30  # a real job title starts as a plausible baseline
    reasons = []

    # Topic match -- strong-fit areas.
    if d["policy"] and _has(t, POLICY):
        score += 28
        reasons.append("policy / advocacy role")
    if d["latam"] and _has(t, LATAM):
        score += 25
        reasons.append("Latin America / Spanish angle")
    if d["research"] and _has(t, RESEARCH):
        score += 22
        reasons.append("research / PhD track")
    if d["comms"] and _has(t, SECONDARY):
        score += 12
        reasons.append("adjacent area she's qualified for")

    # Seniority -- she's 2-5 years in. The penalty is a toggle; the mid/junior
    # level signals always apply (they're not what "seniority filter" means).
    if d["seniority"] and _has(t, TOO_SENIOR):
        score -= 30
        reasons.append("likely too senior")
    elif _has(t, MID):
        score += 12
        reasons.append("right level (officer / adviser / coordinator)")
    elif _has(t, JUNIOR):
        score -= 6
        reasons.append("entry-level (a bit junior, but an EU foot in the door)")

    # Language edge.
    if _has(t, HER_LANGS):
        score += 6
        reasons.append("names one of her languages")

    score = max(0, min(100, score))
    band = ("strong" if score >= 65 else "possible" if score >= 45
            else "weak")
    return {"score": score, "reasons": reasons, "band": band}


def score_openings(titles: list[str], dims: dict | None = None) -> dict:
    """Aggregate fit across an org's openings.

    Returns the best title's score/band, plus how many openings are a strong
    or possible fit -- so the app can say '3 of 8 openings fit her'.
    """
    if not titles:
        return {"best_score": 0, "best_band": "none", "best_title": "",
                "strong": 0, "possible": 0, "scored": []}
    scored = [{"title": t, **score_title(t, dims)} for t in titles]
    scored.sort(key=lambda s: -s["score"])
    top = scored[0]
    return {
        "best_score": top["score"],
        "best_band": top["band"],
        "best_title": top["title"],
        "strong": sum(1 for s in scored if s["band"] == "strong"),
        "possible": sum(1 for s in scored if s["band"] == "possible"),
        "scored": scored,
    }


if __name__ == "__main__":
    import sys
    for title in sys.argv[1:]:
        d = score_title(title)
        print(f"{d['score']:>3} {d['band']:<9} {title}")
        for r in d["reasons"]:
            print(f"      · {r}")
