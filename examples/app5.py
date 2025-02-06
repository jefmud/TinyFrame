# test redirect feature in TinyFrame app.redirect('/myview')
from tinyframe import TinyFrame, ClassView
app = TinyFrame()

@app.route('/')
def index(request, response):
    # Render the main page
    return app.redirect('/success')

@app.route('/myview')
class MyView(ClassView):
    def get(self, request, response):
        # Render the form
        return app.render_template('input_form.html')

    def post(self, request, response):
        # Process form and redirect to a success page
        return app.redirect('/success')

@app.route('/success')
def success(request, response):
    return "Form submitted successfully!"

# Run the application
app.run()
