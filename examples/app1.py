from tinyframe import TinyFrame, TinyFrameView

app = TinyFrame(template_folder='templates')

@app.route("/myview")
class MyView(TinyFrameView):
    def get(self, request, response):
        return "<h1>GET route</h1>"

    def post(self, request, response):
        return "<h1>POST route</h1>"

if __name__ == "__main__":
    app.run()
