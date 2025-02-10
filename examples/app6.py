# app6.py
# ------------------------------
# Example Usage
# ------------------------------
from tinyframe import TinyFrame

app = TinyFrame()

@app.route('/', name='home')
def home(request, response):
    return f'<a href="{app.url_for("about")}">Go to About</a>'

@app.route('/about', name='about')
def about(request, response):
    return '<h1>About Page</h1>'

@app.route('/user/<name>', name='user_profile')
def user_profile(request, response, name):
    return f'<h1>Welcome, {name}!</h1>'

# Example Redirect Usage
@app.route('/redirect-to-user')
def redirect_example(request, response):
    return app.redirect(app.url_for('user_profile', name='JohnDoe'))

app.run()