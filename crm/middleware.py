from django.shortcuts import redirect


class WholesaleBuyerRestrictionMiddleware:
    """
    Restricts WholesaleBuyer users to only access the wholesale product lookup page.
    All other URLs redirect to /wholesale/.
    Must be placed after AuthenticationMiddleware in MIDDLEWARE.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if request.user.groups.filter(name='WholesaleBuyer').exists():
                path = request.path_info

                allowed_prefixes = (
                    '/wholesale/',
                    '/login/',
                    '/logout/',
                    '/',
                )

                if not any(path.startswith(prefix) for prefix in allowed_prefixes):
                    return redirect('/wholesale/')

        return self.get_response(request)
