from tinyframe import TinyFrame

# Initialize the framework with the folder where templates are stored
app = TinyFrame(template_folder='templates')

@app.route("/")
def index(request, response):
    # Use the session to count page visits
    session = request.session
    session["visits"] = session.get("visits", 0) + 1
    # Render a template, passing the visit count to it
    return app.render_template("index.html", visits=session["visits"])

@app.route("/hello")
def hello(request, response):
    return "<h1>Hello from the non-decorator route!</h1>"

if __name__ == "__main__":
    app.run()
