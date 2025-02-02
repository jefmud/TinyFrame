from tinyframe import TinyFrame

app = TinyFrame(template_folder='templates')

@app.route("/hello/<name>", methods=["GET"])
def hello(request, response, name):
    return f"<h1>Hello, {name}!</h1>"

if __name__ == "__main__":
    # You can choose the server: 'wsgiref', 'waitress', 'paste', or 'twisted'
    app.run(host='127.0.0.1', port=5000, server='waitress')
