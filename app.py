from flask import Flask, render_template, redirect, url_for, request
import random
import copy

app = Flask(__name__)

# -------------------------------------------------
# NO-CACHE HEADERS
# -------------------------------------------------
@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# -----------------------------
# MISSION CONFIG (PHASE B)
# -----------------------------
MISSION_TYPES = {
    "tech": {
        "label": "Tech Operation",
        "base_success": 0.8,
        "base_heat": 5,
        "wm_integrity_loss": 10,
        "max_crew": 3,
    },
    "physical": {
        "label": "Physical Operation",
        "base_success": 0.65,
        "base_heat": 12,
        "wm_integrity_loss": 20,
        "max_crew": 4,
    },
    # Shadow kept simple for now; we will gate visibility later
    "shadow": {
        "label": "Shadow Operation",
        "base_success": 0.6,
        "base_heat": -5,
        "wm_integrity_loss": 5,
        "max_crew": 2,
    },
}

# -----------------------------
# BASE GAME STATE
# -----------------------------
BASE_GAME_STATE = {
    "day": 1,
    "credits": 1000,
    "global_heat": 0,
    "war_machine": {
        "integrity": 100,
        "repair_days": 0,
        "upgrades": {},
    },
    "crew": [
        {
            "name": "Vega",
            "injury": None,
            "injury_days": 0,
            "heat_mod": 8,
            "specialty": "Tech",
            "backstory": "Brilliant hacker with corporate escapee background.",
            "relations": ["Kade (partner)", "Iris (teammate)"],
            "status": "Active",
            "known_shadow": [],
        },
        {
            "name": "Kade",
            "injury": None,
            "injury_days": 0,
            "heat_mod": 12,
            "specialty": "Physical",
            "backstory": "Ex-special forces, heavy weapons expert.",
            "relations": ["Vega (partner)", "Viper (contact)"],
            "status": "Active",
            "known_shadow": [],
        },
        {
            "name": "Iris",
            "injury": None,
            "injury_days": 0,
            "heat_mod": 3,
            "specialty": "Stealth",
            "backstory": "Ghost operative, master of infiltration.",
            "relations": ["Vega (teammate)"],
            "status": "Active",
            "known_shadow": [],
        },
        {
            "name": "Viper",
            "injury": None,
            "injury_days": 0,
            "heat_mod": 4,
            "specialty": "Tech/Physical (solo/tact)",
            "backstory": "Ex-gun runner with underground contacts (guns/tech/hackers). Bros with Artemis, jobs for Kai/Piper.",
            "relations": ["Artemis (brother-like)", "Kai (jobs)", "Piper (jobs)", "Kade (contact)"],
            "status": "Active",
            "known_shadow": [],
        },
    ],
    "mission_history": [],
    "last_mission_result": None,
    "last_mission_config": {
        "mission_type": "tech",
        "selected_crew": [],
        "projected_success": None,
        "projected_heat_change": None,
        "projected_wm_integrity_change": None,
    },
}

sandbox_state = copy.deepcopy(BASE_GAME_STATE)
game_state = copy.deepcopy(BASE_GAME_STATE)

# -----------------------------
# HEAT / RISK / ADVISOR
# -----------------------------
def heat_tier(heat: int) -> str:
    if heat < 10:
        return "Cold"
    if heat < 25:
        return "Warm"
    if heat < 45:
        return "Hot"
    if heat < 70:
        return "Severe"
    return "Critical"


def injury_chance_by_heat(heat: int) -> int:
    table = {
        "Cold": 5,
        "Warm": 10,
        "Hot": 20,
        "Severe": 35,
        "Critical": 55,
    }
    return table[heat_tier(heat)]


def advisor_for_heat(heat: int) -> dict:
    table = {
        "Cold": {"severity": "calm", "message": "Heat is low. Operations are safe."},
        "Warm": {"severity": "notice", "message": "Minor attention detected."},
        "Hot": {"severity": "warning", "message": "Heat is rising. Expect resistance."},
        "Severe": {"severity": "urgent", "message": "High risk. Injuries likely."},
        "Critical": {"severity": "critical", "message": "Exposure critical. Stand down."},
    }
    return table[heat_tier(heat)]


def risk_for_heat(heat: int) -> dict:
    return {
        "tier": heat_tier(heat),
        "injury_chance": injury_chance_by_heat(heat),
    }

# -----------------------------
# NAVIGATION
# -----------------------------
def nav_for(mode: str) -> dict:
    base = "sandbox_" if mode == "sandbox" else "campaign_"
    return {
        "command": url_for(f"{base}index"),
        "mission_plan": url_for(f"{base}mission_plan"),
        "history": url_for(f"{base}history"),
        "medical": url_for(f"{base}medical"),
        "war_machine": url_for(f"{base}war_machine"),
        "crew": url_for(f"{base}crew"),
        "toggle": url_for("toggle_mode"),
    }

# -----------------------------
# MISSION PREVIEW LOGIC
# -----------------------------
def compute_mission_preview(state: dict, mission_type: str, selected_crew_names: list[str]) -> dict:
    mt = MISSION_TYPES[mission_type]
    crew_objs = [c for c in state["crew"] if c["name"] in selected_crew_names]

    base_success = mt["base_success"]
    specialties = [c["specialty"] for c in crew_objs]

    # Basic specialty bonuses / penalties
    if mission_type == "tech":
        if any("Tech" in s for s in specialties):
            base_success += 0.05
        else:
            base_success -= 0.1
    elif mission_type == "physical":
        if any("Physical" in s for s in specialties):
            base_success += 0.05
        else:
            base_success -= 0.1
    elif mission_type == "shadow":
        if any("Stealth" in s or "Shadow" in s for s in specialties):
            base_success += 0.05
        else:
            base_success -= 0.1

    base_success = max(0.2, min(0.95, base_success))

    crew_heat = sum(c.get("heat_mod", 0) for c in crew_objs)
    heat_change = mt["base_heat"] + crew_heat

    wm_change = -mt["wm_integrity_loss"]

    return {
        "projected_success": round(base_success * 100),
        "projected_heat_change": heat_change,
        "projected_wm_change": wm_change,
    }

# -----------------------------
# CORE ACTIONS
# -----------------------------
def advance_day(state: dict) -> None:
    state["day"] += 1
    state["global_heat"] = max(0, state["global_heat"] - 1)
    for member in state["crew"]:
        if member["injury"] == "Injured":
            member["injury_days"] = member.get("injury_days", 0) + 1
            if member["injury_days"] >= 3:
                member["injury"] = None
                member["injury_days"] = 0
        else:
            member["injury_days"] = 0
    # WM auto-repair hooks could go here later


def resolve_mission(state: dict, mission_type: str, selected_crew_names: list[str]) -> None:
    mt = MISSION_TYPES[mission_type]
    preview = compute_mission_preview(state, mission_type, selected_crew_names)

    state["global_heat"] = max(0, state["global_heat"] + preview["projected_heat_change"])
    state["war_machine"]["integrity"] = max(
        0,
        min(100, state["war_machine"]["integrity"] + preview["projected_wm_change"]),
    )

    success_chance = preview["projected_success"] / 100.0
    roll = random.random()

    if roll < success_chance * 0.75:
        outcome = "Success"
    elif roll < success_chance + 0.25:
        outcome = "Messy Success"
    else:
        outcome = "Failure"

    injuries = []
    chance = injury_chance_by_heat(state["global_heat"]) / 100.0
    for member in state["crew"]:
        if member["name"] in selected_crew_names and member["injury"] is None:
            if random.random() < chance:
                member["injury"] = "Injured"
                member["injury_days"] = 0
                injuries.append(member["name"])

    result = {
        "day": state["day"],
        "outcome": outcome,
        "heat_after": state["global_heat"],
        "wm_integrity_after": state["war_machine"]["integrity"],
        "injuries": injuries,
        "mission_type": mission_type,
        "mission_label": mt["label"],
        "crew": selected_crew_names,
        "projected_success": preview["projected_success"],
        "projected_heat_change": preview["projected_heat_change"],
        "projected_wm_change": preview["projected_wm_change"],
    }

    state["mission_history"].append(result)
    state["last_mission_result"] = result
    state["last_mission_config"] = {
        "mission_type": mission_type,
        "selected_crew": selected_crew_names,
        "projected_success": preview["projected_success"],
        "projected_heat_change": preview["projected_heat_change"],
        "projected_wm_integrity_change": preview["projected_wm_change"],
    }

# -----------------------------
# MODE TOGGLE
# -----------------------------
@app.route("/toggle")
def toggle_mode():
    if request.referrer and "sandbox" in request.referrer:
        return redirect(url_for("campaign_index"))
    return redirect(url_for("sandbox_index"))

# -----------------------------
# SANDBOX ROUTES
# -----------------------------
@app.route("/sandbox", methods=["GET", "POST"])
def sandbox_index():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "advance_day":
            advance_day(sandbox_state)
            return redirect(url_for("sandbox_index"))
    return render_template(
        "index.html",
        state=sandbox_state,
        advisor=advisor_for_heat(sandbox_state["global_heat"]),
        nav=nav_for("sandbox"),
        mode="sandbox",
        heat_tier=heat_tier,
    )


@app.route("/sandbox/mission_plan", methods=["GET", "POST"])
def sandbox_mission_plan():
    if request.method == "POST":
        mission_type = request.form.get("mission_type", "tech")
        selected_crew = request.form.getlist("crew")
        preview = compute_mission_preview(sandbox_state, mission_type, selected_crew) if selected_crew else None
        return render_template(
            "mission_plan.html",
            risk=risk_for_heat(sandbox_state["global_heat"]),
            advisor=advisor_for_heat(sandbox_state["global_heat"]),
            nav=nav_for("sandbox"),
            mode="sandbox",
            heat_tier=heat_tier,
            mission_types=MISSION_TYPES,
            crew=sandbox_state["crew"],
            selected_type=mission_type,
            selected_crew=selected_crew,
            preview=preview,
        )

    return render_template(
        "mission_plan.html",
        risk=risk_for_heat(sandbox_state["global_heat"]),
        advisor=advisor_for_heat(sandbox_state["global_heat"]),
        nav=nav_for("sandbox"),
        mode="sandbox",
        heat_tier=heat_tier,
        mission_types=MISSION_TYPES,
        crew=sandbox_state["crew"],
        selected_type="tech",
        selected_crew=[],
        preview=None,
    )


@app.route("/sandbox/launch_mission", methods=["POST"])
def sandbox_launch_mission():
    mission_type = request.form.get("mission_type", "tech")
    selected_crew = request.form.getlist("crew")
    if not selected_crew:
        return redirect(url_for("sandbox_mission_plan"))
    resolve_mission(sandbox_state, mission_type, selected_crew)
    return redirect(url_for("sandbox_mission_result"))


@app.route("/sandbox/mission_result")
def sandbox_mission_result():
    return render_template(
        "mission_result.html",
        result=sandbox_state["last_mission_result"],
        nav=nav_for("sandbox"),
        mode="sandbox",
    )


@app.route("/sandbox/history")
def sandbox_history():
    return render_template(
        "history.html",
        history=sandbox_state["mission_history"],
        nav=nav_for("sandbox"),
        mode="sandbox",
    )


@app.route("/sandbox/medical", methods=["GET", "POST"])
def sandbox_medical():
    if request.method == "POST":
        for member in sandbox_state["crew"]:
            if member["injury"] == "Injured":
                member["injury"] = None
                member["injury_days"] = 0
        return redirect(url_for("sandbox_medical"))
    injured = [c for c in sandbox_state["crew"] if c["injury"]]
    return render_template(
        "medical.html",
        injured=injured,
        nav=nav_for("sandbox"),
        mode="sandbox",
    )


@app.route("/sandbox/war_machine", methods=["GET", "POST"])
def sandbox_war_machine():
    if request.method == "POST":
        sandbox_state["war_machine"]["integrity"] = 100
        return redirect(url_for("sandbox_war_machine"))
    return render_template(
        "war_machine.html",
        wm=sandbox_state["war_machine"],
        nav=nav_for("sandbox"),
        mode="sandbox",
    )


@app.route("/sandbox/crew")
def sandbox_crew():
    return render_template(
        "crew.html",
        crew=sandbox_state["crew"],
        nav=nav_for("sandbox"),
        mode="sandbox",
        heat_tier=heat_tier,
    )


@app.route("/sandbox/lay_low", methods=["POST"])
def sandbox_lay_low():
    sandbox_state["global_heat"] = max(0, sandbox_state["global_heat"] - 3)
    return redirect(url_for("sandbox_index"))


@app.route("/sandbox/espionage", methods=["POST"])
def sandbox_espionage():
    sandbox_state["global_heat"] = max(0, sandbox_state["global_heat"] - 6)
    return redirect(url_for("sandbox_index"))

# -----------------------------
# CAMPAIGN ROUTES
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def campaign_index():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "advance_day":
            advance_day(game_state)
            return redirect(url_for("campaign_index"))
    return render_template(
        "index.html",
        state=game_state,
        advisor=advisor_for_heat(game_state["global_heat"]),
        nav=nav_for("campaign"),
        mode="campaign",
        heat_tier=heat_tier,
    )


@app.route("/campaign/mission_plan", methods=["GET", "POST"])
def campaign_mission_plan():
    if request.method == "POST":
        mission_type = request.form.get("mission_type", "tech")
        selected_crew = request.form.getlist("crew")
        preview = compute_mission_preview(game_state, mission_type, selected_crew) if selected_crew else None
        return render_template(
            "mission_plan.html",
            risk=risk_for_heat(game_state["global_heat"]),
            advisor=advisor_for_heat(game_state["global_heat"]),
            nav=nav_for("campaign"),
            mode="campaign",
            heat_tier=heat_tier,
            mission_types=MISSION_TYPES,
            crew=game_state["crew"],
            selected_type=mission_type,
            selected_crew=selected_crew,
            preview=preview,
        )

    return render_template(
        "mission_plan.html",
        risk=risk_for_heat(game_state["global_heat"]),
        advisor=advisor_for_heat(game_state["global_heat"]),
        nav=nav_for("campaign"),
        mode="campaign",
        heat_tier=heat_tier,
        mission_types=MISSION_TYPES,
        crew=game_state["crew"],
        selected_type="tech",
        selected_crew=[],
        preview=None,
    )


@app.route("/campaign/launch_mission", methods=["POST"])
def campaign_launch_mission():
    mission_type = request.form.get("mission_type", "tech")
    selected_crew = request.form.getlist("crew")
    if not selected_crew:
        return redirect(url_for("campaign_mission_plan"))
    resolve_mission(game_state, mission_type, selected_crew)
    return redirect(url_for("campaign_mission_result"))


@app.route("/campaign/mission_result")
def campaign_mission_result():
    return render_template(
        "mission_result.html",
        result=game_state["last_mission_result"],
        nav=nav_for("campaign"),
        mode="campaign",
    )


@app.route("/campaign/history")
def campaign_history():
    return render_template(
        "history.html",
        history=game_state["mission_history"],
        nav=nav_for("campaign"),
        mode="campaign",
    )


@app.route("/campaign/medical", methods=["GET", "POST"])
def campaign_medical():
    if request.method == "POST":
        for member in game_state["crew"]:
            if member["injury"] == "Injured":
                member["injury"] = None
                member["injury_days"] = 0
        return redirect(url_for("campaign_medical"))
    injured = [c for c in game_state["crew"] if c["injury"]]
    return render_template(
        "medical.html",
        injured=injured,
        nav=nav_for("campaign"),
        mode="campaign",
    )


@app.route("/campaign/war_machine", methods=["GET", "POST"])
def campaign_war_machine():
    if request.method == "POST":
        game_state["war_machine"]["integrity"] = 100
        return redirect(url_for("campaign_war_machine"))
    return render_template(
        "war_machine.html",
        wm=game_state["war_machine"],
        nav=nav_for("campaign"),
        mode="campaign",
    )


@app.route("/campaign/crew")
def campaign_crew():
    return render_template(
        "crew.html",
        crew=game_state["crew"],
        nav=nav_for("campaign"),
        mode="campaign",
        heat_tier=heat_tier,
    )


@app.route("/campaign/lay_low", methods=["POST"])
def campaign_lay_low():
    game_state["global_heat"] = max(0, game_state["global_heat"] - 3)
    return redirect(url_for("campaign_index"))


@app.route("/campaign/espionage", methods=["POST"])
def campaign_espionage():
    game_state["global_heat"] = max(0, game_state["global_heat"] - 6)
    return redirect(url_for("campaign_index"))

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)
