from rest_framework import authentication


class SessionAuthentication(authentication.SessionAuthentication):
    """Session auth that answers unauthenticated requests with 401 instead of 403.

    The SPA uses the 401 to detect an expired session and send the user to login.
    """

    def authenticate_header(self, request):
        return 'Session realm="api"'
