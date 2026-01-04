# project_genesis.py

class GameEngine:
    def __init__(self):
        self.state = {
            "crew": [
                {"id": "c1", "name": "Artemis", "skills": {"ops": 3}, "injured": False},
                {"id": "c2", "name": "Jake", "skills": {"ops": 2}, "injured": False},
                {"id": "c3", "name": "Destiny", "skills": {"ops": 4}, "injured": False},
            ],
            "heat": 0,
            "war_machine": {"integrity": 100},
            "mission_history": []
        }
        self.last_mission_report = None

    def get_actions(self):
        return ["Prepare mission", "Advance time"]

    def resolve_mission(self, crew_ids):
        total_ops = sum(
            c["skills"]["ops"]
            for c in self.state["crew"]
            if c["id"] in crew_ids
        )

        # Outcome logic
        if total_ops >= 7:
            outcome = "Clean Success"
            heat = 2
            integrity_loss = 0
        elif total_ops >= 4:
            outcome = "Messy Success"
            heat = 5
            integrity_loss = 5
        else:
            outcome = "Failure"
            heat = 8
            integrity_loss = 10

        self.state["heat"] += heat
        self.state["war_machine"]["integrity"] = max(
            0, self.state["war_machine"]["integrity"] - integrity_loss
        )

        entry = {
            "outcome": outcome,
            "crew": crew_ids,
            "heat": heat,
            "integrity_loss": integrity_loss,
        }

        self.state["mission_history"].insert(0, entry)
        self.last_mission_report = entry

    def advance_time(self):
        # Placeholder for future recovery / decay
        pass
