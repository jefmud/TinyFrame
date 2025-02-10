#################################################################################################
# TinyFrame
#
# A very simple web framework by Jeff Muday
#
# lots of technical debt owed to the Pallets Project, Ben Darnell, Armin Ronacher, Marcel Helkamp
#
# (C) 2025 Jeff Muday, MIT License
#
#################################################################################################
import re
import uuid
from http import cookies
from urllib.parse import urlparse, parse_qs
from jinja2 import Environment, FileSystemLoader

__version__ = 0.4

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
        self.status_code = 200  # Default status code

    def set_header(self, key, value):
        self._headers[key] = value

    def set_cookie(self, key, value, path="/"):
        self._cookies[key] = value
        self._cookies[key]["path"] = path

    def redirect(self, location, status_code=302):
        """
        Set up a redirect response.

        Parameters:
          location (str): The URL to redirect to.
          status_code (int): The HTTP status code for the redirect (default is 302).
        """
        self.status_code = status_code
        self.set_header("Location", location)

# ------------------------------
# Class-Based Views Base Class
# ------------------------------
class ClassView:
    """
    Base class for class-based views.
    """
    def dispatch_request(self, request, response, **kwargs):
        """
        Dispatch the request to the appropriate method based on the HTTP method.
        """
        method = request.method.lower()
        if hasattr(self, method):
            return getattr(self, method)(request, response, **kwargs)
        else:
            # If the method is not implemented, return a 405 Method Not Allowed
            return "405 Method Not Allowed", 405

    @classmethod
    def get_supported_methods(cls):
        """
        Return a list of HTTP methods supported by this view.
        """
        methods = []
        for method in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']:
            if hasattr(cls, method):
                methods.append(method.upper())
        return methods
# ------------------------------
# TinyFrame Web Framework Class with Multiple Server Support
# ------------------------------
class TinyFrame:
    def __init__(self, template_folder='templates'):
        self.routes = []
        self.named_routes = {}  # Store named routes
        self.sessions = {}
        self.jinja_env = Environment(loader=FileSystemLoader(template_folder))

    def route(self, route_str, methods=None, name=None):
        def decorator(view):
            route_name = name or view.__name__  # Use provided name or default to function name
            compiled = compile_route(route_str)
            allowed_methods = methods if methods else ["GET"]
            
            self.routes.append((compiled, view, allowed_methods))
            self.named_routes[route_name] = {
                'pattern': route_str,
                'compiled': compiled,
                'view': view
            }
            return view
        return decorator

    def url_for(self, route_name, **params):
        if route_name not in self.named_routes:
            raise ValueError(f"No route named '{route_name}' found.")

        pattern = self.named_routes[route_name]['pattern']
        
        # Replace dynamic segments with provided parameters
        def repl(match):
            param_name = match.group(2)
            if param_name in params:
                return str(params.pop(param_name))
            raise ValueError(f"Missing parameter '{param_name}' for route '{route_name}'.")

        url = re.sub(r'<(path:)?(\w+)>', repl, pattern)

        # Append remaining params as query string
        if params:
            url += '?' + urlencode(params)

        return url


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

    def redirect(self, location, status_code=302):
        """
        Create a redirect response.

        Parameters:
          location (str): The URL to redirect to.
          status_code (int): The HTTP status code for the redirect (default is 302).
        """
        response = WSGIResponse()
        response.redirect(location, status_code)
        return response  # Returning the response object

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
                    result = view(request, response, **kwargs)
                    
                    # If the view returns a WSGIResponse object (like a redirect)
                    if isinstance(result, WSGIResponse):
                        return "", result.status_code, result  # Redirect or special response handling
                    
                    elif isinstance(result, tuple):
                        return result[0], result[1], response  # Handles (body, status_code)
                    
                    else:
                        return result, response.status_code, response  # Default case

        if found_route:
            return "405 Method Not Allowed", 405, response
        return None, None, response


    # ------------------------------
    # WSGI Application Interface
    # ------------------------------
    def wsgi_app(self, environ, start_response):
        req = WSGIRequest(environ)
        res = WSGIResponse()
        req.session = self._get_session(req, res)

        body, status, res = self._handle_request(req, res)

        if body is None:
            status = 404
            body = "404 Not Found"

        status_message = self._http_status_message(status)
        headers = [("Content-Type", "text/html")]

        # Include any headers set in the response object
        for key, value in res._headers.items():
            headers.append((key, value))

        # Handle cookies
        for morsel in res._cookies.values():
            headers.append(("Set-Cookie", morsel.OutputString()))

        start_response(f"{status} {status_message}", headers)

        # If it's a redirect, we don't need a body
        if status in [301, 302, 303, 307, 308]:
            return [b""]

        if isinstance(body, str):
            body = body.encode("utf-8")  # Convert string to bytes

        return [body]

    def _http_status_message(self, status_code):
        """return standard error messages given a status_code."""
        status_messages = {
        100: "Continue",
        101: "Switching Protocols",
        200: "OK",
        201: "Created",
        202: "Accepted",
        203: "Non-Authoritative Information",
        204: "No Content",
        205: "Reset Content",
        206: "Partial Content",
        300: "Multiple Choices",
        301: "Moved Permanently",
        302: "Found",
        303: "See Other",
        304: "Not Modified",
        305: "Use Proxy",
        307: "Temporary Redirect",
        400: "Bad Request",
        401: "Unauthorized",
        402: "Payment Required",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        406: "Not Acceptable",
        407: "Proxy Authentication Required",
        408: "Request Timeout",
        409: "Conflict",
        410: "Gone",
        411: "Length Required",
        412: "Precondition Failed",
        413: "Payload Too Large",
        414: "URI Too Long",
        415: "Unsupported Media Type",
        416: "Range Not Satisfiable",
        417: "Expectation Failed",
        418: "I'm a teapot",
        422: "Unprocessable Entity",
        425: "Too Early",
        426: "Upgrade Required",
        428: "Precondition Required",
        429: "Too Many Requests",
        431: "Request Header Fields Too Large",
        451: "Unavailable For Legal Reasons",
        500: "Internal Server Error",
        501: "Not Implemented",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
        505: "HTTP Version Not Supported",
        506: "Variant Also Negotiates",
        507: "Insufficient Storage",
        508: "Loop Detected",
        510: "Not Extended",
        511: "Network Authentication Required",
        }
        return status_messages.get(status_code, "Unknown Status Code")

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
