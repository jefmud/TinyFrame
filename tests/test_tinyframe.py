# you've got to have tests!
#
import unittest
from tinyframe import TinyFrame, TinyFrameView
from io import BytesIO

def simulate_request(app, path, method="GET", query_string="", headers=None, body=b""):
    """
    Simulate a WSGI request to the TinyFrame app.
    
    Returns a tuple of (status, response_headers, response_body as string).
    """
    # Build a minimal WSGI environ dictionary.
    environ = {
        'REQUEST_METHOD': method,
        'PATH_INFO': path,
        'QUERY_STRING': query_string,
        'wsgi.input': BytesIO(body),
        'wsgi.errors': BytesIO(),
        'wsgi.version': (1, 0),
        'wsgi.run_once': False,
        'wsgi.url_scheme': 'http',
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
    }
    
    # Add any extra headers.
    if headers:
        for key, value in headers.items():
            environ['HTTP_' + key.upper().replace("-", "_")] = value

    # A dictionary to capture status and headers set by start_response.
    captured = {}
    def start_response(status, response_headers, exc_info=None):
        captured['status'] = status
        captured['headers'] = response_headers

    # Call the WSGI application.
    result = app.wsgi_app(environ, start_response)
    response_body = b"".join(result).decode('utf-8')
    return captured.get('status'), captured.get('headers'), response_body

class TestTinyFrame(unittest.TestCase):

    def setUp(self):
        # Create a TinyFrame instance and register some routes.
        self.app = TinyFrame(template_folder='templates')
        
        # Simple function-based route.
        @self.app.route("/simple")
        def simple_route(request, response):
            return "Simple route"
        
        # Dynamic route with a parameter.
        @self.app.route("/hello/<name>")
        def hello(request, response, name):
            return f"Hello, {name}!"
        
        # Route that allows only GET.
        @self.app.route("/onlyget", methods=["GET"])
        def only_get(request, response):
            return "GET only"
        
        # Class-based view example.
        @self.app.route("/myview")
        class MyView(TinyFrameView):
            def get(self, request, response):
                return "GET view"
            def post(self, request, response):
                return "POST view"

    def test_simple_route(self):
        status, headers, body = simulate_request(self.app, "/simple")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(body, "Simple route")

    def test_dynamic_route(self):
        status, headers, body = simulate_request(self.app, "/hello/John")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(body, "Hello, John!")

    def test_not_found(self):
        status, headers, body = simulate_request(self.app, "/nonexistent")
        self.assertTrue(status.startswith("404"))
        self.assertEqual(body, "404 Not Found")

    def test_method_not_allowed(self):
        # The route /onlyget only allows GET. We'll simulate a POST.
        status, headers, body = simulate_request(self.app, "/onlyget", method="POST")
        self.assertTrue(status.startswith("405"))
        self.assertEqual(body, "405 Method Not Allowed")

    def test_class_based_view_get(self):
        status, headers, body = simulate_request(self.app, "/myview", method="GET")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(body, "GET view")

    def test_class_based_view_post(self):
        status, headers, body = simulate_request(self.app, "/myview", method="POST")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(body, "POST view")

if __name__ == '__main__':
    unittest.main()
