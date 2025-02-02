from tinyframe import TinyFrame

app = TinyFrame(template_folder='templates')

# A dynamic GET route: /hello/<name>
@app.route("/hello/<name>", methods=["GET"])
def hello(request, response, name):
    return f"<h1>Hello, {name}!</h1>"

# A route that accepts GET and POST:
@app.route("/submit", methods=["GET", "POST"])
def submit(request, response):
    if request.method == "GET":
        # Render a simple form (could be from a template as well)
        return """
            <form method="post" action="/submit">
                <input type="text" name="data" placeholder="Enter something">
                <input type="submit" value="Submit">
            </form>
        """
    elif request.method == "POST":
        # For simplicity, we'll echo a simple message.
        # (Note: In a complete implementation, you'd parse the POST body.)
        return "<h1>Form Submitted!</h1>"

# A route with query parameters: /greet?firstname=John&lastname=Doe
@app.route("/greet", methods=["GET"])
def greet(request, response):
    firstname = request.query_params.get("firstname", ["Guest"])[0]
    lastname = request.query_params.get("lastname", [""])[0]
    return f"<h1>Hello, {firstname} {lastname}!</h1>"

if __name__ == "__main__":
    app.run()
