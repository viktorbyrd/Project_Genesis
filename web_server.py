from flask import Flask, render_template, redirect, url_for
from project_genesis import GameEngine

app = Flask(__name__)
engine = GameEngine()
engine.load_game()

@app.route("/")
def index():
    state = engine.state
    return render_template(
        "index.html",
        state=state,
        actions=engine.get_actions()
    )

@app.route("/action/<int:choice>")
def take_action(choice):
    try:
        engine.execute(choice)
        engine.save_game()
    except Exception as e:
        print("Action error:", e)
    return redirect(url_for("index"))

@app.route("/export")
def export():
    filename = engine.export_save(engine.state)
    return f"Exported save to {filename}"

if __name__ == "__main__":
    app.run(debug=True)
