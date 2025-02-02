#################################################################################################
# TinyFrame
#
# A very simple web framework by Jeff Muday
#
# lots of technical debt owed to the Pallets Project, Ben Darnell, Armin Ronacher, Marcel Helkamp
#
# (C) 2025
#
#################################################################################################
import re
import uuid
from http import cookies
from urllib.parse import urlparse, parse_qs
from jinja2 import Environment, FileSystemLoader

# ------------------------------
# Helpers for Compiling Dynamic Routes
# ------------------------------
def compile_route(route_str):
    """
    Convert a route string with dynamic parameters into a regular expression.
    Supports:
      - /hello/<name>         => captures one segment as "name"
      - /mypath/<path:var>      => captures the rest of the path as "var" (allows slashes)
    """
    pattern = '^'
    def repl(match):
        # If match.group(1) is provided then we are using the "path:" converter.
        if match.group(1):
            return '(?P<{}>.+)'.format(match.group(2))
        else:
            return '(?P<{}>[^/]+)'.format(match.group(2))
    pattern += re.sub(r'<(path:)?(\w+)>', repl, route_str)
    pattern += '$'
    return re.compile(pattern)

# ------------------------------
# WSGI-Adapted Request and Response Classes
# ------------------------------
class WSGIRequest:
    def __init__(self, environ):
        self.environ = environ
        self.method = environ.get("REQUEST_METHOD", "GET")
        self.path = environ.get("PATH_INFO", "/")
        self.query_params = parse_qs(environ.get("QUERY_STRING", ""))
        # Build headers from the WSGI environ (headers are in HTTP_ variables)
        self.headers = {}
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").title()
                self.headers[header_name] = value
        if "CONTENT_TYPE" in environ:
            self.headers["Content-Type"] = environ["CONTENT_TYPE"]
        if "CONTENT_LENGTH" in environ:
            self.headers["Content-Length"] = environ["CONTENT_LENGTH"]
        from http import cookies
        self.cookies = cookies.SimpleCookie()
        if "HTTP_COOKIE" in environ:
            self.cookies.load(environ["HTTP_COOKIE"])
        self.session = None
        # Internal cache for form data so that the input stream is read only once.
        self._form = None

    def get_post_data(self):
        """
        Read and return the raw POST data from the request.
        (This method is provided for cases where you need the unparsed data.)
        """
        try:
            length = int(self.environ.get('CONTENT_LENGTH', 0))
        except (ValueError, TypeError):
            length = 0
        return self.environ['wsgi.input'].read(length)

    @property
    def form(self):
        """
        Parse the POST data (assumed to be URL-encoded) and return it as a dictionary.
        If a key has a single value, it returns that value; otherwise, it returns a list.
        This property caches its value so that the input stream is READ ONLY ONCE.
        (I made a mistake implementing this function, but fixed now)
        """
        if self._form is None:
            # Only attempt to read the form if this is a POST request.
            if self.method.upper() == "POST":
                try:
                    length = int(self.environ.get('CONTENT_LENGTH', 0))
                except (ValueError, TypeError):
                    length = 0
                # Read the raw POST data.
                raw_data = self.environ['wsgi.input'].read(length)
                # Decode the data into a string (assuming UTF-8) and parse it.
                parsed = parse_qs(raw_data.decode('utf-8'))
                # Convert parsed values: if a key's value list has one item, use that item.
                self._form = {key: value[0] if len(value) == 1 else value
                              for key, value in parsed.items()}
            else:
                self._form = {}
        return self._form

class WSGIResponse:
    def __init__(self):
        self._headers = {}
        self._cookies = cookies.SimpleCookie()

    def set_header(self, key, value):
        self._headers[key] = value

    def set_cookie(self, key, value, path="/"):
        self._cookies[key] = value
        self._cookies[key]["path"] = path

# ------------------------------
# Class-Based Views Base Class
# ------------------------------
class TinyFrameView:
    """
    Base class for class-based views in TinyFrame.
    Subclass this and define methods named after HTTP verbs (in lowercase)
    such as get(), post(), etc.
    """
    def dispatch_request(self, request, response, **kwargs):
        method = request.method.lower()
        if not hasattr(self, method):
            return "405 Method Not Allowed", 405
        handler = getattr(self, method)
        return handler(request, response, **kwargs)

# ------------------------------
# TinyFrame Web Framework Class with Multiple Server Support
# ------------------------------
class TinyFrame:
    def __init__(self, template_folder='templates'):
        # Store routes as a list of tuples: (compiled_regex, view_function, allowed_methods)
        self.routes = []
        # In-memory session store: session_id -> session data dictionary.
        self.sessions = {}
        # Set up Jinja2 environment for templating.
        self.jinja_env = Environment(loader=FileSystemLoader(template_folder))

    def route(self, route_str, methods=["GET"]):
        """
        A decorator to register a view for a given route.

        If used on a function, it registers that function.
        If used on a class that is a subclass of TinyFrameView, it wraps the class
        so that an instance is created and dispatch_request() is called.

        Example usage:

            @app.route('/myview')
            class MyView(TinyFrameView):
                def get(self, request, response):
                    return "GET route"
                def post(self, request, response):
                    return "POST route"
        """
        def decorator(view):
            compiled = compile_route(route_str)
            # If view is a class-based view, wrap it.
            if isinstance(view, type) and issubclass(view, TinyFrameView):
                def view_func(request, response, **kwargs):
                    view_instance = view()
                    return view_instance.dispatch_request(request, response, **kwargs)
                allowed_methods = methods
                self.routes.append((compiled, view_func, allowed_methods))
            else:
                self.routes.append((compiled, view, methods))
            return view
        return decorator

    def add_route(self, path=None, callback=None, methods=None, name=None):
        """
        A slightly simpler way of adding a non-decorator specified route.
        
          add_route(path, callback, methods, name):
          
          path - the path including route specifier
          callback - the view function
          methods - ["GET","POST", ...] defaults to ["GET"]
          name - (unused) for future versions that support url_for()
        """
        if methods is None:
            methods = ['GET']
        if path and callback:
            self.routes.append( (compile_route(path), callback, methods) )
        else:
            raise ValueError("TinyFrame.add_route requires both a path and view_function callback")

    def render_template(self, template_name, **context):
        """
        Render a template using Jinja2.
        """
        template = self.jinja_env.get_template(template_name)
        return template.render(**context)

    def _get_session(self, request, response):
        """
        Retrieve an existing session (via a cookie) or create a new one.
        """
        session_cookie = request.cookies.get("session_id")
        session_id = session_cookie.value if session_cookie else None
        if session_id and session_id in self.sessions:
            session = self.sessions[session_id]
        else:
            session_id = str(uuid.uuid4())
            session = {}
            self.sessions[session_id] = session
            response.set_cookie("session_id", session_id)
        return session

    def _handle_request(self, request, response):
        """
        Iterate over registered routes. If a route pattern matches the request path,
        verify that the HTTP method is allowed and call the view function with any
        captured parameters.
        Returns a tuple: (body, status_code)
        """
        found_route = False
        for pattern, view, methods in self.routes:
            match = pattern.match(request.path)
            if match:
                found_route = True
                if request.method.upper() in [m.upper() for m in methods]:
                    kwargs = match.groupdict()
                    return view(request, response, **kwargs), 200
        if found_route:
            return "405 Method Not Allowed", 405
        return None, None

    # ------------------------------
    # WSGI Application Interface
    # ------------------------------
    def wsgi_app(self, environ, start_response):
        req = WSGIRequest(environ)
        res = WSGIResponse()
        req.session = self._get_session(req, res)
        body, status = self._handle_request(req, res)
        if body is None:
            status = 404
            body = "404 Not Found"
        status_message = self._http_status_message(status)
        headers = [("Content-Type", "text/html")]
        for key, value in res._headers.items():
            headers.append((key, value))
        for morsel in res._cookies.values():
            headers.append(("Set-Cookie", morsel.OutputString()))
        start_response(f"{status} {status_message}", headers)
        if isinstance(body, str):
            body = body.encode("utf-8")
        return [body]

    def _http_status_message(self, status):
        messages = {
            200: "OK",
            404: "Not Found",
            405: "Method Not Allowed"
        }
        return messages.get(status, "OK")

    # ------------------------------
    # Unified Run Method Supporting Multiple Servers
    # ------------------------------
    def run(self, host='127.0.0.1', port=5000, server='wsgiref', keyfile=None, certfile=None):
        """
        Run the application using the specified server.

        Parameters:
          host    - hostname to bind (default '127.0.0.1')
          port    - port number to bind (default 5000)
          server  - one of 'wsgiref', 'waitress', 'paste', 'twisted'
          keyfile - path to an SSL key file (for 'twisted' SSL; ignored by others)
          certfile- path to an SSL certificate file (for 'twisted' SSL; ignored by others)
        """
        server = server.lower()
        if server == 'wsgiref':
            from wsgiref.simple_server import make_server
            if keyfile or certfile:
                print("Warning: wsgiref does not support SSL. Ignoring keyfile/certfile.")
            print(f"Serving on http://{host}:{port} with wsgiref")
            httpd = make_server(host, port, self.wsgi_app)
            httpd.serve_forever()

        elif server == 'waitress':
            from waitress import serve
            print(f"Serving on http://{host}:{port} with waitress")
            serve(self.wsgi_app, host=host, port=port)

        elif server == 'paste':
            from paste import httpserver
            print(f"Serving on http://{host}:{port} with paste")
            httpserver.serve(self.wsgi_app, host=host, port=str(port))

        elif server == 'twisted':
            from twisted.web.wsgi import WSGIResource
            from twisted.web.server import Site
            from twisted.internet import reactor
            if keyfile and certfile:
                from twisted.internet import ssl
                contextFactory = ssl.DefaultOpenSSLContextFactory(keyfile, certfile)
                resource = WSGIResource(reactor, reactor.getThreadPool(), self.wsgi_app)
                site = Site(resource)
                reactor.listenSSL(port, site, contextFactory)
            else:
                resource = WSGIResource(reactor, reactor.getThreadPool(), self.wsgi_app)
                site = Site(resource)
                reactor.listenTCP(port, site)
            print(f"Serving on http://{host}:{port} with twisted")
            reactor.run()

        else:
            raise ValueError(f"Unknown server type: {server}")
